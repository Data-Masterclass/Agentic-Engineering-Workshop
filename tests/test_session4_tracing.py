"""Real span hierarchy and approval lifecycle, using no collector or model calls."""
import builtins
import json
import socket

import pytest

from workshop import telemetry
from workshop.session4 import runner


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setattr(socket.socket, "connect", lambda *_: pytest.fail("network forbidden"))
    monkeypatch.setattr(runner, "LiveTransport", lambda *_a, **_k: pytest.fail("live client forbidden"))
    monkeypatch.delenv("WORKSHOP_TRACING", raising=False)


@pytest.fixture
def recorded(monkeypatch):
    pytest.importorskip("opentelemetry.sdk")
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setattr(telemetry, "_providers", {"workshop-session4": provider})
    monkeypatch.setenv("WORKSHOP_TRACING", "phoenix")
    yield exporter
    provider.shutdown()


def children(spans, parent):
    return sorted((span for span in spans if span.parent and span.parent.span_id == parent.context.span_id), key=lambda span: span.start_time)


def test_four_case_hierarchy_and_real_span_containment(recorded, tmp_path):
    rows = runner.experiment(tmp_path / "all", input_fn=lambda _: "approve rehearsal")
    spans = recorded.get_finished_spans()
    roots = [span for span in spans if span.parent is None]
    assert len(roots) == 4 and len({span.context.trace_id for span in roots}) == 4
    for root in roots:
        scenario = json.loads(root.attributes["input.value"])["scenario"]
        assert json.loads(root.attributes["input.value"])["mode"] == "scripted"
        row = next(row for row in rows if row["scenario"] == scenario)
        trace = [span for span in spans if span.context.trace_id == root.context.trace_id]
        by_id = {span.context.span_id: span for span in trace}
        direct = children(trace, root)
        lead, = [span for span in direct if span.name == "Lead investigator"]
        assert lead.attributes["openinference.span.kind"] == "AGENT"
        assert direct[-1].name == "Finalize recommendation"
        for span in trace:
            assert span.status.status_code.name != "ERROR"
            if span.parent:
                parent = by_id[span.parent.span_id]
                assert parent.start_time <= span.start_time <= span.end_time <= parent.end_time
        assert any(span.name == "Invoice investigation" for span in children(trace, lead))
        specialists = [span for span in trace if span.name == "Correspondence specialist"]
        assert len(specialists) == int(scenario in ("supplier-request", "request-pending"))
        for specialist in specialists:
            assert specialist.parent.span_id == lead.context.span_id
            assert specialist.attributes["openinference.span.kind"] == "AGENT"
            turns = children(trace, specialist)
            assert [span.name for span in turns] == ["Correspondence turn", "Correspondence turn"]
            first, last = turns
            assert [span.name for span in children(trace, first)] == ["Specialist request", "read_supplier_correspondence"]
            request, tool = children(trace, first)
            assert request.end_time <= tool.start_time
            assert tool.attributes["openinference.span.kind"] == "TOOL"
            assert json.loads(tool.attributes["output.value"])["coverage"] == "selected"
            assert [span.name for span in children(trace, last)] == ["Specialist request"]
        reviews = [span for span in direct if span.name == "Human draft review"]
        assert len(reviews) == int(scenario == "supplier-request")
        if reviews:
            review, = reviews
            assert lead.end_time <= review.start_time
            assert [span.name for span in children(trace, review)] == ["Apply draft approval"]
            assert json.loads(review.attributes["output.value"])["draft_review"] == "approved"
        assert sum(span.attributes["openinference.span.kind"] == "LLM" for span in trace) == row["models"]
        assert sum(span.attributes["openinference.span.kind"] == "TOOL" for span in trace) == row["tools"]


@pytest.mark.parametrize("decision", ["reject", "eof"])
def test_rejected_or_pending_review_is_not_an_error_or_repeated_model_work(recorded, tmp_path, decision):
    def respond(_):
        if decision == "eof":
            raise EOFError()
        return "reject not appropriate"
    rows = runner.experiment(tmp_path / decision, scenario="supplier-request", input_fn=respond)
    spans = recorded.get_finished_spans()
    assert rows[0]["draft_review"] == ("rejected" if decision == "reject" else "pending_review")
    review, = [span for span in spans if span.name == "Human draft review"]
    assert all(span.end_time <= review.start_time for span in spans if span.attributes["openinference.span.kind"] == "LLM")
    assert sum(span.name == "Apply draft approval" for span in spans) == int(decision == "reject")
    assert all(span.status.status_code.name != "ERROR" for span in spans)


def test_lookup_failure_ends_specialist_and_does_not_parent_the_next_case(recorded, tmp_path, monkeypatch):
    original = runner.CorrespondenceLookup.execute
    attempts = 0
    def fail_once(self, arguments):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise ValueError("private-lookup-error-payload")
        return original(self, arguments)
    monkeypatch.setattr(runner.CorrespondenceLookup, "execute", fail_once)
    rows = runner.experiment(tmp_path / "failure", input_fn=lambda _: "approve")
    spans = recorded.get_finished_spans()
    roots = [span for span in spans if span.parent is None]
    assert len(roots) == 4 and rows[0]["followup_terminal"]
    for root in roots:
        scenario = json.loads(root.attributes["input.value"])["scenario"]
        assert (root.status.status_code.name == "ERROR") == (scenario == "supplier-request")
        trace = [span for span in spans if span.context.trace_id == root.context.trace_id]
        assert all(span.end_time <= root.end_time for span in trace)
    assert "private-lookup-error-payload" not in str([(dict(span.attributes), span.status.description) for span in spans])


def test_trace_content_omits_private_reasoning(recorded, tmp_path, monkeypatch):
    original = runner.ScriptedTransport.response
    def with_reasoning(self, items, **kwargs):
        output = original(self, items, **kwargs)
        if kwargs.get("instructions") == runner.SPECIALIST_PROMPT and any(item["type"] == "function_call" for item in output):
            output.insert(0, {"type": "reasoning", "encrypted_content": "PRIVATE_REASONING_MARKER"})
        return output
    monkeypatch.setattr(runner.ScriptedTransport, "response", with_reasoning)
    runner.experiment(tmp_path / "private", scenario="supplier-request", input_fn=lambda _: "approve")
    spans = recorded.get_finished_spans()
    assert "PRIVATE_REASONING_MARKER" not in str([dict(span.attributes) for span in spans])
    assert any(span.name == "Specialist request" and "function_call_output" in span.attributes["input.value"] for span in spans)


def test_tracing_preserves_reports_and_counts(recorded, tmp_path, monkeypatch):
    traced = tmp_path / "traced"
    plain = tmp_path / "plain"
    runner.experiment(traced, input_fn=lambda _: "approve")
    monkeypatch.delenv("WORKSHOP_TRACING")
    runner.experiment(plain, input_fn=lambda _: "approve")
    def stable(value):
        if isinstance(value, dict):
            return {key: stable(item) for key, item in value.items() if key != "elapsed_seconds"}
        if isinstance(value, list):
            return [stable(item) for item in value]
        return value
    for path in traced.rglob("*.json"):
        assert stable(json.loads(path.read_text())) == stable(json.loads((plain/path.relative_to(traced)).read_text()))
    for path in traced.rglob("*.jsonl"):
        assert path.read_bytes() == (plain/path.relative_to(traced)).read_bytes()


def test_disabled_or_broken_tracing_never_changes_the_flow(tmp_path, monkeypatch):
    original = builtins.__import__
    def no_optional(name, *args, **kwargs):
        if name.startswith("opentelemetry"):
            pytest.fail("disabled tracing imported optional dependencies")
        return original(name, *args, **kwargs)
    with monkeypatch.context() as scoped:
        scoped.setattr(builtins, "__import__", no_optional)
        rows = runner.experiment(tmp_path / "disabled", input_fn=lambda _: "approve")
        assert len(rows) == 4
    class Broken:
        def start_span(self, *_a, **_kw):
            raise RuntimeError("private-collector-error")
        start_as_current_span = start_span
    monkeypatch.setattr(telemetry, "_get_tracer", lambda: Broken())
    monkeypatch.setattr(telemetry, "_warned", False)
    with pytest.warns(RuntimeWarning, match="workflow continues"):
        rows = runner.experiment(tmp_path / "broken", input_fn=lambda _: "approve")
    assert [row["followup_action"] for row in rows] == ["recommend_email", "await_existing_request", "internal_handoff", "human_review_only"]
