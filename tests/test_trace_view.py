import json

import pytest

from workshop.trace_view import main, render


def test_trace_distinguishes_proposals_from_accepted_corrections():
    document = render([
        {"event": "validation", "checks": [{"status": "unresolved"}]},
        {"event": "model_result", "result": {"tool_requests": [{"name": "review_pdf_page"}]}},
        {"event": "page_review", "request": {"page": 1}, "evidence": [{"confidence": "clear"}]},
        {"event": "investigation", "result": {"findings": {"corrections": [{}]}}},
        {"event": "findings_applied", "changes": [{"field": "lines.1.quantity", "before": "100", "after": "10"}]},
        {"event": "finalization", "recommendation": "READY_FOR_APPROVAL", "checks": [{"status": "pass"}]},
    ])
    assert "1 unresolved" in document
    assert "1 tool request(s)" in document
    assert "review_pdf_page · page 1; 1 observation(s); 1 clear" in document
    assert "1 proposed correction(s)" in document
    assert "1 accepted correction(s); Line quantity: 100 → 10" in document
    assert "recommendation: READY_FOR_APPROVAL" in document
    assert "no span durations or actual provider costs" in document
    assert "can describe the same model operation" in document


def test_imported_text_and_secrets_are_never_embedded():
    secret = 'sk-test-SECRET<script>alert("owned")</script>'
    document = render([
        {"event": "model_result", "api_key": secret, "reasoning": secret, "result": {"handoff": secret, "findings": {"note": secret}}},
        {"event": "page_review", "request": {"page": secret, "invoice_id": secret}, "evidence": [{"id": secret, "excerpt": secret, "field": secret, "value": secret}]},
        {"event": "findings_applied", "note": secret, "changes": [{"field": "lines.1.quantity", "before": secret, "after": secret, "evidence_id": secret}]},
        {"event": "finalization", "recommendation": secret, "checks": [{"detail": secret, "status": secret}]},
        {"event": secret},
    ])
    assert secret not in document
    assert "SECRET" not in document
    assert "<script" not in document
    assert "Line quantity: withheld → withheld" in document
    assert "Content-Security-Policy" in document


def test_malformed_event_shapes_are_safe():
    document = render([None, [], {"event": []}, {"event": "policy", "recommendation": []}, {"event": "page_review", "request": [], "evidence": "bad"}, {"event": "investigation", "result": {"findings": []}}, {"event": "extraction", "source": []}])
    assert "3 unrecognised or malformed event(s) omitted" in document


def test_offline_command_writes_html_beside_trace(tmp_path, capsys):
    trace = tmp_path / "trace.jsonl"
    trace.write_text(json.dumps({"event": "finalization", "recommendation": "NEEDS_CLARIFICATION"}) + "\n")
    main([str(trace)])
    assert "NEEDS_CLARIFICATION" in trace.with_name("trace-view.html").read_text()
    assert "Trace view:" in capsys.readouterr().out


@pytest.mark.parametrize("body", [b"not json", b"\xff", b"x" * 2_000_001])
def test_invalid_trace_is_rejected(tmp_path, body):
    trace = tmp_path / "trace.jsonl"
    trace.write_bytes(body)
    with pytest.raises(SystemExit):
        main([str(trace)])
    assert not trace.with_name("trace-view.html").exists()


def test_source_cannot_be_overwritten(tmp_path):
    trace = tmp_path / "trace.jsonl"
    trace.write_text('{}\n')
    with pytest.raises(SystemExit):
        main([str(trace), "--output", str(trace)])
    assert trace.read_text() == '{}\n'
