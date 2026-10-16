"""Credential-free command line and static human review output."""
import argparse
import html
import json
import os
from decimal import Decimal
from pathlib import Path

# Explicitly disable optional hosted LangChain tracing, even in inherited shells.
os.environ["LANGCHAIN_TRACING_V2"] = "false"
os.environ["LANGSMITH_TRACING"] = "false"

from .pack import ROOT, CASES, seed, fixture, load_packet
from .runtime import Budget, Runtime, ScriptedClient, LiveClient
from .extraction import extract
from .graph import Nodes, run
from .scripts import interaction_examples

STATE = ROOT / "state"
DB = STATE / "workshop.sqlite"

def preflight():
    if os.getenv("WORKSHOP_MODE", "offline") != "offline":
        raise ValueError("offline preflight requires WORKSHOP_MODE=offline")
    if not DB.exists():
        raise ValueError("database missing; run workshop seed")
    from .tools import page_image
    from .validation import validate
    from .graph import scaffold
    for case in CASES:
        extraction = fixture(case)
        validate(extraction.candidate.model_dump(mode="json"), load_packet(case, DB))
        page_image(case, 1)
    # Prepared matching-case smoke test; never imports or assumes learner TODOs.
    extraction = fixture("matching")
    runtime = Runtime(extraction)
    def unexpected_investigation(*_):
        raise AssertionError("prepared matching case should bypass investigation")
    nodes = Nodes(runtime, unexpected_investigation, packet=load_packet("matching", DB))
    result = run(scaffold(nodes), {"candidate": extraction.candidate.model_dump(mode="json")}, nodes)
    if result["recommendation"] != "READY_FOR_APPROVAL":
        raise ValueError("prepared matching graph smoke check failed")
    print("Offline preflight passed: fixture hashes, SQLite packets, PDF rendering and prepared matching LangGraph smoke check. Learner edits are not evaluated.")

def review(case, result, runtime):
    folder = STATE / case
    folder.mkdir(parents=True, exist_ok=True)
    report = {"case": case, "mode": "live" if runtime.client.live else "offline scripted examples (prompt-independent)", "recommendation": result["recommendation"], "human_decision": "PENDING - separate human review", "handoff": result.get("handoff"), "terminal": result.get("terminal"), "extraction": runtime.extraction.model_dump(mode="json"), "candidate": result["candidate"], "checks": next((e["checks"] for e in reversed(runtime.events) if e["event"] == "finalization"), result["checks"]), "evidence": [e.model_dump(mode="json") for e in runtime.evidence.values()], "correction_history": runtime.history, "attempts": {"tools": runtime.budget.tools, "models": runtime.budget.models, "reserved_usd": str(runtime.budget.reserved)}}
    (folder / "review.json").write_text(json.dumps(report, indent=2) + "\n")
    (folder / "trace.jsonl").write_text("".join(json.dumps(e) + "\n" for e in runtime.events))
    rows = "".join(f"<tr><td>{html.escape(c['id'])}</td><td>{c['status']}</td><td>{html.escape(c.get('detail', c.get('question', '')))}</td></tr>" for c in report["checks"])
    document = f"""<!doctype html><html lang="en"><meta charset="utf-8"><title>Invoice human review</title><style>body{{font:16px system-ui;max-width:1100px;margin:40px auto;padding:20px}}table{{border-collapse:collapse;width:100%}}td,th{{padding:8px;border:1px solid #ccc;text-align:left}}pre{{white-space:pre-wrap;overflow-wrap:anywhere}}a{{color:#1565c0}}</style><h1>{html.escape(case)}: {result['recommendation']}</h1><p>Human decision: PENDING. This is a recommendation. No payment/accounting action.</p><p>{html.escape(report['mode'])}</p><p>{html.escape(report['handoff'] or report['terminal'] or '')}</p><p><a href="../../data/invoices/{case}.pdf">Open source PDF</a> | <a href="review.json">Full review JSON</a> | <a href="trace.jsonl">Trace events</a></p><table><tr><th>Check</th><th>Status</th><th>Reason</th></tr>{rows}</table><h2>Evidence and correction history</h2><pre>{html.escape(json.dumps({'evidence':report['evidence'],'corrections':runtime.history}, indent=2))}</pre><h2>Original extraction and current candidate</h2><pre>{html.escape(json.dumps({'original':report['extraction']['original'],'candidate':report['candidate']}, indent=2))}</pre></html>"""
    (folder / "review.html").write_text(document)
    return folder

def failed_review(case, error_type):
    """Bootstrap/extraction failures also leave a credential-free human handoff."""
    folder = STATE / case
    folder.mkdir(parents=True, exist_ok=True)
    result = {"case": case, "recommendation": "ESCALATE", "human_decision": "PENDING", "handoff": "Startup/extraction failed; no live fixture fallback.", "error_type": error_type}
    (folder / "review.json").write_text(json.dumps(result, indent=2) + "\n")
    (folder / "trace.jsonl").write_text(json.dumps({"event": "startup_or_extraction_failure", **result}) + "\n")
    (folder / "review.html").write_text('<!doctype html><html lang="en"><meta charset="utf-8"><title>Human handoff</title><h1>ESCALATE</h1><p>Human review required. Startup/extraction failed; no live fixture fallback.</p><pre>' + html.escape(json.dumps(result, indent=2)) + '</pre></html>')
    return folder

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("seed", "preflight", "check", "run"))
    parser.add_argument("--case", choices=CASES, default="reading-conflict")
    parser.add_argument("--extraction-source", choices=("fixture", "live"), default="fixture",
                        help="run: preserve the supplied exercise extraction (default), or explicitly extract live")
    args = parser.parse_args()
    try:
        if args.command == "seed":
            seed(DB)
            print(f"Reset local synthetic database: {DB}")
            return
        if args.command == "preflight":
            preflight()
            return
        if not DB.exists():
            raise ValueError("run workshop seed first")
        if args.command == "check":
            from .progress import check_progress
            label, detail, result, runtime = check_progress(args.case, DB)
            folder = review(args.case, result, runtime)
            print(f"{label}: {detail}\nOffline fixed responses; this does not evaluate prompt quality.\nReview: {folder / 'review.html'}")
            if label == "REGRESSION":
                parser.exit(1)
            return
        mode = os.getenv("WORKSHOP_MODE", "offline")
        if mode not in ("offline", "live"):
            raise ValueError("WORKSHOP_MODE must be offline or live")
        client = LiveClient() if mode == "live" else ScriptedClient(interaction_examples(args.case))
        allowance = Decimal(os.environ["WORKSHOP_SPEND_USD"]) if client.live else Decimal("0")
        if not allowance.is_finite() or allowance < 0:
            raise ValueError("finite nonnegative spending allowance required")
        extraction, remaining = extract(args.case, client, allowance, source=args.extraction_source)
        runtime = Runtime(extraction, client, Budget(allowance=remaining))
        runtime.trace("extraction", source=extraction.source, version=extraction.version, sha256=extraction.invoice_sha256, reserved_usd=str(allowance-remaining))
        packet = load_packet(args.case, DB)
        from .agent import investigate
        from .graph import build_graph
        from .tools import review_pdf_page
        nodes = Nodes(runtime, investigate, review_pdf_page, packet=packet)
        result = run(build_graph(nodes), {"candidate": extraction.candidate.model_dump(mode="json")}, nodes)
        folder = review(args.case, result, runtime)
        print(result["recommendation"] + " — human review pending")
        if result.get("handoff"):
            print(result["handoff"])
        for check in result["checks"]:
            if check["status"] != "pass":
                print(f"  {check['status']}: {check['id']} — {check.get('detail', check.get('question', ''))}")
        print(f"Review: {folder / 'review.html'}\nTrace: {folder / 'trace.jsonl'}")
    except Exception as exc:
        # Configuration/transport failures never expose environment secrets.
        if args.command == "run":
            failed_review(args.case, type(exc).__name__)
        parser.exit(1, f"ESCALATE — human review required: {type(exc).__name__}. Check local configuration/pack; no live fixture fallback.\n")

if __name__ == "__main__":
    main()
