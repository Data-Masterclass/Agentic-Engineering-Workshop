"""Workflow construction, routing and prepared nodes, with a safe learner fallback."""
import json
import copy
from typing import TypedDict
from langgraph.graph import StateGraph, START, END
from .runtime import Terminal, IncompleteExercise
from .schemas import InvestigationResult
from .views import flags, investigation_view
from .validation import apply_findings, recommendation, validate, cite_corrections

class State(TypedDict, total=False):
    # Serial shared case notebook. Runtime owns evidence/audit enforcement;
    # these full snapshots are replaced at prepared node boundaries, not merged.
    original_extraction: dict
    evidence: list[dict]
    correction_history: list[dict]
    candidate: dict
    validation_status: str
    checks: list
    result: dict
    handoff: str | None
    terminal: str | None
    recommendation: str

class Nodes:
    def __init__(self, runtime, investigate, review_tool=None, *, packet):
        self.__packet = copy.deepcopy(packet)
        self.runtime = runtime
        self.investigate = investigate
        self.review_tool = review_tool
        self.last_signature = None
    def checks(self, candidate):
        """Prepared validation against retained private records, never graph state."""
        return cite_corrections(validate(candidate, self.__packet), self.runtime.history)
    def validation(self, state):
        checks = self.checks(state["candidate"])
        self.runtime.trace("validation", checks=checks)
        return {**self.runtime.notebook(), "checks": flags(checks, state["candidate"]), "validation_status": recommendation(checks)}
    def policy(self, state):
        if state.get("handoff") or state.get("terminal") or self.runtime.budget.terminal:
            return "finalize"
        status = recommendation(self.checks(state["candidate"]))
        self.runtime.trace("policy", recommendation=status)
        return "investigate" if status == "NEEDS_CLARIFICATION" else "finalize"
    def investigation(self, state):
        try:
            self.runtime.budget.remaining()
            signature = json.dumps({"candidate": state["candidate"], "evidence": sorted(self.runtime.evidence)}, sort_keys=True)
            if signature == self.last_signature:
                self.runtime.budget.fail("investigation made no progress")
            self.last_signature = signature
            inspection_state = investigation_view(state, self.runtime.notebook())
            result = InvestigationResult.model_validate(self.runtime.budget.bounded(
                lambda: self.investigate(inspection_state, self.runtime.investigation_client)
            ))
            self.runtime.last_result = result
            self.runtime.trace("investigation", result=result.model_dump(mode="json"))
            return {**self.runtime.notebook(), "result": result.model_dump(mode="json"), "handoff": result.handoff}
        except Exception as exc:
            reason = safe_error(exc)
            self.runtime.budget.terminal = reason
            return {**self.runtime.notebook(), "terminal": reason, "handoff": reason}
    def route_investigation(self, state):
        """Prepared choice; learners connect this conditional edge in TODO 3."""
        return guarded_route(state, self.runtime, lambda s:
            "tools" if s["result"].get("tool_requests") else "findings"
        )

    def tools(self, state):
        try:
            requests = InvestigationResult.model_validate(state["result"]).tool_requests
            if not requests:
                self.runtime.budget.fail("tool route selected without request")
            for request in requests:
                self.runtime.review(request.model_dump(), self.review_tool)
            return self.runtime.notebook()
        except IncompleteExercise as exc:
            self.runtime.trace("unfinished_tool", handoff=str(exc))
            return {**self.runtime.notebook(), "handoff": str(exc)}
        except Exception as exc:
            reason = safe_error(exc)
            self.runtime.budget.terminal = reason
            return {**self.runtime.notebook(), "terminal": reason, "handoff": reason}
    def after_tools(self, state):
        return "finalize" if state.get("handoff") or state.get("terminal") or self.runtime.budget.terminal else "investigate"
    def findings(self, state):
        try:
            self.runtime.budget.remaining()
            result = InvestigationResult.model_validate(state["result"])
            candidate = apply_findings(state["candidate"], result.findings.model_dump(), self.runtime)
            if candidate == state["candidate"] and not result.handoff:
                self.runtime.budget.fail("findings made no progress")
            return {**self.runtime.notebook(), "candidate": candidate, "handoff": result.handoff}
        except Exception as exc:
            reason = safe_error(exc)
            self.runtime.budget.terminal = reason
            return {**self.runtime.notebook(), "terminal": reason, "handoff": reason}
    def after_findings(self, state):
        return "finalize" if state.get("terminal") or self.runtime.budget.terminal else "validate"
    def finalize(self, state):
        checks = self.checks(state["candidate"])
        status = recommendation(checks, state.get("terminal") or self.runtime.budget.terminal)
        self.runtime.trace("finalization", recommendation=status, handoff=state.get("handoff"), checks=checks)
        return {**self.runtime.notebook(), "checks": flags(checks, state["candidate"]), "validation_status": status, "recommendation": status}

# Transport errors may contain credentials/URLs. Never copy their messages to traces.
def safe_error(exc):
    if isinstance(exc, ValueError) and not isinstance(exc, Terminal):
        return "investigation rejected invalid structured output or findings"
    if isinstance(exc, Terminal):
        # Terminal messages are generated locally; avoid nested transport messages.
        return str(exc) if "operation failed:" not in str(exc) else "operation failed; live transport/output error (no fixture fallback)"
    return f"investigation failed ({type(exc).__name__})"

def prepared_graph(nodes):
    """Register nodes only; learners still supply edges and compilation."""
    graph = StateGraph(State)
    for name, function in (
        ("validate", nodes.validation), ("investigate", nodes.investigation),
        ("tools", nodes.tools), ("findings", nodes.findings),
        ("finalize", nodes.finalize),
    ):
        graph.add_node(name, function)
    return graph

def scaffold(nodes):
    """Safe launch path until TODO 3: unresolved cases call the placeholder once."""
    graph = StateGraph(State)
    graph.add_node("validate", nodes.validation)
    def unwired_investigation(state):
        update = nodes.investigation(state)
        if not update.get("handoff"):
            update["handoff"] = "investigation graph not implemented: complete Session 1 graph wiring"
        return update
    graph.add_node("investigate", unwired_investigation)
    graph.add_node("finalize", nodes.finalize)
    graph.add_edge(START, "validate")
    graph.add_conditional_edges("validate", nodes.policy, {"investigate": "investigate", "finalize": "finalize"})
    graph.add_edge("investigate", "finalize")
    graph.add_edge("finalize", END)
    return graph.compile()

def guarded_route(state, runtime, route):
    """Terminal stops all work; a handoff can still carry findings for validation."""
    if state.get("terminal") or runtime.budget.terminal:
        return "finalize"
    try:
        runtime.budget.remaining()
        choice = route(state)
        if choice not in ("tools", "findings"):
            raise ValueError("route must be tools or findings")
        if state.get("handoff"):
            result = InvestigationResult.model_validate(state.get("result", {}))
            if choice != "findings" or result.tool_requests or not result.findings.corrections:
                return "finalize"
        return choice
    except Exception:
        runtime.budget.terminal = "invalid investigation route or deadline"
        return "finalize"

def run(graph, initial, nodes):
    runtime = nodes.runtime
    # No private packet or caller-provided check internals enter graph snapshots.
    initial = {"candidate": initial["candidate"], **runtime.notebook()}
    result = initial
    try:
        for update in graph.stream(initial, {"recursion_limit": 64}, stream_mode="values"):
            result = update
        checks = nodes.checks(result["candidate"])
        terminal = result.get("terminal") or runtime.budget.terminal
        if "recommendation" not in result:
            terminal = "graph ended without prepared finalization"
        status = recommendation(checks, terminal)
        result.update(runtime.notebook(), checks=flags(checks, result["candidate"]), recommendation=status, validation_status=status, terminal=terminal)
        return result
    except Exception as exc:
        reason = safe_error(exc)
        runtime.budget.terminal = reason
        finalized = nodes.finalize({**result, "terminal": reason, "handoff": reason})
        return {**result, **finalized, "terminal": reason, "handoff": reason}


def build_graph(nodes):
    # TODO 3 (~10 min): use prepared_graph(nodes) for registered nodes.
    # Add the edges/conditional edges in docs/session1-hints.md and compile.
    # nodes.route_investigation already selects tools/findings or handoff.
    # Keep validation first, revalidation after findings and finalization last.
    return scaffold(nodes)  # Safe launch until graph wiring is implemented.
