"""Offline evidence, provenance and export boundaries for Session 3."""
import copy
import hashlib
import json
from pathlib import Path
import socket
import zipfile

import pytest

from workshop.session2 import runner
from workshop.session2.data import digest
from workshop.session3.core import bundle_contents, compare, demo, export, inspect_experiment
from workshop.session3.__main__ import main
from workshop.trace_view import render


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setattr(socket.socket, "connect", lambda *_: pytest.fail("network forbidden"))
    monkeypatch.setattr(runner, "LiveTransport", lambda *_a, **_k: pytest.fail("live client forbidden"))
    # Explicit scripted mode must remain offline even with a live-configured shell.
    monkeypatch.setenv("WORKSHOP_MODE", "live")
    monkeypatch.setenv("WORKSHOP_LIVE_ACK", "approved-paid-calls")


@pytest.fixture
def experiment(tmp_path):
    root = tmp_path / "experiment"
    demo(root)
    return root


def update(path, change):
    value = json.loads(path.read_text())
    change(value)
    path.write_text(json.dumps(value))


def test_demo_has_same_version_success_failure_and_honest_mode(experiment):
    projection, views = inspect_experiment(experiment)
    assert projection["changed_field"] == "enabled_tools"
    assert projection["interpretation"] == "scripted_tool_permission_boundary_only"
    assert projection["comparison_makes_model_calls"] is False
    assert len(projection["runs"]) == len(views) == 4
    failed = [r for r in projection["runs"] if r["execution_failed"]]
    assert [(r["case"], r["variant_role"]) for r in failed] == [("order-gap", "candidate")]
    assert all(r["original_preserved"] for r in projection["runs"])
    assert all(r["actual_cost_usd"] == "0" and r["usage"] is None for r in projection["runs"])
    assert b"Execution stopped" in views["traces/order-gap-candidate.html"]
    assert b"review_pdf_page" in views["traces/order-gap-baseline.html"]


def test_prompt_comparison_does_not_claim_offline_quality(tmp_path):
    variants = [{"id": "a", "model": "same", "prompt": "Use available evidence."},
                {"id": "b", "model": "same", "prompt": "Check history first, then other evidence."}]
    root = tmp_path / "prompt"
    runner.experiment(root, variants, mode="scripted")
    projection, _ = inspect_experiment(root)
    assert projection["changed_field"] == "prompt"
    assert projection["interpretation"] == "scripted_prompt_effect_not_measured"


@pytest.mark.parametrize("change", [
    lambda d: d["variants"][1].update(prompt="also changed"),
    lambda d: d["variants"][1].update(model="different-model"),
    lambda d: d["variants"][1].update(enabled_tools=d["variants"][0]["enabled_tools"]),
])
def test_one_change_gate_rejects_confounded_or_identical_variants(experiment, change):
    update(experiment / "configuration.json", change)
    with pytest.raises(ValueError, match="exactly one"):
        inspect_experiment(experiment)


@pytest.mark.parametrize("key,value", [("implementation_sha256", "0" * 64), ("code", "wrong"), ("data_source_sha256", "0" * 64), ("tools", 12), ("configured_model", "different"), ("mode", "live")])
def test_tampered_row_cannot_masquerade_as_matched(experiment, key, value):
    update(experiment / "comparison.json", lambda rows: rows[0].update({key: value}))
    with pytest.raises(ValueError):
        inspect_experiment(experiment)


def test_missing_or_duplicate_runs_rejected(experiment):
    update(experiment / "comparison.json", lambda rows: rows.__setitem__(3, copy.deepcopy(rows[0])))
    with pytest.raises(ValueError, match="duplicate"):
        inspect_experiment(experiment)


def test_unknown_live_measurements_stay_null(tmp_path):
    root = tmp_path / "live-artifacts"
    demo(root)
    update(root / "configuration.json", lambda d: d.update(mode="live"))
    def rows_live(rows):
        for row in rows:
            row.update(model=row["configured_model"], mode="live-investigator/live-page-review/synthetic-sqlite-tools", actual_cost_usd=None)
    update(root / "comparison.json", rows_live)
    for path in root.glob("*/*/run-1/review.json"):
        update(path, lambda d: d.update(execution_mode="live-investigator/live-page-review/synthetic-sqlite-tools", actual_cost_usd=None, usage=None))
    projection, _ = inspect_experiment(root)
    # This tests imported shape handling; these fabricated inputs are NOT live evidence.
    assert projection["input_mode"] == "live"
    assert all(r["actual_cost_usd"] is None and r["usage"] is None for r in projection["runs"])


def test_export_projects_not_copies_secrets_or_source_html(experiment, tmp_path):
    secret = 'sk-test-CANARY-PRIVATE<script>alert("secret")</script>'
    def config(d):
        d["dependencies"]["private"] = secret
        for v in d["variants"]:
            v.update(model=secret, prompt=secret)
    update(experiment / "configuration.json", config)
    def rows_secret(rows):
        for row in rows:
            row.update(configured_model=secret, prompt=digest(secret))
    update(experiment / "comparison.json", rows_secret)
    for path in experiment.glob("*/*/run-1/review.json"):
        def report(d):
            d["versions"]["prompt"] = digest(secret)
            d["private_field"] = secret
        update(path, report)
        with path.with_name("trace.jsonl").open("a") as stream:
            stream.write(json.dumps({"event": "answer", "handoff": secret, "note": secret}) + "\n")
            stream.write(json.dumps({"event": "reasoning", "encrypted_content": secret}) + "\n")
        path.with_name("trace-view.html").write_text(secret)
    (experiment / ".env").write_text(secret)
    archive = export(experiment, tmp_path / "share.zip")
    with zipfile.ZipFile(archive) as bundle:
        assert set(bundle.namelist()) == {"README.txt", "comparison.json", "comparison.html", "manifest.json", *(f"traces/{case}-{role}.html" for case in ("order-gap", "posted-copy") for role in ("baseline", "candidate"))}
        for name in bundle.namelist():
            assert b"CANARY" not in bundle.read(name)
            assert b"DE-SYNTHETIC" not in bundle.read(name)
            assert b"<script>" not in bundle.read(name)
        manifest = json.loads(bundle.read("manifest.json"))
        for name, expected in manifest["files"].items():
            assert hashlib.sha256(bundle.read(name)).hexdigest() == expected


def test_trace_projection_omits_session2_free_text_and_unknown_tools():
    secret = "PRIVATE-CANARY"
    page = render([
        {"event": "tool_requested", "name": "get_supplier", "arguments": {"supplier_id": secret}},
        {"event": "tool_result", "evidence": {"tool": "get_supplier", "records": [{"bank": secret}]}},
        {"event": "page_read", "observations": [{"confidence": "clear", "excerpt": secret, "value": secret}]},
        {"event": "answer", "handoff": secret, "note": secret},
        {"event": "terminal", "error": secret},
        {"event": "tool_requested", "name": [secret]},
    ])
    assert secret not in page
    assert "get_supplier; 1 returned record(s)" in page
    assert "1 observation(s); 1 clear" in page
    assert "unrecognised tool" in page


def test_symlink_and_oversize_artifact_rejected(experiment, tmp_path):
    path = experiment / "configuration.json"
    outside = tmp_path / "elsewhere.json"
    outside.write_bytes(path.read_bytes())
    path.unlink()
    path.symlink_to(outside)
    with pytest.raises(ValueError, match="symlinks"):
        inspect_experiment(experiment)
    path.unlink()
    path.write_bytes(b"x" * 524289)
    with pytest.raises(ValueError, match="byte bound"):
        inspect_experiment(experiment)


def test_export_and_compare_never_overwrite_or_write_into_source(experiment, tmp_path):
    output = tmp_path / "projected"
    compare(experiment, output)
    assert (output / "comparison.html").is_file()
    with pytest.raises(FileExistsError):
        compare(experiment, output)
    archive = tmp_path / "share.zip"
    export(experiment, archive)
    before = archive.read_bytes()
    with pytest.raises(FileExistsError):
        export(experiment, archive)
    assert archive.read_bytes() == before
    with pytest.raises(ValueError, match="outside"):
        export(experiment, experiment / "share.zip")
    with pytest.raises(ValueError, match=".zip"):
        export(experiment, tmp_path / "share.txt")


def test_cli_no_live_mode_and_sanitized_failure(tmp_path, capsys):
    with pytest.raises(SystemExit):
        main(["demo", "--mode", "live", "--output", str(tmp_path / "demo")])
    capsys.readouterr()
    with pytest.raises(SystemExit):
        main(["export", "--input", str(tmp_path / "PRIVATE-CANARY"), "--output", str(tmp_path / "out.zip")])
    assert "PRIVATE-CANARY" not in capsys.readouterr().err


def test_swapped_trace_is_not_a_matched_run(experiment):
    first = experiment / "order-gap/baseline/run-1/trace.jsonl"
    second = experiment / "posted-copy/baseline/run-1/trace.jsonl"
    first.write_bytes(second.read_bytes())
    with pytest.raises(ValueError, match="correspond"):
        inspect_experiment(experiment)


def test_terminal_trace_cannot_be_hidden(experiment):
    path = experiment / "order-gap/candidate/run-1/trace.jsonl"
    events = [json.loads(line) for line in path.read_text().splitlines()]
    path.write_text("".join(json.dumps(e) + "\n" for e in events if e["event"] != "terminal"))
    with pytest.raises(ValueError, match="correspond"):
        inspect_experiment(experiment)


def test_changed_original_is_not_the_frozen_case(experiment):
    path = experiment / "order-gap/baseline/run-1/review.json"
    update(path, lambda d: d["original"].update(quantity="999"))
    with pytest.raises(ValueError, match="frozen case"):
        inspect_experiment(experiment)


def test_offline_variants_share_the_same_fixed_actions():
    a = runner.Variant(id="baseline", model="same", prompt="baseline wording")
    b = runner.Variant(id="candidate", model="same", prompt="changed wording")
    first = runner._client(a, "scripted", "order-gap", 0)
    second = runner._client(b, "scripted", "order-gap", 1)
    assert [first.response([]) for _ in range(7)] == [second.response([]) for _ in range(7)]


def test_summary_and_report_cannot_override_the_trace_outcome(experiment):
    update(experiment / "comparison.json", lambda rows: rows[0].update(recommendation="READY_FOR_APPROVAL"))
    update(experiment / "order-gap/baseline/run-1/review.json", lambda d: d.update(recommendation="READY_FOR_APPROVAL"))
    with pytest.raises(ValueError, match="final trace outcome"):
        inspect_experiment(experiment)


def test_export_does_not_leak_session1_numeric_readings(experiment):
    path = experiment / "order-gap/baseline/run-1/trace.jsonl"
    with path.open("a") as stream:
        stream.write(json.dumps({"event": "findings_applied", "changes": [{"field": "lines.1.quantity", "before": "1234567.89", "after": "7654321.98"}]}) + "\n")
    files = bundle_contents(experiment)
    assert all(b"1234567.89" not in raw and b"7654321.98" not in raw for raw in files.values())
