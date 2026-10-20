"""Small local runner for invoice follow-up; scripted runs prove wiring only."""
import copy
import csv
from decimal import Decimal, InvalidOperation
import html
import json
from pathlib import Path
from importlib.metadata import version
import subprocess

from .. import telemetry
from ..session2.checkpoint import LiveTransport, ScriptedTransport, PROMPT, run as investigate
from ..session2.data import digest
from .checkpoint import FollowupSession, LEAD_PROMPT, SPECIALIST_PROMPT, ReviewDecision
from .data import SCENARIOS, correspondence_snapshot, invoice_packet
from .tools import CorrespondenceLookup


def amount(value):
    """Validate explicit reservations, without treating them as actual billing."""
    try:
        value = Decimal(value)
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError("allowance must be a finite nonnegative decimal") from None
    if not value.is_finite() or value < 0:
        raise ValueError("allowance must be a finite nonnegative decimal")
    return value


def investigation_actions(name):
    """Fixed, visible evidence paths; not adaptive tool-selection examples."""
    history = {"name": "get_invoice_history", "arguments": {"supplier_id": "SUP-1", "invoice_number": "INV / 204"}}
    if name == "posted-copy":
        return [history]
    return [
        {"name": "review_pdf_page", "arguments": {"page": 1}},
        {"name": "get_supplier", "arguments": {"supplier_id": "SUP-1"}},
        {"name": "get_purchase_order", "arguments": {"order_id": "PO-7"}},
        {"name": "get_receipts", "arguments": {"order_id": "PO-7"}}, history,
        {"note": "Scripted evidence path completed.", "handoff": "Selected coverage and the recorded unresolved checks remain open."},
    ]


def followup_actions(name, investigation):
    """Fixed examples with actual registered references. Never used in live mode."""
    evidence = [item["id"] for item in investigation["evidence"]]
    if name == "internal-receipts":
        return [{"action": "internal_handoff", "reason": "Ask warehouse/accounts payable whether accepted receipt records supporting the remaining four units are available; six of ten are supported.", "evidence_ids": evidence}]
    if name == "posted-copy":
        return [{"action": "human_review_only", "reason": "Accounting must review the matching posted record LEDGER-9.", "evidence_ids": evidence}]
    lead = {"action": "supplier_followup", "reason": "Actual page review records an unreadable quantity; request a legible invoice if a current request is not already pending.", "evidence_ids": evidence}
    lookup = {"name": "read_supplier_correspondence", "arguments": {"supplier_id": "SUP-1"}}
    if name == "request-pending":
        conclusion = {"action": "await_existing_request", "reason": "In the selected correspondence MAIL-201 requests the current invoice and MAIL-202 promises a legible copy tomorrow. The unreadable quantity remains unresolved.", "evidence_ids": evidence, "message_ids": ["MAIL-201", "MAIL-202"], "draft": None}
    else:
        conclusion = {"action": "recommend_email", "reason": "The selected messages concern INV-199, rather than the current invoice. Request a legible copy without inferring its quantity.", "evidence_ids": evidence, "message_ids": ["MAIL-101", "MAIL-102"], "draft": {"recipient": "billing@workshop-supplier.example", "subject": "Request for a legible copy of invoice INV / 204", "body": "Hello, please provide a legible copy of invoice INV / 204. We cannot read the quantity for the Calibration kit line on the copy available to us. Please include a copy where that field is clear. Thank you."}}
    return [lead, lookup, conclusion]


def _safe_report(value):
    """Never persist provider exception text; transport/private continuations stay in memory."""
    if isinstance(value, dict):
        return {key: ("Execution stopped; provider details omitted." if key in ("terminal", "error") and item else _safe_report(item)) for key, item in value.items() if key not in ("encrypted_content", "api_key", "authorization")}
    if isinstance(value, list):
        return [_safe_report(item) for item in value]
    return value


def _write_json(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def _save(directory, investigation, report, *, mode):
    report = _safe_report(copy.deepcopy(report))
    invoice = _safe_report(copy.deepcopy(investigation))
    invoice_trace = invoice.pop("trace", [])
    followup_trace = report.pop("trace", [])
    events = [{"phase": "investigation", "actor": "lead", **event} for event in invoice_trace]
    events += [{"phase": "followup", **event} for event in followup_trace]
    report.update(execution_mode=mode, interpretation="scripted wiring only; not model quality evidence" if mode == "scripted" else "live model choices; synthetic invoice and correspondence sources")
    report["combined_attempts"] = {key: invoice["attempts"][key] + report["attempts"][key] for key in ("models", "tools")}
    report["combined_reserved_usd"] = str(Decimal(invoice["reserved_usd"]) + Decimal(report["reserved_usd"]))
    report["actual_cost_usd"] = "0" if mode == "scripted" else None
    report["usage"] = None
    _write_json(directory / "investigation.json", invoice)
    _write_json(directory / "review.json", report)
    (directory / "trace.jsonl").write_text("".join(json.dumps(event) + "\n" for event in events), encoding="utf-8")
    body = "<h1>Invoice follow-up review</h1><p>" + html.escape(report["interpretation"]) + "</p><h2>Recommendation and draft review</h2><pre>" + html.escape(json.dumps(report, indent=2)) + "</pre><h2>Role-labelled local events</h2>"
    for index, event in enumerate(events, 1):
        body += "<details><summary>" + html.escape(f"{index}: {event.get('phase', '')} / {event.get('actor', event.get('role', 'runtime'))} / {event.get('event', '')}") + "</summary><pre>" + html.escape(json.dumps(event, indent=2)) + "</pre></details>"
    (directory / "review.html").write_text("<!doctype html><meta charset=utf-8><title>Session 4 review</title>" + body, encoding="utf-8")
    return report


def _summary(output, rows):
    _write_json(output / "summary.json", rows)
    fields = ["scenario", "mode", "invoice_recommendation", "followup_action", "draft_review", "investigation_terminal", "followup_terminal", "models", "tools", "elapsed_seconds", "reserved_usd", "actual_cost_usd", "attempt_counts_complete"]
    with (output / "summary.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _review(session, report, directory, investigation, mode, input_fn):
    """Save pending output before input; EOF/cancel is neither rejection nor approval."""
    while report.get("pending_review"):
        print("\nReview the exact proposed manual follow-up (nothing will be sent):")
        print(json.dumps(report["pending_review"], indent=2))
        try:
            answer = input_fn("Approve or reject this draft [approve/reject; optional note after a space]: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nDraft remains pending. In-memory approval cannot resume after this process exits.")
            return report, True
        decision, _, note = answer.partition(" ")
        if decision.lower() not in ("approve", "reject"):
            print("Enter approve or reject. The same draft remains pending.")
            continue
        try:
            decision = ReviewDecision.model_validate({"approved": decision.lower() == "approve", "note": note or None}).model_dump()
        except ValueError:
            print("Invalid review note; use at most 2000 characters. The same draft remains pending.")
            continue
        report = session.resume(decision)
        _save(directory, investigation, report, mode=mode)
    return report, False


def _run_case(directory, name, mode, live, invoice_limit, followup_limit, input_fn):
    """Own the lead's active span separately from human waiting and finalization."""
    packet = invoice_packet(name)
    complete_counts, stopped = True, False
    try:
        with telemetry.span("Lead investigator", "AGENT", {"invoice": packet["invoice"], "mode": mode}) as lead:
            try:
                client = live if live is not None else ScriptedTransport(investigation_actions(name))
                investigation = investigate(packet, client, allowance=invoice_limit, trace_label="session4-lead")
            except Exception as exc:
                complete_counts = False
                investigation = {"original": copy.deepcopy(packet["invoice"]), "candidate": copy.deepcopy(packet["invoice"]), "corrections": [], "checks": [], "evidence": [], "recommendation": "ESCALATE", "answer": None, "terminal": "investigation failed: " + type(exc).__name__, "trace": [], "attempts": {"models": 0, "tools": 0}, "reserved_usd": str(invoice_limit), "elapsed_seconds": 0, "actual_cost_usd": None if live else "0", "execution_mode": mode}
            _write_json(directory / "investigation.json", _safe_report(investigation))
            followup_client = live if live is not None else ScriptedTransport(followup_actions(name, investigation))
            session = FollowupSession(investigation, followup_client, CorrespondenceLookup(packet["invoice"], correspondence_snapshot(name)), allowance=followup_limit)
            report = session.start()
            report["attempt_counts_complete"] = complete_counts
            _save(directory, investigation, report, mode=mode)
            lead.output({key: report[key] for key in ("invoice_recommendation", "followup_action", "reason", "proposal", "draft_review")})
            if investigation.get("terminal") or report.get("terminal"):
                lead.error("Execution stopped; see the local report.")
        # GraphInterrupt is already handled by LangGraph. Open the human span
        # after the lead ends, so approval waiting is not agent/model latency.
        if report.get("pending_review"):
            with telemetry.span("Human draft review", "CHAIN", report["pending_review"]) as review:
                report, stopped = _review(session, report, directory, investigation, mode, input_fn)
                review.output({key: report[key] for key in ("draft_review", "email_draft", "followup_action", "invoice_recommendation")})
    except Exception as exc:
        complete_counts = False
        report = {"invoice_recommendation": investigation["recommendation"], "followup_action": "human_review_only", "reason": "Follow-up unavailable; human review required (" + type(exc).__name__ + ").", "references": {"invoice_evidence_ids": [], "lookup_id": None, "message_ids": []}, "email_draft": None, "draft_review": "not_applicable", "proposal": None, "pending_review": None, "terminal": "follow-up failed: " + type(exc).__name__, "attempts": {"models": 0, "tools": 0}, "reserved_usd": str(followup_limit), "elapsed_seconds": 0, "trace": []}
    report["attempt_counts_complete"] = complete_counts
    with telemetry.span("Finalize recommendation", "CHAIN", {"draft_review": report["draft_review"]}) as final:
        saved = _save(directory, investigation, report, mode=mode)
        final.output(saved)
    row = {"scenario": name, "mode": mode, "invoice_recommendation": saved["invoice_recommendation"], "followup_action": saved["followup_action"], "draft_review": saved["draft_review"], "investigation_terminal": _safe_report(investigation).get("terminal"), "followup_terminal": saved.get("terminal"), "models": saved["combined_attempts"]["models"], "tools": saved["combined_attempts"]["tools"], "elapsed_seconds": investigation["elapsed_seconds"] + report["elapsed_seconds"], "reserved_usd": saved["combined_reserved_usd"], "actual_cost_usd": saved["actual_cost_usd"], "attempt_counts_complete": complete_counts}
    return row, stopped


def experiment(output, *, mode="scripted", scenario="all", investigation_allowance="0", followup_allowance="0", experiment_allowance="0", input_fn=None):
    """Run fresh independent sessions. Live errors never fall back to fixed scripts."""
    if mode not in ("scripted", "live") or scenario not in ("all", *SCENARIOS):
        raise ValueError("unsupported mode or scenario")
    invoice_limit, followup_limit, batch_limit = map(amount, (investigation_allowance, followup_allowance, experiment_allowance))
    # Construct the live transport once before writing outputs; never save env or credentials.
    live = LiveTransport() if mode == "live" else None
    if live is not None and (invoice_limit < 8 * live.cost or followup_limit < 3 * live.cost):
        raise ValueError("live allowances must reserve eight investigation and three follow-up model requests")
    envelope = invoice_limit + followup_limit
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    names = SCENARIOS if scenario == "all" else (scenario,)
    root = Path(__file__).resolve().parents[3]
    revision = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, text=True, capture_output=True, check=False).stdout.strip() or "unavailable"
    sources = Path(__file__).parents[1]
    files = sorted(sources.rglob("*.py"))
    status = subprocess.run(["git", "status", "--porcelain"], cwd=root, text=True, capture_output=True, check=False)
    config = {"mode": mode, "scenario": scenario, "interpretation": "scripted wiring only" if mode == "scripted" else "live calls; synthetic read-only sources", "code": revision,
              "implementation_sha256": digest({str(p.relative_to(root)): p.read_text() for p in files}), "code_dirty": bool(status.stdout.strip()) if status.returncode == 0 else None,
              "prompts_sha256": digest({"investigator": PROMPT, "lead": LEAD_PROMPT, "specialist": SPECIALIST_PROMPT}), "dependencies": {name: version(name) for name in ("langgraph", "pydantic", "httpx")},
              "reasoning_effort": getattr(live, "effort", None), "max_output_tokens": getattr(live, "max_output_tokens", None),
              "investigation_allowance_usd": str(invoice_limit), "followup_allowance_usd": str(followup_limit), "experiment_allowance_usd": str(batch_limit),
              "model": live.model if live else "offline-script", "max_call_reservation_usd": str(live.cost if live else 0), "actual_cost_usd": None if live else "0",
              "data": {name: {"invoice_source_sha256": invoice_packet(name)["source_hash"], "pdf_sha256": invoice_packet(name)["invoice"]["page_ref"]["sha256"], "correspondence_sha256": digest(correspondence_snapshot(name))} for name in names}}
    _write_json(output / "configuration.json", config)
    rows, committed = [], Decimal("0")
    _summary(output, rows)
    for name in names:
        if committed + envelope > batch_limit:
            raise ValueError("experiment allowance cannot reserve the next complete execution; previous outputs retained")
        committed += envelope
        directory = output / name
        directory.mkdir()
        with telemetry.session(project="workshop-session4"):
            with telemetry.span("Session 4: " + name, "CHAIN", {"scenario": name, "mode": mode,
                    "interpretation": config["interpretation"]}) as workflow:
                row, stopped = _run_case(directory, name, mode, live, invoice_limit, followup_limit, input_fn or input)
                workflow.output(row)
                if row["investigation_terminal"] or row["followup_terminal"]:
                    workflow.error("Execution stopped; see the local report.")
            telemetry.flush()
        rows.append(row)
        _summary(output, rows)
        if stopped:
            break
    return rows
