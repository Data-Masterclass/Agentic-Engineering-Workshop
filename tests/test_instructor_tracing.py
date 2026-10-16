"""Instructor telemetry is optional, local, content-bounded and behaviour-neutral."""
import builtins
import json
import socket

import pytest

from workshop import telemetry
from workshop.session2 import checkpoint, runner
from workshop.session2.data import case
from workshop.session3.core import bundle_contents, demo


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setattr(socket.socket, "connect", lambda *_: pytest.fail("network forbidden"))
    monkeypatch.setattr(runner, "LiveTransport", lambda *_a, **_k: pytest.fail("live client forbidden"))
    monkeypatch.delenv("WORKSHOP_TRACING", raising=False)


@pytest.fixture
def recorded(monkeypatch):
    pytest.importorskip("opentelemetry.sdk")
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
    exporter = InMemorySpanExporter()
    provider = TracerProvider(resource=Resource({"service.name": "offline-test"}))
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setattr(telemetry, "_provider", provider)
    monkeypatch.setenv("WORKSHOP_TRACING", "phoenix")
    yield exporter
    provider.shutdown()


def test_disabled_tracing_needs_no_optional_imports(monkeypatch):
    original = builtins.__import__
    def guarded(name, *args, **kwargs):
        if name.startswith("opentelemetry"):
            pytest.fail("disabled tracing imported optional package")
        return original(name, *args, **kwargs)
    monkeypatch.setattr(builtins, "__import__", guarded)
    monkeypatch.setattr(telemetry, "_get_tracer", telemetry._get_tracer)
    result = checkpoint.run(case("order-gap"), checkpoint.ScriptedTransport(runner.actions("order-gap")))
    assert result["terminal"] is None


def test_instrumented_script_preserves_results_and_parentage(recorded, monkeypatch):
    result = checkpoint.run(case("order-gap"), checkpoint.ScriptedTransport(runner.actions("order-gap")), trace_label="baseline")
    spans = recorded.get_finished_spans()
    root, = [s for s in spans if s.parent is None]
    assert root.name == "Invoice investigation"
    assert json.loads(root.attributes["input.value"])["variant"] == "baseline"
    children = [s for s in spans if s.parent is not None]
    by_id = {s.context.span_id: s for s in spans}
    turns = [s for s in children if s.name == "Investigation turn"]
    assert len(turns) == result["attempts"]["models"]
    assert [json.loads(s.attributes["input.value"])["number"] for s in sorted(turns, key=lambda s: s.start_time)] == list(range(1, len(turns) + 1))
    assert all(s.parent.span_id == root.context.span_id for s in turns)
    assert all(s.parent.span_id == root.context.span_id for s in children if s.name == "Validate invoice")
    for turn in turns:
        steps = sorted((s for s in children if s.parent.span_id == turn.context.span_id), key=lambda s: s.start_time)
        assert steps[0].name == "Investigator request"
        assert len(steps) in (1, 2)
        if len(steps) == 2:
            assert steps[1].attributes["openinference.span.kind"] == "TOOL"
            assert steps[0].end_time <= steps[1].start_time
        assert all(turn.start_time <= s.start_time <= s.end_time <= turn.end_time for s in steps)
        assert turn.attributes.get("output.value")
    assert all(by_id[s.parent.span_id].name == "Investigation turn" for s in children if s.name == "Investigator request" or s.attributes["openinference.span.kind"] == "TOOL")
    assert all(s.context.trace_id == root.context.trace_id for s in spans)
    assert all(root.start_time <= s.start_time <= s.end_time <= root.end_time for s in children)
    tools = [s for s in spans if s.attributes["openinference.span.kind"] == "TOOL"]
    assert len(tools) == result["attempts"]["tools"] == 6
    supplier, = [s for s in tools if s.name == "get_supplier"]
    assert json.loads(supplier.attributes["input.value"]) == {"supplier_id": "SUP-1"}
    assert json.loads(supplier.attributes["output.value"])["records"]
    models = [s for s in spans if s.attributes["openinference.span.kind"] == "LLM"]
    assert len(models) == result["attempts"]["models"]
    assert all(json.loads(s.attributes["input.value"])["mode"] == "scripted" for s in models)
    monkeypatch.delenv("WORKSHOP_TRACING")
    plain = checkpoint.run(case("order-gap"), checkpoint.ScriptedTransport(runner.actions("order-gap")))
    assert {k:v for k,v in result.items() if k != "elapsed_seconds"} == {k:v for k,v in plain.items() if k != "elapsed_seconds"}


def test_live_shaped_pdf_is_nested_under_tool_without_paid_calls(recorded, monkeypatch):
    class FakeLive(checkpoint.ScriptedTransport):
        live = True
    packet = case("order-gap")
    # Offline stand-in exercises the live branch; no gateway client exists.
    from workshop.session2.pdf import page_reference
    monkeypatch.setattr(checkpoint, "read_page", lambda *_: [{"page_ref": page_reference("order-gap"), "field": "quantity", "value": "10", "confidence": "clear", "excerpt": "Quantity 10", "origin": "live-page-review"}])
    result = checkpoint.run(packet, FakeLive(runner.actions("order-gap")))
    assert result["terminal"] is None
    spans = recorded.get_finished_spans()
    pdf, = [s for s in spans if s.name == "PDF page read"]
    parent, = [s for s in spans if s.context.span_id == pdf.parent.span_id]
    assert parent.name == "review_pdf_page"
    turn, = [s for s in spans if s.context.span_id == parent.parent.span_id]
    assert turn.name == "Investigation turn"
    assert turn.start_time <= parent.start_time <= pdf.start_time <= pdf.end_time <= parent.end_time <= turn.end_time
    assert json.loads(pdf.attributes["output.value"])


def test_reasoning_credentials_image_bodies_and_exception_text_not_recorded(recorded):
    with telemetry.session():
        with pytest.raises(ValueError):
            with telemetry.span("Safe failure", "LLM", {"api_key": "credential-marker", "items": [
                {"type": "reasoning", "encrypted_content": "reasoning-marker"},
                {"type": "input_image", "image_url": "data:image/png;base64,image-marker"}],
                "header": "Bearer secret-token", "key": "sk-secret123456"}) as observed:
                observed.output({"ok": True})
                raise ValueError("private-error-marker")
    span, = recorded.get_finished_spans()
    text = str(span.attributes) + str(span.events) + str(span.status.description)
    for marker in ("credential-marker", "reasoning-marker", "image-marker", "private-error-marker", "secret-token", "sk-secret123456"):
        assert marker not in text
    assert span.status.description == "ValueError"
    assert not span.events
    assert json.loads(telemetry._json({"large": "x" * 70000}))["omitted"]


def test_tracing_setup_or_span_failure_does_not_change_workflow(monkeypatch):
    class Broken:
        def start_as_current_span(self, *_a, **_kw):
            raise RuntimeError("private-export-failure")
    monkeypatch.setattr(telemetry, "_get_tracer", lambda: Broken())
    monkeypatch.setattr(telemetry, "_warned", False)
    with pytest.warns(RuntimeWarning, match="workflow continues"):
        result = checkpoint.run(case("posted-copy"), checkpoint.ScriptedTransport(runner.actions("posted-copy")))
    assert result["terminal"] is None
    assert result["recommendation"] == "ESCALATE"


def test_missing_optional_dependency_falls_back(monkeypatch):
    original = builtins.__import__
    def missing(name, *args, **kwargs):
        if name.startswith("opentelemetry"):
            raise ImportError("not installed")
        return original(name, *args, **kwargs)
    monkeypatch.setattr(builtins, "__import__", missing)
    monkeypatch.setattr(telemetry, "_provider", None)
    monkeypatch.setattr(telemetry, "_warned", False)
    monkeypatch.setenv("WORKSHOP_TRACING", "phoenix")
    with pytest.warns(RuntimeWarning):
        assert telemetry._get_tracer() is None


def test_sharing_bundle_is_independent_of_telemetry(recorded, tmp_path):
    root = tmp_path / "demo"
    demo(root)
    files = bundle_contents(root)
    assert len(files) == 8
    combined = b"".join(files.values())
    assert b"SUP-1" not in combined and b"instructions" not in combined
    assert not any("phoenix" in name or "telemetry" in name for name in files)


def test_export_configuration_ignores_external_endpoints_headers_and_proxies(monkeypatch):
    pytest.importorskip("opentelemetry.sdk")
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
    import opentelemetry.exporter.otlp.proto.http.trace_exporter as transport
    captured = {}
    def exporter(**kwargs):
        captured.update(kwargs)
        return InMemorySpanExporter()
    monkeypatch.setattr(transport, "OTLPSpanExporter", exporter)
    monkeypatch.setattr(telemetry, "_provider", None)
    monkeypatch.setenv("WORKSHOP_TRACING", "phoenix")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "https://external.invalid")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_HEADERS", "Authorization=secret")
    assert telemetry._get_tracer() is not None
    assert captured["endpoint"] == "http://127.0.0.1:6006/v1/traces"
    assert captured["headers"] == {"Content-Type": "application/x-protobuf"}
    assert captured["session"].trust_env is False
    assert telemetry._provider.resource.attributes["openinference.project.name"] == "workshop-session3"
    telemetry._provider.shutdown()


def test_terminal_workflow_is_marked_as_error(recorded):
    result = checkpoint.run(case("order-gap"), checkpoint.ScriptedTransport(runner.actions("order-gap")), enabled_tools=[])
    assert result["terminal"] is not None
    root, = [s for s in recorded.get_finished_spans() if s.parent is None]
    assert root.status.status_code.name == "ERROR"


@pytest.mark.parametrize("failure", ["model", "tool"])
def test_failed_turn_ends_and_cannot_parent_the_next_run(recorded, monkeypatch, failure):
    class BrokenModel(checkpoint.ScriptedTransport):
        def response(self, *_a, **_kw):
            raise ValueError("private-model-error")
    with monkeypatch.context() as scoped:
        if failure == "tool":
            def broken_tool(*_a, **_kw):
                raise ValueError("private-tool-error")
            scoped.setattr(checkpoint.EvidenceTools, "execute", broken_tool)
            client = checkpoint.ScriptedTransport(runner.actions("order-gap"))
        else:
            client = BrokenModel([])
        result = checkpoint.run(case("order-gap"), client)
        assert result["terminal"] is not None
    failed_turn, = [s for s in recorded.get_finished_spans() if s.name == "Investigation turn"]
    assert failed_turn.status.status_code.name == "ERROR" and failed_turn.end_time is not None
    assert json.loads(failed_turn.attributes["output.value"]) == {"stopped": True}
    second = checkpoint.run(case("posted-copy"), checkpoint.ScriptedTransport(runner.actions("posted-copy")))
    assert second["terminal"] is None
    spans = recorded.get_finished_spans()
    roots = [s for s in spans if s.parent is None]
    assert len(roots) == 2 and all(s.name == "Invoice investigation" for s in roots)
    assert len({s.context.trace_id for s in roots}) == 2
    assert "private-model-error" not in str([dict(s.attributes) for s in spans])
    assert "private-tool-error" not in str([dict(s.attributes) for s in spans])


def test_answer_only_turn_has_no_tool_child(recorded):
    answer = {"note": "Available evidence is insufficient.", "handoff": "Needs human review."}
    result = checkpoint.run(case("order-gap"), checkpoint.ScriptedTransport([answer]))
    assert result["answer"] == answer and result["terminal"] is None
    spans = recorded.get_finished_spans()
    turn, = [s for s in spans if s.name == "Investigation turn"]
    children = [s for s in spans if s.parent and s.parent.span_id == turn.context.span_id]
    assert [s.name for s in children] == ["Investigator request"]
    assert json.loads(turn.attributes["output.value"]) == {"answer": answer}
