"""Deterministic teaching policy. Citations are provenance, not truth."""
from decimal import Decimal, ROUND_HALF_UP
from .schemas import Check, Finding, Invoice

CENT = Decimal("0.01")

def validate(candidate, packet):
    invoice = Invoice.model_validate(candidate)
    checks = []
    def check(id, ok, detail, blocking=False):
        checks.append(Check(id=id, status="pass" if ok else ("blocking" if blocking else "unresolved"), detail=detail).model_dump())
    coverage = {r["dataset"]: r["status"] for r in packet["coverage"]}
    supplier = [r for r in packet["suppliers"] if r["id"] == invoice.supplier_id]
    check("supplier", len(supplier) == 1, "Selected supplier identity must match one supplied record.")
    if len(supplier) == 1:
        check("bank", invoice.bank_account == supplier[0]["bank_account"], "Bank must match selected supplier master.", blocking=True)
        check("supplier_currency", invoice.currency == supplier[0]["currency"], "Supplier currency must match.", blocking=True)
    orders = [r for r in packet["purchase_orders"] if r["id"] == invoice.po_id]
    check("order", len(orders) == 1, "One selected PO must match.")
    if len(orders) == 1:
        check("order_supplier", orders[0]["supplier_id"] == invoice.supplier_id, "PO supplier must match invoice.", blocking=True)
        check("order_currency", orders[0]["currency"] == invoice.currency, "PO currency must match invoice.", blocking=True)
    check("receipt_coverage", coverage.get("receipts") == "complete", "Complete selected receipt coverage is mandatory.")
    check("duplicate_coverage", coverage.get("duplicate_scope") == "complete", "Complete supplier/invoice-number duplicate scope is mandatory.")
    duplicates = [r for r in packet["invoice_history"] if r["supplier_id"] == invoice.supplier_id and r["invoice_number"] == invoice.invoice_number]
    check("duplicate", not duplicates, "An exact supplier/invoice-number history match blocks approval.", blocking=bool(duplicates))
    check("line_identity", len({l.id for l in invoice.lines}) == len(invoice.lines), "Line IDs must be unique.")
    selected_lines = [r for r in packet["po_lines"] if r["po_id"] == invoice.po_id]
    check("line_coverage", {l.id for l in invoice.lines} == {r["line_id"] for r in selected_lines}, "Invoice lines must cover exactly the selected PO lines in this provisional pack.")
    for line in invoice.lines:
        prefix = f"lines.{line.id}"
        rows = [r for r in selected_lines if r["line_id"] == line.id]
        check(prefix + ".match", len(rows) == 1, "One supplied PO line must match.")
        if len(rows) == 1:
            po = rows[0]
            check(prefix + ".quantity", line.quantity == Decimal(po["quantity"]), "Quantity conflicts are reading candidates; PO agreement alone cannot correct the invoice.")
            check(prefix + ".price", line.unit_price == Decimal(po["unit_price"]), "Invoice unit price must match PO price.")
            check(prefix + ".uom", line.uom == po["uom"], "Units must match without implicit conversions.")
            check(prefix + ".description", line.description == po["description"], "Description must match the selected item in this pack.")
        received = [r for r in packet["receipts"] if r["po_id"] == invoice.po_id and r["line_id"] == line.id]
        qty = sum((Decimal(r["quantity"]) for r in received if r["uom"] == line.uom), Decimal(0))
        check(prefix + ".receipt", coverage.get("receipts") == "complete" and qty >= line.quantity and all(r["uom"] == line.uom for r in received), "Supplied receipts and complete coverage must support invoice quantity/UOM.")
        check(prefix + ".net", (line.quantity * line.unit_price).quantize(CENT, rounding=ROUND_HALF_UP) == line.net, "Quantity times unit price must equal line net (EUR cents, half up).")
        check(prefix + ".precision", all(x == x.quantize(CENT) for x in (line.unit_price, line.net)), "Monetary values must use EUR cent precision.")
    check("net", sum((l.net for l in invoice.lines), Decimal(0)) == invoice.net, "Sum of line nets must equal invoice net.")
    check("tax", (invoice.net * Decimal("0.19")).quantize(CENT, rounding=ROUND_HALF_UP) == invoice.tax, "Provisional pack uses explicit 19% VAT, half up.")
    check("gross", invoice.net + invoice.tax == invoice.gross, "Net plus tax must equal gross.")
    check("money_precision", all(x == x.quantize(CENT) for x in (invoice.net, invoice.tax, invoice.gross)), "Invoice monetary values must use EUR cent precision.")
    return checks

def recommendation(checks, terminal=None):
    if terminal or any(c["status"] == "blocking" for c in checks):
        return "ESCALATE"
    if not checks or any(c["status"] != "pass" for c in checks):
        return "NEEDS_CLARIFICATION"
    return "READY_FOR_APPROVAL"

def apply_findings(candidate, raw, runtime):
    """Accept a supported reading proposal atomically; keep original untouched."""
    finding = Finding.model_validate(raw)
    if any(id not in runtime.evidence for id in finding.evidence_ids):
        raise ValueError("unknown evidence ID")
    invoice = Invoice.model_validate(candidate).model_copy(deep=True)
    changes = []
    for correction in finding.corrections:
        evidence = runtime.evidence.get(correction.evidence_id)
        if not evidence or evidence.confidence != "clear" or evidence.field != correction.field or evidence.value != correction.value:
            raise ValueError("unsupported or ambiguous correction")
        if any(e.field == evidence.field and e.confidence == "clear" and e.value != evidence.value for e in runtime.evidence.values()):
            raise ValueError("conflicting direct readings remain unresolved")
        parts = correction.field.split(".")
        if len(parts) != 3 or parts[0] != "lines" or parts[2] != "quantity":
            raise ValueError("only a supported line quantity reading can be corrected in Session 1")
        matches = [l for l in invoice.lines if l.id == parts[1]]
        if len(matches) != 1:
            raise ValueError("unknown or ambiguous line ID")
        line = matches[0]
        value = Decimal(correction.value)
        before = str(line.quantity)
        line.quantity = value
        changes.append({"field": correction.field, "before": before, "after": correction.value, "evidence_id": correction.evidence_id, "reason": finding.note})
    result = Invoice.model_validate(invoice.model_dump()).model_dump(mode="json")
    runtime.history.extend(changes)
    runtime.trace("findings_applied", changes=changes, note=finding.note)
    return result


def cite_corrections(checks, history):
    """Attach accepted reading provenance; a citation does not certify accuracy."""
    for change in history:
        prefix = change["field"].rsplit(".", 1)[0]
        for check in checks:
            if check["id"] in (prefix + ".quantity", prefix + ".receipt", prefix + ".net"):
                if change["evidence_id"] not in check["evidence_ids"]:
                    check["evidence_ids"].append(change["evidence_id"])
    return checks
