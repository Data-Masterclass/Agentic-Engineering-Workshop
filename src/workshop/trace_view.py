"""Offline teaching view of recorded workflow events; no model requests."""
import argparse
import html
import json
from pathlib import Path
import re


LABELS = {
    "extraction": "Select extraction",
    "validation": "Validate business rules",
    "policy": "Choose workflow route",
    "model_result": "Model proposes next action",
    "investigation": "Investigation returns",
    "page_review": "Review PDF page",
    "findings_applied": "Accept supported findings",
    "unfinished_tool": "Participant tool remains unfinished",
    "finalization": "Finalize recommendation",
    "startup_or_extraction_failure": "Startup or extraction failed",
    "tool_requested": "Investigator requests evidence",
    "tool_result": "Register tool evidence",
    "page_read": "Read selected PDF page",
    "answer": "Investigator hands back its answer",
    "terminal": "Execution stopped",
}
KNOWN_TOOLS = {"review_pdf_page", "get_supplier", "search_purchase_orders", "get_purchase_order", "get_receipts", "get_invoice_history"}
RECOMMENDATIONS = {"READY_FOR_APPROVAL", "NEEDS_CLARIFICATION", "ESCALATE"}


def objects(value):
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def numeric(value):
    """Only short decimal readings; never interpolate arbitrary stored strings."""
    text = str(value) if isinstance(value, (str, int, float)) and not isinstance(value, bool) else ""
    return text if re.fullmatch(r"-?[0-9]{1,10}(?:\.[0-9]{1,6})?", text) else "withheld"


def changes_text(changes):
    rows = objects(changes)
    parts = [f"{len(rows)} accepted correction(s)"]
    for change in rows:
        # Session 1 supports quantity corrections only. Do not expose raw IDs,
        # notes, descriptions or unrelated fields from an imported trace.
        field = change.get("field")
        if isinstance(field, str) and re.fullmatch(r"lines\.[^.]{1,40}\.quantity", field):
            parts.append(f"Line quantity: {numeric(change.get('before'))} → {numeric(change.get('after'))}")
    return "; ".join(parts)


def describe(event):
    kind = event.get("event")
    if kind in ("validation", "finalization"):
        checks = objects(event.get("checks"))
        detail = ", ".join(f"{sum(c.get('status') == status for c in checks)} {status}" for status in ("pass", "unresolved", "blocking"))
        recommendation = event.get("recommendation")
        if isinstance(recommendation, str) and recommendation in RECOMMENDATIONS:
            detail += f"; recommendation: {recommendation}"
        if event.get("handoff"):
            detail += "; human handoff recorded"
        return detail
    if kind == "policy":
        status = event.get("recommendation")
        return status if isinstance(status, str) and status in RECOMMENDATIONS else "Route decision recorded"
    if kind in ("model_result", "investigation"):
        result = event.get("result")
        result = result if isinstance(result, dict) else {}
        findings = result.get("findings")
        findings = findings if isinstance(findings, dict) else {}
        detail = f"{len(objects(result.get('tool_requests')))} tool request(s); {len(objects(findings.get('corrections')))} proposed correction(s)"
        return detail + ("; human handoff requested" if result.get("handoff") else "")
    if kind == "page_review":
        evidence = objects(event.get("evidence"))
        request = event.get("request")
        request = request if isinstance(request, dict) else {}
        page = request.get("page")
        detail = "review_pdf_page"
        if type(page) is int and 1 <= page <= 20:
            detail += f" · page {page}"
        detail += f"; {len(evidence)} observation(s)"
        detail += f"; {sum(e.get('confidence') == 'clear' for e in evidence)} clear"
        return detail
    if kind in ("tool_requested", "tool_result"):
        evidence = event.get("evidence")
        evidence = evidence if isinstance(evidence, dict) else {}
        name = event.get("name") if kind == "tool_requested" else evidence.get("tool")
        name = name if isinstance(name, str) and name in KNOWN_TOOLS else "unrecognised tool"
        return name if kind == "tool_requested" else f"{name}; {len(objects(evidence.get('records')))} returned record(s)"
    if kind == "page_read":
        observations = objects(event.get("observations"))
        return f"{len(observations)} observation(s); {sum(row.get('confidence') == 'clear' for row in observations)} clear"
    if kind == "answer":
        return "Human handoff requested" if event.get("handoff") else "Answer recorded; deterministic validation remains authoritative"
    if kind == "terminal":
        return "Run stopped; details remain in the local review report"
    if kind == "findings_applied":
        return changes_text(event.get("changes"))
    if kind == "extraction":
        return {"verified-fixture": "Verified fixture selected", "live-vlm": "Live extraction selected"}.get(event.get("source") if isinstance(event.get("source"), str) else None, "Extraction selected")
    return "See the local human review report for the outcome"


def render(events):
    """Build a deliberately narrow projection, never embed the source JSON."""
    rows = []
    hidden = 0
    for step, event in enumerate(events, 1):
        kind = event.get("event") if isinstance(event, dict) else None
        if not isinstance(kind, str) or kind not in LABELS:
            hidden += 1
            continue
        rows.append(f"<tr><td>{step}</td><th scope='row'>{html.escape(LABELS[kind])}</th><td>{html.escape(describe(event))}</td></tr>")
    return """<!doctype html><html lang="en"><meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Workshop workflow trace</title><style>
body{font:16px system-ui;max-width:1050px;margin:32px auto;padding:20px;color:#182331;background:#f7f9fc}
table{border-collapse:collapse;width:100%;background:white}td,th{padding:12px;border:1px solid #ccd5df;text-align:left;vertical-align:top}
caption{text-align:left;margin:18px 0;font-weight:bold}p{line-height:1.6}code{background:#e7edf5;padding:2px 5px}
</style><h1>Workshop workflow trace</h1>
<p>This local event sequence shows validation, model proposals, evidence tools, PDF review and accepted corrections.
Model proposals and accepted corrections are separate steps. The original human review report remains the source for evidence citations and the final recommendation.</p>
<p>Recorded event order only: no span durations or actual provider costs are recorded here.
Repeated model-result and investigation events can describe the same model operation.
Prompts, private reasoning, excerpts, identifiers and free-text notes are omitted.</p>
<table><caption>Recorded workflow events</caption><thead><tr><th>Step</th><th>Event</th><th>Outcome</th></tr></thead><tbody>""" + "".join(rows) + f"</tbody></table><p>{hidden} unrecognised or malformed event(s) omitted.</p></html>"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace", type=Path, help="Existing local trace.jsonl")
    parser.add_argument("--output", type=Path, help="HTML destination (default: trace-view.html beside trace)")
    args = parser.parse_args(argv)
    output = args.output or args.trace.with_name("trace-view.html")
    if output.resolve() == args.trace.resolve():
        parser.error("HTML destination must differ from the source trace")
    with args.trace.open("rb") as source:
        raw = source.read(2_000_001)
    if len(raw) > 2_000_000:
        parser.error("trace exceeds 2 MB teaching-view limit")
    try:
        lines = [line for line in raw.decode("utf-8").splitlines() if line.strip()]
        if len(lines) > 5000:
            parser.error("trace exceeds 5000 event teaching-view limit")
        events = [json.loads(line) for line in lines]
    except (ValueError, UnicodeError):
        parser.error("trace must contain UTF-8 JSON events, one per line")
    output.write_text(render(events), encoding="utf-8")
    print(f"Trace view: {output}")


if __name__ == "__main__":
    main()
