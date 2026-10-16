"""Private contextual traces remain offline and separate from safe exports."""
import json
import socket

import pytest

from workshop.session2 import runner
from workshop.session3.core import bundle_contents, demo
from workshop.session3.context import context, render_context
from workshop.session3.__main__ import main


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setattr(socket.socket, "connect", lambda *_: pytest.fail("network forbidden"))
    monkeypatch.setattr(runner, "LiveTransport", lambda *_a, **_k: pytest.fail("model calls forbidden"))


def test_context_shows_recorded_io_without_changing_export(tmp_path):
    source = tmp_path / "experiment"
    demo(source)
    before = bundle_contents(source)
    target = context(source, tmp_path / "private")
    assert len(list(target.glob("*.html"))) == 5
    view = (target / "order-gap-baseline.html").read_text()
    report = json.loads((source / "order-gap/baseline/run-1/review.json").read_text())
    assert report["original"]["invoice_number"] in view
    assert '"arguments"' in view.replace("&quot;", '"')
    assert "supplier_bank" in view and "records" in view and "coverage" in view
    assert "Final investigator output" in view
    assert "Exact model request/response bodies" in view
    assert "Private local view" in view
    assert "Configured investigation prompt" in view
    assert bundle_contents(source) == before
    assert report["original"]["invoice_number"].encode() not in b"".join(before.values())
    with pytest.raises(FileExistsError):
        context(source, target)
    with pytest.raises(ValueError, match="outside"):
        context(source, source / "private")


def test_context_escapes_content_masks_credentials_and_omits_unknown_fields():
    events = [{"event": "tool_requested", "name": "get_supplier", "arguments": {
        "supplier_id": "<script>alert(1)</script>", "api_key": "credential-marker",
        "nested": {"encrypted_content": "reasoning-marker"}, "text": "Bearer secret-token-value"},
        "unknown": "unknown-marker"}, {"event": "invented", "value": "unknown-event-marker"}]
    view = render_context(events, {"original": {}, "answer": None}, {"prompt": "sk-secret123456"}, mode="scripted", title="<img>")
    assert "<script>" not in view and "&lt;script&gt;" in view
    for hidden in ("credential-marker", "reasoning-marker", "secret-token-value", "sk-secret123456", "unknown-marker", "unknown-event-marker"):
        assert hidden not in view
    assert "No final investigator answer was recorded" in view
    assert "default-src 'none'" in view


def test_context_cli_uses_only_saved_artifacts(tmp_path, capsys):
    source = tmp_path / "experiment"
    demo(source)
    main(["context", "--input", str(source), "--output", str(tmp_path / "context")])
    assert "Private local context" in capsys.readouterr().out
    assert (tmp_path / "context/index.html").exists()
