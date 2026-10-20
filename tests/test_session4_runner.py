"""Local runner and terminal approval checks; no credentials or paid calls."""
import json
from decimal import Decimal

import pytest

from workshop.session4 import runner


def test_scripted_batch_and_escaped_local_reports(tmp_path):
    output = tmp_path / "batch"
    rows = runner.experiment(output, input_fn=lambda _: "approve reviewed locally")
    assert len(rows) == 4
    assert [row["draft_review"] for row in rows] == ["approved", "not_applicable", "not_applicable", "not_applicable"]
    assert [row["followup_action"] for row in rows] == ["recommend_email", "await_existing_request", "internal_handoff", "human_review_only"]
    assert all(row["mode"] == "scripted" and row["reserved_usd"] == "0" for row in rows)
    assert rows[-1]["invoice_recommendation"] == "ESCALATE"
    assert rows[-1]["investigation_terminal"] is None
    configuration = json.loads((output / "configuration.json").read_text())
    assert configuration["mode"] == "scripted"
    assert configuration["data"]["supplier-request"]["pdf_sha256"] == configuration["data"]["request-pending"]["pdf_sha256"]
    assert json.loads((output / "summary.json").read_text()) == rows
    for name in runner.SCENARIOS:
        report = json.loads((output / name / "review.json").read_text())
        original = json.loads((output / name / "investigation.json").read_text())
        assert original["original"] == original["candidate"]
        assert report["invoice_recommendation"] == original["recommendation"]
        assert report["interpretation"].startswith("scripted wiring only")
        events = [json.loads(line) for line in (output / name / "trace.jsonl").read_text().splitlines()]
        assert all("phase" in event and "actor" in event for event in events)
        assert (output / name / "review.html").exists()
    text = (output / "supplier-request" / "review.json").read_text()
    assert '"outbox"' not in text and '"sent"' not in text


def test_pending_is_saved_before_input_invalid_input_keeps_same_draft(tmp_path):
    output = tmp_path / "review"
    observed = []
    def respond(_):
        saved = json.loads((output / "supplier-request" / "review.json").read_text())
        assert saved["draft_review"] == "pending_review"
        observed.append(saved)
        return "maybe" if len(observed) == 1 else "reject do not request another copy"
    rows = runner.experiment(output, scenario="supplier-request", input_fn=respond)
    assert rows[0]["draft_review"] == "rejected"
    final = json.loads((output / "supplier-request" / "review.json").read_text())
    assert final["email_draft"] is None
    assert observed[0]["proposal"] == observed[1]["proposal"] == final["proposal"]
    assert final["attempts"] == observed[0]["attempts"]
    assert final["combined_attempts"] == observed[0]["combined_attempts"]


@pytest.mark.parametrize("exception", [EOFError, KeyboardInterrupt])
def test_closed_input_stops_batch_with_pending_output(tmp_path, exception):
    output = tmp_path / "interrupted"
    def close(_):
        raise exception()
    rows = runner.experiment(output, input_fn=close)
    assert len(rows) == 1
    assert rows[0]["draft_review"] == "pending_review"
    assert not (output / "request-pending").exists()
    saved = json.loads((output / "supplier-request" / "review.json").read_text())
    assert saved["pending_review"] is not None
    assert saved["email_draft"] is None
    assert saved["terminal"] is None


def test_existing_output_refused(tmp_path):
    with pytest.raises(FileExistsError):
        runner.experiment(tmp_path)


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-1", "oops"])
def test_invalid_allowances_refused(tmp_path, value):
    with pytest.raises(ValueError):
        runner.experiment(tmp_path / "invalid", experiment_allowance=value)


def test_batch_cap_reserves_whole_execution_before_next_case(tmp_path):
    output = tmp_path / "limited"
    with pytest.raises(ValueError, match="next complete execution"):
        runner.experiment(output, scenario="all", investigation_allowance="0.40", followup_allowance="0.15", experiment_allowance="0.55", input_fn=lambda _: "approve")
    assert len(json.loads((output / "summary.json").read_text())) == 1
    assert not (output / "request-pending").exists()


def test_live_requires_full_phase_reservations_before_outputs(tmp_path, monkeypatch):
    class Live:
        cost = Decimal("0.05")
        model = "approved-test-alias"
    monkeypatch.setattr(runner, "LiveTransport", Live)
    with pytest.raises(ValueError, match="eight investigation"):
        runner.experiment(tmp_path / "live", mode="live", investigation_allowance="0.39", followup_allowance="0.15", experiment_allowance="1")
    assert not (tmp_path / "live").exists()


def test_live_failure_has_no_script_fallback_or_provider_error_leak(tmp_path, monkeypatch):
    secret = "provider-secret-in-error"
    class FailingLive:
        live = True
        cost = Decimal("0.05")
        model = "approved-test-alias"
        def response(self, *args, **kwargs):
            raise RuntimeError(secret)
    monkeypatch.setattr(runner, "LiveTransport", FailingLive)
    def no_script(*args, **kwargs):
        raise AssertionError("live failure must not use a script")
    monkeypatch.setattr(runner, "ScriptedTransport", no_script)
    output = tmp_path / "live-error"
    rows = runner.experiment(output, mode="live", scenario="supplier-request", investigation_allowance="0.40", followup_allowance="0.15", experiment_allowance="0.55")
    assert rows[0]["investigation_terminal"] is not None
    assert rows[0]["followup_action"] == "human_review_only"
    assert rows[0]["actual_cost_usd"] is None
    for path in output.rglob("*"):
        if path.is_file():
            assert secret not in path.read_text()


def test_html_escapes_draft_and_note(tmp_path):
    rows = runner.experiment(tmp_path / "html", scenario="supplier-request", input_fn=lambda _: "approve <script>alert(1)</script>")
    assert rows[0]["draft_review"] == "approved"
    text = (tmp_path / "html" / "supplier-request" / "review.html").read_text()
    assert "<script>" not in text
    assert "&lt;script&gt;" in text


def test_unexpected_investigation_failure_retains_visible_rows(tmp_path, monkeypatch):
    def fail(*args, **kwargs):
        raise ValueError("private-provider-message")
    monkeypatch.setattr(runner, "investigate", fail)
    output = tmp_path / "setup-errors"
    rows = runner.experiment(output)
    assert len(rows) == 4
    assert all(row["investigation_terminal"] and not row["attempt_counts_complete"] for row in rows)
    assert all(row["followup_action"] == "human_review_only" for row in rows)
    assert "private-provider-message" not in (output / "supplier-request" / "review.json").read_text()


def test_unexpected_followup_setup_failure_preserves_invoice_report(tmp_path, monkeypatch):
    class BrokenSession:
        def __init__(self, *args, **kwargs):
            raise RuntimeError("private-followup-provider-message")
    monkeypatch.setattr(runner, "FollowupSession", BrokenSession)
    output = tmp_path / "followup-errors"
    rows = runner.experiment(output, scenario="internal-receipts")
    assert rows[0]["invoice_recommendation"] == "NEEDS_CLARIFICATION"
    assert rows[0]["investigation_terminal"] is None
    assert rows[0]["followup_terminal"] is not None
    assert not rows[0]["attempt_counts_complete"]
    for path in output.rglob("*"):
        if path.is_file():
            assert "private-followup-provider-message" not in path.read_text()


def test_cli_never_prints_unexpected_exception_payload(tmp_path, monkeypatch, capsys):
    from workshop.session4 import __main__ as cli
    def fail(*args, **kwargs):
        raise ValueError("private-setup-message")
    monkeypatch.setattr(cli, "experiment", fail)
    monkeypatch.setattr("sys.argv", ["session4", "--output", str(tmp_path / "unused")])
    with pytest.raises(SystemExit) as error:
        cli.main()
    assert error.value.code == 2
    captured = capsys.readouterr()
    assert "private-setup-message" not in captured.err
    assert "ValueError" in captured.err
