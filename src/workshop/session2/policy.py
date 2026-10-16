"""Teaching policy rechecks only actually obtained records, never model claims."""
from decimal import Decimal
from .data import digest
from .tools import normalized_number


def unit(value):
    return "unit" if value in ("unit", "units") else value


def validate(invoice, evidence):
    checks = []
    def check(name, ok, detail, blocking=False, ids=()):
        checks.append({"id": name, "status": "pass" if ok else ("blocking" if blocking else "unresolved"), "detail": detail, "evidence_ids": list(ids)})
    def rows(tool):
        return [(r, e["id"]) for e in evidence if e["tool"] == tool for r in e["records"]]
    if any(digest(e["records"]) != e["record_hash"] for e in evidence):
        raise ValueError("evidence changed after retrieval")
    suppliers = [(r, eid) for r, eid in rows("get_supplier") if r["id"] == invoice["supplier_id"] and r["buyer_id"] == invoice["buyer_id"]]
    pages = [(r, eid) for r, eid in rows("review_pdf_page") if r["page_ref"] == invoice["page_ref"] and r["field"] == "quantity" and r["confidence"] == "clear"]
    supported_quantity = bool(pages) and all(Decimal(r["value"]) == Decimal(invoice["quantity"]) for r, _ in pages)
    check("source_quantity", supported_quantity, "Obtain direct PDF quantity corroboration; extracted values and business agreement alone are insufficient.", ids=[eid for _, eid in pages])
    check("supplier_bank", len(suppliers) == 1 and suppliers[0][0]["bank_account"] == invoice["bank_account"], "One unambiguous selected supplier bank must match.", blocking=len(suppliers) == 1, ids=[eid for _, eid in suppliers])
    orders = [(r, eid) for r, eid in rows("get_purchase_order") if r["buyer_id"] == invoice["buyer_id"] and r["supplier_id"] == invoice["supplier_id"] and r["requisition"] == invoice["requisition"] and r["product"] == invoice["product"] and (invoice["po_id"] is None or r["id"] == invoice["po_id"])]
    association = None
    if len(orders) == 1:
        order, eid = orders[0]
        association = {"order_id": order["id"], "evidence_id": eid, "basis": "buyer/supplier/requisition/product agreement"}
        aligned = Decimal(order["quantity"]) == Decimal(invoice["quantity"]) and Decimal(order["unit_price"]) == Decimal(invoice["unit_price"]) and unit(order["uom"]) == unit(invoice["uom"])
        check("order_terms", aligned, "Quantity, unit and unit price must agree; no source rewriting.", blocking=not aligned, ids=[eid])
        receipts = [(r, eid) for r, eid in rows("get_receipts") if r["order_id"] == order["id"]]
        qty = sum((Decimal(r["quantity"]) for r, _ in receipts if r["status"] == "accepted" and unit(r["uom"]) == unit(invoice["uom"])), Decimal(0))
        check("receipt_support", qty >= Decimal(invoice["quantity"]), "Selected accepted receipts can support quantity, but do not establish full coverage.", ids=[eid for _, eid in receipts])
    else:
        check("order_terms", False, "Retrieve one unambiguous supported order association.")
        check("receipt_support", False, "Receipt support requires an established order association.")
    hits = [(r, eid) for r, eid in rows("get_invoice_history") if r["buyer_id"] == invoice["buyer_id"] and r["supplier_id"] == invoice["supplier_id"] and normalized_number(r["invoice_number"]) == normalized_number(invoice["invoice_number"]) and Decimal(r["net"]) == Decimal(invoice["net"]) and r["status"] in ("posted", "paid")]
    check("posted_copy", False, "A corroborated posted/paid match needs human escalation." if hits else "No positive match obtained; selected search cannot establish absence.", blocking=bool(hits), ids=[eid for _, eid in hits])
    check("arithmetic", Decimal(invoice["quantity"]) * Decimal(invoice["unit_price"]) == Decimal(invoice["net"]), "Quantity times price must equal net.")
    check("mandatory_coverage", False, "Selected sources with unknown as-of do not establish mandatory completeness.")
    recommendation = "ESCALATE" if any(c["status"] == "blocking" for c in checks) else "NEEDS_CLARIFICATION"
    return {"checks": checks, "recommendation": recommendation, "association": association}
