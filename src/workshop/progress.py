"""Offline progress checks, never a reasoning agent or graph solution."""
from .pack import fixture, load_packet
from .runtime import Runtime, ScriptedClient
from .scripts import interaction_examples
from .graph import Nodes, run
from .validation import recommendation


def assess(case, result, runtime):
    """Compare supported outcomes using authoritative evidence and audit data."""
    checks = next((e["checks"] for e in reversed(runtime.events) if e["event"] == "finalization"), [])
    terminal = result.get("terminal") or runtime.budget.terminal
    status = recommendation(checks, terminal)
    events = [e["event"] for e in runtime.events]
    if status != result.get("recommendation") or "finalization" not in events:
        return "REGRESSION", "Prepared finalization/recommendation is missing or inconsistent."
    if terminal:
        return "REGRESSION", "The offline case terminated; inspect its checks and trace."
    if case == "matching":
        if status == "READY_FOR_APPROVAL" and "investigation" not in events and runtime.budget.models == runtime.budget.tools == 0:
            return "SUPPORTED_OUTCOME", "Matching invoice bypasses investigation."
        return "REGRESSION", "Matching invoice must pass without investigation."
    handoff = result.get("handoff") or ""
    if "investigation not implemented:" in handoff or "investigation graph not implemented:" in handoff or "PDF review tool not implemented:" in handoff:
        if status == "NEEDS_CLARIFICATION" and result["candidate"] == runtime.extraction.candidate.model_dump(mode="json") and not runtime.history:
            return "NOT_IMPLEMENTED_YET", "The PDF tool, investigation agent or graph is still unfinished; this is not a regression."
        return "REGRESSION", "The unfinished graph changed the candidate or its recommendation."
    if case == "reading-conflict":
        supported = any(
            change["field"] == "lines.L1.quantity" and change["before"] == "100" and change["after"] == "10"
            and change["evidence_id"] in runtime.evidence
            and runtime.evidence[change["evidence_id"]].confidence == "clear"
            and runtime.evidence[change["evidence_id"]].value == "10"
            for change in runtime.history
        )
        if status == "READY_FOR_APPROVAL" and supported and events.count("validation") >= 2 and "page_review" in events:
            return "SUPPORTED_OUTCOME", "Direct page evidence, accepted correction and revalidation support the recommendation."
        return "REGRESSION", "Recoverable case needs supported page evidence, an accepted correction and revalidation."
    if case == "missing-evidence":
        if status == "NEEDS_CLARIFICATION" and handoff and not runtime.history and "page_review" in events:
            return "SUPPORTED_OUTCOME", "Unavailable evidence remains unresolved with a human handoff."
        return "REGRESSION", "Missing evidence must remain unresolved with an explained handoff."
    raise ValueError("unknown progress case")


def check_progress(case, db):
    # Always offline, even if the shell configured live mode. No LiveClient exists here.
    from .agent import investigate
    from .graph import build_graph
    from .tools import review_pdf_page
    extraction = fixture(case)
    runtime = Runtime(extraction, ScriptedClient(interaction_examples(case)))
    state = {"candidate": extraction.candidate.model_dump(mode="json")}
    nodes = Nodes(runtime, investigate, review_pdf_page, packet=load_packet(case, db))
    result = run(build_graph(nodes), state, nodes)
    label, detail = assess(case, result, runtime)
    return label, detail, result, runtime
