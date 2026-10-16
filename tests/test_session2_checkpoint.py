import copy
import json
from decimal import Decimal
import pytest
import sqlite3

from workshop.session2.checkpoint import ScriptedTransport, run
from workshop.session2.data import case, digest
from workshop.session2.policy import validate
from workshop.session2.runner import actions, experiment, score
from workshop.session2.tools import EvidenceTools, normalized_number
from workshop.session2.store import Store


def test_order_discovery_preserves_original_and_unknown_coverage():
    packet = case("order-gap")
    original = copy.deepcopy(packet)
    result = run(packet, ScriptedTransport(actions("order-gap")))
    assert result["terminal"] is None
    assert result["recommendation"] == "NEEDS_CLARIFICATION"
    assert result["association"]["order_id"] == "PO-7"
    assert result["original"]["po_id"] is None
    assert result["candidate"] == result["original"]
    assert packet == original
    checks = {c["id"]: c["status"] for c in result["checks"]}
    assert checks["order_terms"] == checks["receipt_support"] == "pass"
    assert checks["mandatory_coverage"] == checks["posted_copy"] == "unresolved"
    assert checks["source_quantity"] == "pass"
    assert result["attempts"] == {"models": 7, "tools": 6}


def test_posted_match_can_stop_without_prescribed_full_tool_sequence():
    result = run(case("posted-copy"), ScriptedTransport(actions("posted-copy")))
    assert result["recommendation"] == "ESCALATE"
    assert result["attempts"] == {"models": 1, "tools": 1}
    assert result["evidence"][0]["records"][0]["invoice_number"] == "INV-204"
    assert result["original"]["invoice_number"] == "INV / 204"
    assert result["terminal"] is None


@pytest.mark.parametrize("name,arguments", [
    ("get_supplier", {"supplier_id": "OTHER"}),
    ("get_purchase_order", {"order_id": "OTHER"}),
    ("get_receipts", {"order_id": "OTHER"}),
    ("get_invoice_history", {"supplier_id": "SUP-1", "invoice_number": "OTHER"}),
    ("review_pdf_page", {"page": True}),
    ("review_pdf_page", {"page": 2}),
    ("get_supplier", {"supplier_id": "SUP-1", "sql": "SELECT *"}),
    ("write_payment", {}),
])
def test_tool_rejects_invalid_arguments_and_scope(name, arguments):
    tools = EvidenceTools(case("order-gap"))
    with pytest.raises(ValueError):
        tools.execute(name, arguments)
    assert not tools.evidence


def test_returned_evidence_cannot_be_modified_through_detached_tool_result():
    tools = EvidenceTools(case("order-gap"))
    result = tools.execute("get_supplier", {"supplier_id": "SUP-1"})
    result["records"][0]["bank_account"] = "tampered"
    assert tools.evidence[0]["records"][0]["bank_account"] == "DE-SYNTHETIC-001"
    tools.evidence[0]["records"][0]["bank_account"] = "tampered"
    with pytest.raises(ValueError, match="changed"):
        validate(case("order-gap")["invoice"], tools.evidence)


def test_duplicate_and_disabled_tools_stop_investigation_without_retry():
    request = {"name": "get_supplier", "arguments": {"supplier_id": "SUP-1"}}
    client = ScriptedTransport([request, request])
    result = run(case("order-gap"), client)
    assert result["terminal"] is not None
    assert result["attempts"] == {"models": 2, "tools": 2}
    assert len(result["evidence"]) == 1
    result = run(case("order-gap"), ScriptedTransport([request]), enabled_tools=[])
    assert result["terminal"] is not None
    assert not result["evidence"]


def test_budget_reserves_before_live_call_and_reports_unknown_actual_cost():
    class FakePaid(ScriptedTransport):
        live = True
        cost = Decimal("0.05")
    client = FakePaid(actions("order-gap"))
    result = run(case("order-gap"), client, allowance=Decimal("0.05"))
    assert result["terminal"] is not None
    assert client.count == 1
    assert result["reserved_usd"] == "0.05"
    assert result["actual_cost_usd"] is None


def test_no_private_packet_or_labels_in_investigation_context_and_actual_continuation():
    class Inspect(ScriptedTransport):
        def response(self, items, **kwargs):
            if self.count == 0:
                context = json.loads(items[0]["content"])
                assert set(context) == {"invoice", "questions", "result_schema"}
                assert "records" not in context
            else:
                assert any(i.get("type") == "function_call_output" for i in items)
            return super().response(items, **kwargs)
    result = run(case("order-gap"), Inspect(actions("order-gap")))
    assert result["terminal"] is None


def test_model_cannot_return_approval_or_unsupported_corrections():
    for answer in ({"recommendation": "READY_FOR_APPROVAL"}, {"note": "fix", "handoff": None, "corrections": [{"quantity": 10}]}):
        result = run(case("order-gap"), ScriptedTransport([answer]))
        assert result["terminal"] is not None
        assert result["candidate"] == result["original"]
        assert result["corrections"] == []


def test_normalization_is_narrow_and_requires_corroboration():
    assert normalized_number("INV / 204") == normalized_number("INV-204")
    assert normalized_number("inv-204") != normalized_number("INV-204")
    packet = case("posted-copy")
    packet["records"]["history"][0]["net"] = "200.00"
    packet["source_hash"] = digest(packet["records"])
    result = run(packet, ScriptedTransport(actions("posted-copy")))
    assert result["recommendation"] == "NEEDS_CLARIFICATION"


def test_four_run_experiment_preserves_distinct_reports_and_labels_post_execution(tmp_path):
    out = tmp_path / "experiment"
    labels = {"order-gap": {"recommendation": "NEEDS_CLARIFICATION", "checks": {"order_terms": "pass"}, "evidence_any_of": [["get_purchase_order"]]}, "posted-copy": {"recommendation": "ESCALATE", "evidence_any_of": [["get_invoice_history"]]}}
    rows = experiment(out, [{"id": "a", "model": "alias-a"}, {"id": "b", "model": "alias-b"}], labels=labels)
    assert len(rows) == 4
    assert all(row["evaluation_passed"] for row in rows)
    assert len(list(out.glob("*/*/run-1/review.json"))) == 4
    assert len(list(out.glob("*/*/run-1/trace.jsonl"))) == 4
    assert (out / "comparison.csv").is_file()
    configuration = json.loads((out / "configuration.json").read_text())
    assert len(configuration["implementation_sha256"]) == 64
    assert configuration["code_dirty"] in (True, False)
    assert all(row["implementation_sha256"] == configuration["implementation_sha256"] for row in rows)
    assert [row["tools"] for row in rows] == [6, 6, 1, 1]
    assert all(len(row["tool_schema_sha256"]) == 64 for row in rows)
    assert all(row["mode"] == "scripted-wiring-only" and row["actual_cost_usd"] == "0" for row in rows)
    with pytest.raises(FileExistsError):
        experiment(out, [{"id": "a", "model": "a"}, {"id": "b", "model": "b"}])


def test_setup_failure_is_a_visible_unknown_cost_row(tmp_path, monkeypatch):
    import workshop.session2.runner as module
    def fail(*args):
        raise RuntimeError("secret must never be copied")
    monkeypatch.setattr(module, "_client", fail)
    rows = experiment(tmp_path / "failure", [{"id": "a", "model": "a"}, {"id": "b", "model": "b"}], mode="live")
    assert len(rows) == 4
    assert all(row["terminal"] == "setup failed: RuntimeError" for row in rows)
    assert all(row["actual_cost_usd"] is None for row in rows)


def test_private_evaluation_accepts_alternative_evidence_paths():
    result = run(case("posted-copy"), ScriptedTransport(actions("posted-copy")))
    outcome = score(result, {"recommendation": "ESCALATE", "evidence_any_of": [["get_invoice_history", "review_pdf_page"]]})
    assert outcome["passed"]


def test_ambiguous_supplier_is_unresolved_not_confirmed_mismatch():
    packet = case("order-gap")
    packet["records"]["suppliers"].append({**packet["records"]["suppliers"][0], "bank_account": "OTHER"})
    packet["source_hash"] = digest(packet["records"])
    result = run(packet, ScriptedTransport(actions("order-gap")))
    assert next(c for c in result["checks"] if c["id"] == "supplier_bank")["status"] == "unresolved"
    assert result["recommendation"] == "NEEDS_CLARIFICATION"


@pytest.mark.parametrize("reasoning,status", [(None, "in_progress"), ({"encrypted_content": True}, "completed"), ({"encrypted_content": ""}, "completed")])
def test_incomplete_calls_and_invalid_reasoning_are_rejected(reasoning, status):
    class Invalid(ScriptedTransport):
        def response(self, items, **kwargs):
            output = [{"type": "function_call", "name": "get_supplier", "call_id": "x", "status": status, "arguments": '{"supplier_id":"SUP-1"}'}]
            if reasoning is not None:
                output.insert(0, {"type": "reasoning", **reasoning})
            return output
    result = run(case("order-gap"), Invalid([]))
    assert result["terminal"] is not None
    assert not result["evidence"]


def test_shared_model_limit_stops_even_distinct_equivalent_queries():
    queries = [{"name": "get_invoice_history", "arguments": {"supplier_id": "SUP-1", "invoice_number": "INV" + " " * i + "204"}} for i in range(10)]
    client = ScriptedTransport(queries)
    result = run(case("order-gap"), client)
    assert client.count == 8
    assert result["attempts"] == {"models": 8, "tools": 8}
    assert result["terminal"] is not None


def test_receipts_require_accepted_state_and_no_ea_conversion():
    packet = case("order-gap")
    packet["records"]["receipts"][0]["uom"] = "EA"
    packet["source_hash"] = digest(packet["records"])
    result = run(packet, ScriptedTransport(actions("order-gap")))
    assert next(c for c in result["checks"] if c["id"] == "receipt_support")["status"] == "unresolved"


def test_unverified_source_fixture_is_rejected():
    packet = case("order-gap")
    packet["records"]["suppliers"][0]["bank_account"] = "tampered"
    with pytest.raises(ValueError, match="source hash"):
        run(packet, ScriptedTransport([]))


def test_sqlite_source_is_read_only_scoped_and_parameterized():
    store = Store(case("order-gap"))
    assert store.select("orders", buyer_id="OTHER") == []
    assert store.select("orders", record_id="PO-7' OR 1=1 --") == []
    assert len(store.select("orders", record_id="PO-7")) == 1
    with pytest.raises(ValueError, match="predicate"):
        store.select("orders", **{"record_id OR 1=1": "PO-7"})
    with pytest.raises(sqlite3.OperationalError, match="readonly"):
        store._db.execute("DELETE FROM records")
    store.close()


def test_scripted_experiment_from_symlinked_checkout(tmp_path, monkeypatch):
    from pathlib import Path
    from workshop.session2 import runner
    real = Path(runner.__file__).resolve()
    alias = tmp_path / "checkout-alias"
    alias.symlink_to(real.parents[3], target_is_directory=True)
    monkeypatch.setattr(runner, "__file__", str(alias / real.relative_to(real.parents[3])))
    variants = [{"id": "baseline", "model": "offline-example"},
                {"id": "comparison", "model": "offline-example"}]
    rows = runner.experiment(tmp_path / "comparison", variants, mode="scripted")
    assert len(rows) == 4 and all(row["terminal"] is None for row in rows)
    assert len({row["implementation_sha256"] for row in rows}) == 1
