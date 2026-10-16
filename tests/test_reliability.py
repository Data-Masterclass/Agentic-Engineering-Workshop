"""Prepared components only; no completed learner investigation or solution graph."""
import copy
import json
import time
from decimal import Decimal
from pathlib import Path
import pytest
from langgraph.graph import StateGraph, START
from workshop.pack import CASES, fixture, load_packet, seed, sha256, DATA
from workshop.runtime import Budget, Runtime, ScriptedClient, LiveClient, Terminal
from workshop.tools import page_image
from workshop.extraction import extract
from workshop.schemas import Evidence, InvestigationResult, Invoice
from workshop.validation import apply_findings, validate, recommendation
from workshop.graph import Nodes, State, guarded_route, run
from workshop.scripts import interaction_examples
from workshop import agent as learner_agent, graph as learner_graph, tools as learner_tools

@pytest.fixture
def setup(tmp_path):
    db = tmp_path / "demo.sqlite"
    seed(db)
    def get(case="reading-conflict", client=None, budget=None):
        ex = fixture(case)
        runtime = Runtime(ex, client, budget)
        # Test-only validation fixture. run() strips packet before graph execution.
        state = {"candidate": ex.candidate.model_dump(mode="json"), "packet": load_packet(case, db)}
        return runtime, state
    return get

@pytest.mark.original_scaffold
@pytest.mark.parametrize("case", CASES)
def test_actual_starter_langgraph(setup, case):
    runtime, state = setup(case)
    nodes = Nodes(runtime, learner_agent.investigate, packet=state["packet"])
    result = run(learner_graph.build_graph(nodes), state, nodes)
    assert result["recommendation"] == ("READY_FOR_APPROVAL" if case == "matching" else "NEEDS_CLARIFICATION")
    assert runtime.budget.models == runtime.budget.tools == 0
    events = [e["event"] for e in runtime.events]
    assert ("investigation" in events) == (case != "matching")
    if case != "matching":
        assert "investigation not implemented" in result["handoff"]

@pytest.mark.parametrize("category", ["receipts", "duplicate_scope"])
def test_missing_coverage_never_ready(setup, category):
    runtime, state = setup("matching")
    state["packet"]["coverage"] = [r for r in state["packet"]["coverage"] if r["dataset"] != category]
    assert recommendation(validate(**state)) == "NEEDS_CLARIFICATION"

@pytest.mark.parametrize("change", ["bank", "currency", "duplicate"])
def test_confirmed_blocking(setup, change):
    runtime, state = setup("matching")
    if change == "bank":
        state["candidate"]["bank_account"] = "DEMO-OTHER"
    elif change == "currency":
        state["packet"]["purchase_orders"][0]["currency"] = "USD"
    else:
        state["packet"]["invoice_history"][0]["invoice_number"] = state["candidate"]["invoice_number"]
    assert recommendation(validate(**state)) == "ESCALATE"

@pytest.mark.parametrize("tool_request", [
    {"name":"arbitrary_sql", "invoice_id":"reading-conflict", "page":1},
    {"name":"review_pdf_page", "invoice_id":"../../secret", "page":1},
    {"name":"review_pdf_page", "invoice_id":"matching", "page":1},
    {"name":"review_pdf_page", "invoice_id":"reading-conflict", "page":2},
    {"name":"review_pdf_page", "invoice_id":"reading-conflict", "page":0},
    {"name":"review_pdf_page", "invoice_id":"reading-conflict", "page":1, "url":"https://bad.invalid"},
])
def test_invalid_tool_counts_and_terminates(setup, tool_request):
    runtime, _ = setup()
    with pytest.raises(Terminal):
        runtime.review(tool_request)
    assert runtime.budget.tools == 1
    assert runtime.budget.terminal
    with pytest.raises(Terminal):
        runtime.review({"name":"review_pdf_page", "invoice_id":"reading-conflict", "page":1})
    assert runtime.budget.tools == 1

# Direct prepared-helper test, not an autonomous agent or completed learner node.
def test_supported_reading_preserves_original(setup):
    runtime, state = setup()
    before = copy.deepcopy(state["candidate"])
    assert recommendation(validate(**state)) == "NEEDS_CLARIFICATION"
    requests, findings = interaction_examples("reading-conflict")
    runtime.review(requests["tool_requests"][0])
    corrected = apply_findings(before, findings["findings"], runtime)
    assert recommendation(validate(corrected, state["packet"])) == "READY_FOR_APPROVAL"
    assert state["candidate"] == before
    assert str(runtime.extraction.original.lines[0].quantity) == "100"
    assert runtime.history[0]["before"] == "100"
    assert runtime.history[0]["evidence_id"] in runtime.evidence

@pytest.mark.parametrize("bad", ["unknown", "wrongvalue", "unknownline", "supplier", "ambiguous", "conflicting"])
def test_unsupported_findings_rejected(setup, bad):
    runtime, state = setup()
    runtime.review(interaction_examples("reading-conflict")[0]["tool_requests"][0])
    finding = interaction_examples("reading-conflict")[1]["findings"]
    correction = finding["corrections"][0]
    if bad == "unknown": correction["evidence_id"] = "invented"
    if bad == "wrongvalue": correction["value"] = "1"
    if bad == "unknownline": correction["field"] = "lines.L9.quantity"
    if bad == "supplier": correction["field"] = "supplier_id"
    if bad == "ambiguous": runtime.evidence[correction["evidence_id"]].confidence = "ambiguous"
    if bad == "conflicting":
        other = runtime.evidence[correction["evidence_id"]].model_copy(deep=True)
        other.id = "other-direct-reading"
        other.value = "100"
        runtime.evidence[other.id] = other
    with pytest.raises(ValueError):
        apply_findings(state["candidate"], finding, runtime)
    assert not runtime.history

@pytest.mark.parametrize("kind,limit", [("tool",12), ("model",8)])
def test_attempt_caps_including_failures(kind, limit):
    budget = Budget()
    for _ in range(limit): budget.attempt(kind)
    with pytest.raises(Terminal): budget.attempt(kind)
    assert budget.terminal

def test_deadline_and_no_reentry():
    budget = Budget(seconds=.02)
    with pytest.raises(Terminal): budget.bounded(lambda: time.sleep(.08))
    with pytest.raises(Terminal): budget.attempt("tool")

def test_spend_reservation_includes_failed_attempt():
    budget = Budget(allowance=Decimal("0.10"))
    budget.attempt("model", Decimal("0.08"))
    with pytest.raises(Terminal): budget.attempt("model", Decimal("0.08"))
    assert budget.models == 2
    assert budget.reserved == Decimal("0.08")

def test_page_no_progress(setup):
    runtime, _ = setup()
    req = interaction_examples("reading-conflict")[0]["tool_requests"][0]
    runtime.review(req)
    with pytest.raises(Terminal, match="no progress"): runtime.review(req)
    assert runtime.budget.tools == 2

def test_node_no_progress_and_terminal_finalize(setup):
    runtime, state = setup()
    nodes = Nodes(runtime, lambda *_: {"findings": {"note":"no evidence"}}, packet=state["packet"])
    state.update(nodes.validation(state))
    state.update(nodes.investigation(state))
    state.update(nodes.findings(state))
    assert nodes.policy(state) == "finalize"
    assert nodes.finalize(state)["recommendation"] == "ESCALATE"
    assert guarded_route(state, runtime, lambda _: "tools") == "finalize"

def test_missing_reading_stays_unresolved(setup):
    runtime, state = setup("missing-evidence")
    req = interaction_examples("missing-evidence")[0]["tool_requests"][0]
    evidence = runtime.review(req)
    assert evidence[0].confidence == "unavailable"
    correction = {"corrections":[{"field":"lines.L1.quantity", "value":"10", "evidence_id":evidence[0].id}]}
    with pytest.raises(ValueError): apply_findings(state["candidate"], correction, runtime)
    assert recommendation(validate(**state)) == "NEEDS_CLARIFICATION"

def test_model_parse_failure_is_terminal(setup):
    runtime, state = setup(client=ScriptedClient([{"recommendation":"READY_FOR_APPROVAL"}]))
    # Minimal test double only invokes prepared transport; learner code unchanged.
    nodes = Nodes(runtime, lambda s, r: r.ask("test", s).model_dump(mode="json"), packet=state["packet"])
    state.update(nodes.validation(state))
    state.update(nodes.investigation(state))
    assert nodes.finalize(state)["recommendation"] == "ESCALATE"
    assert runtime.budget.models == 1

def test_live_review_model_and_tool_attempts(setup):
    class FakeLive(ScriptedClient):
        live = True
        cost = Decimal(".02")
        def review(self, *_): raise RuntimeError("transport failed")
    runtime, _ = setup(client=FakeLive(), budget=Budget(allowance=Decimal(".05")))
    with pytest.raises(Terminal): runtime.review(interaction_examples("reading-conflict")[0]["tool_requests"][0])
    assert runtime.budget.tools == runtime.budget.models == 1
    assert runtime.budget.reserved == Decimal(".02")

def test_initial_extraction_shared_spend(monkeypatch):
    class FakeLive(ScriptedClient):
        live = True
        cost = Decimal(".02")
        def extract(self, case):
            raw = fixture(case).model_dump(mode="json")
            raw["source"] = "live-vlm"
            return raw
    result, remaining = extract("matching", FakeLive(), Decimal(".05"))
    assert result.source == "live-vlm"
    assert remaining == Decimal(".03")

def test_live_requires_explicit_configuration(monkeypatch):
    monkeypatch.delenv("WORKSHOP_MODE", raising=False)
    with pytest.raises(ValueError): LiveClient()

def test_wrong_page_hash_rejected(setup):
    class BadPage(ScriptedClient):
        def review(self, case, page):
            rows = super().review(case, page)
            rows[0]["page_ref"]["sha256"] = "0" * 64
            return rows
    runtime, _ = setup(client=BadPage())
    with pytest.raises(Terminal): runtime.review(interaction_examples("reading-conflict")[0]["tool_requests"][0])
    assert not runtime.evidence

def test_recursion_backstop_still_validates(setup):
    runtime, state = setup()
    nodes = Nodes(runtime, learner_agent.investigate, packet=state["packet"])
    graph = StateGraph(State)
    graph.add_node("loop", lambda _: {})
    graph.add_edge(START, "loop")
    graph.add_edge("loop", "loop")
    result = run(graph.compile(), state, nodes)
    assert result["recommendation"] == "ESCALATE"
    assert result["checks"]

def test_empty_checks_fail_closed():
    assert recommendation([]) == "NEEDS_CLARIFICATION"

@pytest.mark.parametrize("case", CASES)
def test_actual_page_render_and_hash(case):
    assert page_image(case, 1).startswith(b"\x89PNG")
    assert sha256(DATA / "invoices" / f"{case}.pdf") == fixture(case).invoice_sha256

@pytest.mark.parametrize("value", ["NaN", "Infinity", "-10", "0"])
def test_invalid_quantity(value):
    raw = fixture("matching").candidate.model_dump(mode="json")
    raw["lines"][0]["quantity"] = value
    with pytest.raises(ValueError): Invoice.model_validate(raw)

def test_overall_node_deadline(setup):
    runtime, state = setup(budget=Budget(seconds=.02))
    nodes = Nodes(runtime, lambda *_: time.sleep(.1), packet=state["packet"])
    state.update(nodes.validation(state))
    state.update(nodes.investigation(state))
    assert nodes.finalize(state)["recommendation"] == "ESCALATE"
    assert runtime.budget.terminal

def test_offline_cli_no_network_or_secret_export(setup, tmp_path, monkeypatch):
    import socket
    from workshop import cli
    def deny(*args, **kwargs):
        raise AssertionError("offline startup attempted network access")
    monkeypatch.setattr(socket.socket, "connect", deny)
    monkeypatch.setattr(cli, "STATE", tmp_path)
    monkeypatch.setattr(cli, "DB", tmp_path / "demo.sqlite")
    monkeypatch.setenv("WORKSHOP_MODE", "offline")
    monkeypatch.setenv("WORKSHOP_API_KEY", "SECRET-MUST-NOT-BE-EXPORTED")
    seed(cli.DB)
    cli.preflight()
    runtime, state = setup()
    nodes = Nodes(runtime, learner_agent.investigate, packet=state["packet"])
    result = run(learner_graph.build_graph(nodes), state, nodes)
    folder = cli.review("reading-conflict", result, runtime)
    exported = "".join(p.read_text() for p in folder.iterdir())
    assert "SECRET-MUST-NOT-BE-EXPORTED" not in exported
    assert "recommendation" in exported
    assert "human_decision" in exported
    assert "original" in exported

def test_bootstrap_failure_handoff_does_not_export_secrets(tmp_path, monkeypatch):
    import sys
    from workshop import cli
    monkeypatch.setattr(cli, "STATE", tmp_path)
    monkeypatch.setattr(cli, "DB", tmp_path / "absent.sqlite")
    monkeypatch.setattr(sys, "argv", ["workshop", "run", "--case", "reading-conflict"])
    monkeypatch.setenv("WORKSHOP_API_KEY", "SECRET-MUST-NOT-BE-EXPORTED")
    with pytest.raises(SystemExit) as error:
        cli.main()
    assert error.value.code == 1
    folder = tmp_path / "reading-conflict"
    report = json.loads((folder / "review.json").read_text())
    assert report["recommendation"] == "ESCALATE"
    assert "SECRET-MUST-NOT-BE-EXPORTED" not in "".join(p.read_text() for p in folder.iterdir())

# Serial prepared-node calls verify updates, not a completed learner graph.
def test_notebook_updates_are_detached_and_synchronized(setup):
    runtime, state = setup()
    nodes = Nodes(runtime, learner_agent.investigate, packet=state["packet"])
    state.update(nodes.validation(state))
    assert state["original_extraction"]["original"]["lines"][0]["quantity"] == "100"
    assert state["evidence"] == state["correction_history"] == []
    requests, findings = interaction_examples("reading-conflict")
    state["result"] = requests
    state.update(nodes.tools(state))
    assert state["evidence"][0]["value"] == "10"
    assert state["candidate"]["lines"][0]["quantity"] == "100"
    state["result"] = findings
    state.update(nodes.findings(state))
    assert state["candidate"]["lines"][0]["quantity"] == "10"
    assert state["correction_history"][0]["before"] == "100"
    assert state["original_extraction"]["original"]["lines"][0]["quantity"] == "100"
    state["evidence"][0]["value"] = "999"
    state["correction_history"][0]["after"] = "999"
    state["original_extraction"]["original"]["lines"][0]["quantity"] = "999"
    refreshed = nodes.validation(state)
    assert refreshed["evidence"][0]["value"] == "10"
    assert refreshed["correction_history"][0]["after"] == "10"
    assert refreshed["original_extraction"]["original"]["lines"][0]["quantity"] == "100"
    assert str(runtime.extraction.original.lines[0].quantity) == "100"


def test_state_observation_is_not_evidence_proof(setup):
    runtime, state = setup()
    nodes = Nodes(runtime, learner_agent.investigate, packet=state["packet"])
    state.update(nodes.validation(state))
    state["evidence"] = [{"id": "invented", "value": "10", "confidence": "clear"}]
    state["result"] = {"findings": {"corrections": [{"field":"lines.L1.quantity", "value":"10", "evidence_id":"invented"}]}}
    update = nodes.findings(state)
    assert update["evidence"] == []
    assert update["terminal"]
    assert runtime.history == []


def test_failed_tool_update_keeps_authoritative_notebook(setup):
    runtime, state = setup()
    nodes = Nodes(runtime, learner_agent.investigate, packet=state["packet"])
    state["result"] = {"tool_requests": [{"name":"review_pdf_page", "invoice_id":"matching", "page":1}]}
    update = nodes.tools(state)
    assert update["terminal"]
    assert update["evidence"] == []
    assert update["correction_history"] == []
    assert update["original_extraction"]["invoice_sha256"] == runtime.extraction.invoice_sha256


def test_prompt_uses_structured_authoritative_data_at_call_time(setup):
    class Capture(ScriptedClient):
        def investigation(self, messages):
            self.messages = messages
            return {"handoff": "test only"}
    client = Capture()
    runtime, state = setup(client=client)
    state["checks"] = validate(**state)
    state["evidence"] = [{"id":"forged-state-observation"}]
    runtime.ask("test instruction", state)
    payload = json.loads(client.messages[1]["content"])
    assert payload["evidence"] == []
    assert payload["original_extraction"]["original"]["lines"][0]["quantity"] == "100"
    assert payload["correction_history"] == []
    assert "test instruction" in client.messages[0]["content"]
    assert "messages" not in state


def test_preflight_does_not_import_learner_behavior(tmp_path, monkeypatch):
    from workshop import cli
    def unavailable(*_):
        raise AssertionError("preflight must not run learner TODOs")
    monkeypatch.setattr(learner_graph, "build_graph", unavailable)
    monkeypatch.setattr(learner_agent, "investigate", unavailable)
    monkeypatch.setattr(cli, "DB", tmp_path / "demo.sqlite")
    monkeypatch.setenv("WORKSHOP_MODE", "offline")
    seed(cli.DB)
    cli.preflight()


def test_progress_supported_reading_with_manual_prepared_updates(setup):
    from workshop.progress import assess
    runtime, state = setup()
    nodes = Nodes(runtime, learner_agent.investigate, packet=state["packet"])
    state.update(nodes.validation(state))
    requests, findings = interaction_examples("reading-conflict")
    state["result"] = requests
    state.update(nodes.tools(state))
    state["result"] = findings
    state.update(nodes.findings(state))
    state.update(nodes.validation(state))
    state.update(nodes.finalize(state))
    assert assess("reading-conflict", state, runtime)[0] == "SUPPORTED_OUTCOME"


def test_progress_requires_accepted_provenance_and_revalidation(setup):
    from workshop.progress import assess
    runtime, state = setup()
    nodes = Nodes(runtime, learner_agent.investigate, packet=state["packet"])
    state.update(nodes.validation(state))
    # A guessed value and a state-only citation are not accepted audit records.
    state["candidate"]["lines"][0]["quantity"] = "10"
    state["correction_history"] = [{"field":"lines.L1.quantity", "before":"100", "after":"10", "evidence_id":"invented"}]
    state.update(nodes.finalize(state))
    assert assess("reading-conflict", state, runtime)[0] == "REGRESSION"


def test_progress_missing_handoff_manual_prepared_updates(setup):
    from workshop.progress import assess
    runtime, state = setup("missing-evidence")
    nodes = Nodes(runtime, learner_agent.investigate, packet=state["packet"])
    state.update(nodes.validation(state))
    request, handoff = interaction_examples("missing-evidence")
    state["result"] = request
    state.update(nodes.tools(state))
    state["handoff"] = handoff["handoff"]
    state.update(nodes.finalize(state))
    assert assess("missing-evidence", state, runtime)[0] == "SUPPORTED_OUTCOME"


@pytest.mark.parametrize("case", CASES)
def test_progress_current_learner_graph_before_or_after_edits(setup, tmp_path, case):
    from workshop.progress import check_progress
    db = tmp_path / "progress.sqlite"
    seed(db)
    label, detail, result, runtime = check_progress(case, db)
    assert label in ("NOT_IMPLEMENTED_YET", "SUPPORTED_OUTCOME"), detail
    assert result["evidence"] == runtime.notebook()["evidence"]
    assert result["correction_history"] == runtime.notebook()["correction_history"]


def test_progress_cli_is_always_offline(tmp_path, monkeypatch, capsys):
    import sys
    import socket
    from workshop import cli
    def deny(*_args, **_kwargs):
        raise AssertionError("progress must not use network/live client")
    monkeypatch.setattr(socket.socket, "connect", deny)
    monkeypatch.setattr(cli, "LiveClient", deny)
    monkeypatch.setenv("WORKSHOP_MODE", "live")
    monkeypatch.setattr(cli, "STATE", tmp_path)
    monkeypatch.setattr(cli, "DB", tmp_path / "progress.sqlite")
    monkeypatch.setattr(sys, "argv", ["workshop", "check", "--case", "reading-conflict"])
    seed(cli.DB)
    cli.main()
    output = capsys.readouterr().out
    assert "Offline fixed responses" in output
    assert any(label in output for label in ("NOT_IMPLEMENTED_YET", "SUPPORTED_OUTCOME"))


def test_progress_cli_regression_exits_one(tmp_path, monkeypatch):
    import sys
    from workshop import cli
    from workshop import progress
    db = tmp_path / "progress.sqlite"
    seed(db)
    label, detail, result, runtime = progress.check_progress("matching", db)
    monkeypatch.setattr(progress, "check_progress", lambda *_: ("REGRESSION", "test failure", result, runtime))
    monkeypatch.setattr(cli, "STATE", tmp_path)
    monkeypatch.setattr(cli, "DB", db)
    monkeypatch.setattr(sys, "argv", ["workshop", "check"])
    with pytest.raises(SystemExit) as error:
        cli.main()
    assert error.value.code == 1


def test_terminal_failure_preserves_last_completed_case_notebook(setup):
    runtime, state = setup()
    request, findings = interaction_examples("reading-conflict")
    runtime.review(request["tool_requests"][0])
    state["result"] = findings
    # A findings node followed by a deliberately broken loop, not a solution graph.
    nodes = Nodes(runtime, learner_agent.investigate, packet=state["packet"])
    graph = StateGraph(State)
    graph.add_node("test_proposal", lambda _: {"result": findings})
    graph.add_node("accepted_findings", nodes.findings)
    graph.add_node("broken_loop", lambda _: {})
    graph.add_edge(START, "test_proposal")
    graph.add_edge("test_proposal", "accepted_findings")
    graph.add_edge("accepted_findings", "broken_loop")
    graph.add_edge("broken_loop", "broken_loop")
    result = run(graph.compile(), state, nodes)
    assert result["recommendation"] == "ESCALATE"
    assert result["candidate"]["lines"][0]["quantity"] == "10"
    assert result["correction_history"][0]["after"] == "10"
    assert result["original_extraction"]["original"]["lines"][0]["quantity"] == "100"


def test_unfinished_learner_tool_hands_off_without_fixture_substitution(setup):
    from workshop.progress import assess
    from unittest.mock import Mock
    runtime, state = setup()
    nodes = Nodes(runtime, learner_agent.investigate, Mock(return_value=None), packet=state["packet"])
    state.update(nodes.validation(state))
    state["result"] = interaction_examples("reading-conflict")[0]
    state.update(nodes.tools(state))
    assert "PDF review tool not implemented:" in state["handoff"]
    assert runtime.budget.terminal is None
    assert runtime.budget.tools == 1
    assert runtime.budget.models == 0
    assert state["evidence"] == []
    assert nodes.after_tools(state) == "finalize"
    state.update(nodes.finalize(state))
    assert assess("reading-conflict", state, runtime)[0] == "NOT_IMPLEMENTED_YET"


@pytest.mark.parametrize("mode", ["changed_reading", "invented_observation", "redirect", "repeated_read"])
def test_learner_tool_cannot_forge_or_redirect_reader_output(setup, mode):
    runtime, state = setup()
    request = interaction_examples("reading-conflict")[0]["tool_requests"][0]
    def invalid_tool(invoice_id, page, read_page):
        if mode == "invented_observation":
            return {"observations": []}  # Did not actually call the reader.
        if mode == "redirect":
            read_page("matching", page)
        rows = read_page(invoice_id, page)
        if mode == "repeated_read":
            read_page(invoice_id, page)
        rows[0]["value"] = "999"
        return {"observations": rows}
    with pytest.raises(Terminal):
        runtime.review(request, invalid_tool)
    assert runtime.evidence == {}
    assert runtime.budget.terminal
    assert runtime.budget.tools == (2 if mode == "repeated_read" else 1)


def test_learner_tool_callback_runs_inside_live_model_and_tool_bounds(setup):
    from unittest.mock import Mock
    class FakeLive(ScriptedClient):
        live = True
        cost = Decimal(".02")
        def review(self, case, page):
            rows = super().review(case, page)
            for row in rows:
                row["origin"] = "live-page-review"
            return rows
    runtime, state = setup(client=FakeLive(), budget=Budget(allowance=Decimal(".05")))
    # Transport callback test double only; no investigation node/solution graph.
    envelope = {}
    def capture_reader(invoice_id, page, read_page):
        envelope["observations"] = read_page(invoice_id, page)
        return envelope
    tool = Mock(side_effect=capture_reader)
    request = interaction_examples("reading-conflict")[0]["tool_requests"][0]
    evidence = runtime.review(request, tool)
    tool.assert_called_once()
    assert evidence[0].value == "10"
    assert evidence[0].origin == "live-page-review"
    assert runtime.budget.models == runtime.budget.tools == 1
    assert runtime.budget.reserved == Decimal(".02")


def test_prepared_routing_and_unconnected_graph_do_not_complete_wiring(setup):
    from workshop.graph import prepared_graph
    runtime, state = setup()
    nodes = Nodes(runtime, learner_agent.investigate, learner_tools.review_pdf_page, packet=state["packet"])
    graph = prepared_graph(nodes)
    assert set(graph.nodes) == {"validate", "investigate", "tools", "findings", "finalize"}
    assert not graph.edges
    assert not graph.branches
    assert nodes.route_investigation({"result":{"tool_requests":[{}]}}) == "tools"
    assert nodes.route_investigation({"result":{"tool_requests":[]}}) == "findings"
    assert nodes.route_investigation({"handoff":"missing evidence"}) == "finalize"


def test_failed_read_cannot_be_retried_inside_learner_tool(setup):
    class FailedReader(ScriptedClient):
        live = True
        cost = Decimal(".02")
        calls = 0
        def review(self, *_):
            self.calls += 1
            raise RuntimeError("prepared transport failure")
    client = FailedReader()
    runtime, state = setup(client=client, budget=Budget(allowance=Decimal(".05")))
    def retrying_tool(invoice_id, page, read_page):
        try:
            read_page(invoice_id, page)
        except RuntimeError:
            read_page(invoice_id, page)
    request = interaction_examples("reading-conflict")[0]["tool_requests"][0]
    with pytest.raises(Terminal):
        runtime.review(request, retrying_tool)
    assert client.calls == 1
    assert runtime.budget.tools == 2
    assert runtime.budget.models == 1
    assert runtime.budget.terminal


def test_private_business_records_still_drive_prepared_validation(setup):
    runtime, state = setup("matching")
    packet = copy.deepcopy(state["packet"])
    nodes = Nodes(runtime, learner_agent.investigate, packet=packet)
    assert nodes.finalize(state)["recommendation"] == "READY_FOR_APPROVAL"
    packet["suppliers"][0]["bank_account"] = "PRIVATE_BANK_SENTINEL"
    blocked = Nodes(runtime, learner_agent.investigate, packet=packet)
    assert blocked.finalize(state)["recommendation"] == "ESCALATE"
    packet["suppliers"][0]["bank_account"] = state["candidate"]["bank_account"]
    packet["coverage"] = [r for r in packet["coverage"] if r["dataset"] != "receipts"]
    unresolved = Nodes(runtime, learner_agent.investigate, packet=packet)
    packet["coverage"].clear()  # Retained copy cannot be changed by caller mutation.
    assert unresolved.finalize(state)["recommendation"] == "NEEDS_CLARIFICATION"


def test_investigation_projection_and_client_do_not_expose_business_data(setup):
    from workshop.views import InvestigationInput
    secret = "PRIVATE_BUSINESS_SENTINEL_987"
    class Capture(ScriptedClient):
        def investigation(self, messages):
            self.messages = messages
            return {"handoff": "test only"}
    client = Capture()
    runtime, state = setup(client=client)
    for rows in state["packet"].values():
        for row in rows:
            row["private_note"] = secret
    # Put sentinels in actual source fields too, not just metadata extras.
    state["packet"]["suppliers"][0].update(name=secret, bank_account=secret)
    state["packet"]["purchase_orders"][0]["currency"] = secret
    state["packet"]["po_lines"][0]["description"] = secret
    state["packet"]["receipts"][0]["uom"] = secret
    state["packet"]["invoice_history"][0]["invoice_number"] = secret
    for row in state["packet"]["coverage"]:
        row["description"] = secret
    captured = {}
    def inspect_only(view, agent_client):
        captured.update(copy.deepcopy(view))
        assert set(view) == set(InvestigationInput.__annotations__)
        assert set(name for name in dir(agent_client) if not name.startswith("_")) == {"ask"}
        for forbidden in ("packet", "client", "events", "budget", "history", "extraction", "notebook", "review"):
            assert not hasattr(agent_client, forbidden)
        # Reformatting must not leak injected extras, prior results or check nesting.
        contaminated = {**view, "packet": state["packet"], "result": {"private": secret}, "original_extraction": {"private": secret}}
        contaminated["checks"] = [
            {"id":"bank", "status":"pass", "detail":secret, "record":state["packet"]},
            {"id":"lines.L1.quantity", "status":"unresolved", "detail":secret, "expected":secret, "evidence_ids":[secret]},
        ]
        return agent_client.ask("test", contaminated).model_dump(mode="json")
    nodes = Nodes(runtime, inspect_only, packet=state["packet"])
    state.update(nodes.validation(state))
    state["checks"].append({"id":"bank", "status":"pass", "detail":secret, "record":state["packet"]})
    state["checks"][0].update(detail=secret, expected=secret, nested={"record":secret})
    state["result"] = {"private": secret}
    state["original_extraction"] = {"private": secret}
    nodes.investigation(state)
    assert secret not in json.dumps(captured)
    assert secret not in json.dumps(client.messages)
    payload = json.loads(client.messages[1]["content"])
    assert "packet" not in payload and "proposed_result" not in payload and "result" not in payload
    assert all(c["status"] != "pass" for c in payload["checks"])
    assert all(set(c) == {"id", "status"} for c in payload["checks"])
    assert payload["questions"][0]["question"] == "Recheck the printed quantity for invoice line L1 on page 1."


def test_graph_snapshots_drop_private_packet_and_full_check_internals(setup):
    secret = "PRIVATE_CHECK_SENTINEL_654"
    runtime, state = setup()
    nodes = Nodes(runtime, learner_agent.investigate, packet=state["packet"])
    original_checks = nodes.checks
    def detailed_checks(candidate):
        checks = original_checks(candidate)
        for check in checks:
            check.update(detail=secret, private_record={"secret":secret}, evidence_ids=[secret])
        return checks
    nodes.checks = detailed_checks
    snapshots = []
    graph = learner_graph.build_graph(nodes)
    class RecordingGraph:
        def stream(self, *args, **kwargs):
            for update in graph.stream(*args, **kwargs):
                snapshots.append(copy.deepcopy(update))
                yield update
    state["packet"]["suppliers"][0]["private_note"] = secret
    state["checks"] = [{"id":"bank", "status":"pass", "detail":secret}]
    state["result"] = {"private":secret}
    result = run(RecordingGraph(), state, nodes)
    assert result["recommendation"] == "NEEDS_CLARIFICATION"
    assert "packet" not in State.__annotations__
    assert all("packet" not in snapshot for snapshot in snapshots)
    assert secret not in json.dumps(snapshots)
    assert secret not in json.dumps(result)
    assert secret in json.dumps(runtime.events)  # Prepared human audit only; not handed to agent.


def test_accepted_page_evidence_and_history_remain_in_permitted_view(setup):
    from workshop.views import investigation_view
    runtime, state = setup()
    request, findings = interaction_examples("reading-conflict")
    runtime.review(request["tool_requests"][0])
    findings["findings"]["note"] = "PRIVATE_AUDIT_NOTE_SENTINEL"
    nodes = Nodes(runtime, learner_agent.investigate, packet=state["packet"])
    state["result"] = findings
    state.update(nodes.findings(state))
    state.update(nodes.validation(state))
    view = investigation_view(state, runtime.notebook())
    assert view["candidate"]["lines"][0]["quantity"] == "10"
    assert view["original_extraction"]["original"]["lines"][0]["quantity"] == "100"
    assert view["evidence"][0]["value"] == "10"
    assert view["correction_history"][0]["before"] == "100"
    assert "PRIVATE_AUDIT_NOTE_SENTINEL" not in json.dumps(view)
    assert "reason" not in view["correction_history"][0]
    assert view["checks"] == view["questions"] == []
