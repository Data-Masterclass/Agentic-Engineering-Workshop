"""Explicit Session 1 projection; not a security sandbox on a learner laptop."""
import copy
from typing import TypedDict
from .schemas import Invoice

class InvestigationInput(TypedDict):
    candidate: dict
    original_extraction: dict
    checks: list[dict]
    questions: list[dict]
    evidence: list[dict]
    correction_history: list[dict]

QUESTIONS = {
    "supplier": "Recheck the printed supplier identity; business verification remains with validation.",
    "bank": "A blocking payment-account discrepancy needs human review.",
    "supplier_currency": "Recheck the currency printed on the invoice.",
    "order": "Recheck the printed order reference; do not invent an order match.",
    "order_supplier": "A blocking supplier/order discrepancy needs human review.",
    "order_currency": "Recheck the currency printed on the invoice.",
    "receipt_coverage": "Required receipt evidence is unavailable to validation; PDF review cannot supply business records.",
    "duplicate_coverage": "Required duplicate-check evidence is unavailable to validation; hand off the unresolved gap.",
    "duplicate": "A blocking duplicate concern needs human review.",
    "line_identity": "Recheck the invoice's line identities.",
    "line_coverage": "Recheck the printed invoice lines; business matching remains with validation.",
    "net": "Recheck the printed invoice net and line amounts.",
    "tax": "Recheck the printed tax rate and amount.",
    "gross": "Recheck the printed net, tax and gross amounts.",
    "money_precision": "Recheck the precision of printed monetary amounts.",
}
LINE_QUESTIONS = {
    "match": "Recheck the printed item identity",
    "quantity": "Recheck the printed quantity",
    "price": "Recheck the printed unit price",
    "uom": "Recheck the printed unit of measure",
    "description": "Recheck the printed item description",
    "receipt": "Recheck the printed quantity and unit; receipt verification remains with validation",
    "net": "Recheck the printed quantity, unit price and line net",
    "precision": "Recheck the precision of printed monetary amounts",
}

def flags(checks, candidate):
    """Rebuild known identifiers/questions; discard details, passing checks and nesting."""
    invoice = Invoice.model_validate(candidate)
    known = dict(QUESTIONS)
    for line in invoice.lines:
        for suffix, question in LINE_QUESTIONS.items():
            known[f"lines.{line.id}.{suffix}"] = f"{question} for invoice line {line.id} on page {line.page_ref.page}."
    output = []
    for check in checks:
        if check.get("status") not in ("unresolved", "blocking"):
            continue
        raw_id = check.get("id")
        id = raw_id if isinstance(raw_id, str) and raw_id in known else "unresolved_check"
        output.append({"id": id, "status": check["status"], "question": known.get(id, "An unresolved check needs human clarification; do not infer missing business evidence.")})
    return output

def investigation_view(state, notebook) -> InvestigationInput:
    """Allowlist fields, using authoritative actual-page/audit snapshots."""
    candidate = Invoice.model_validate(state["candidate"]).model_dump(mode="json")
    flagged = flags(state.get("checks", []), candidate)
    return {
        "candidate": candidate,
        "original_extraction": copy.deepcopy(notebook["original_extraction"]),
        "checks": [{"id": c["id"], "status": c["status"]} for c in flagged],
        "questions": [{"check_id": c["id"], "question": c["question"]} for c in flagged],
        "evidence": copy.deepcopy(notebook["evidence"]),
        "correction_history": copy.deepcopy(notebook["correction_history"]),
    }

class InvestigationClient:
    """Only the supported ask operation; no business records/client/clock accessors."""
    __slots__ = ("__ask",)
    def __init__(self, ask):
        self.__ask = ask
    def ask(self, prompt, state):
        return self.__ask(prompt, state)
