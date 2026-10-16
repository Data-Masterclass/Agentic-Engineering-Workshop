"""Rebuild redistributable synthetic PDFs and extraction/observation fixtures.
Run from repository root: python data/build_demo.py (dev dependencies required).
"""
import hashlib
import json
from pathlib import Path
from reportlab.pdfgen.canvas import Canvas
from reportlab.lib.pagesizes import A4

DATA = Path(__file__).resolve().parent
for index, case in enumerate(("matching", "reading-conflict", "missing-evidence"), 1):
    pdf = DATA / "invoices" / f"{case}.pdf"
    c = Canvas(str(pdf), pagesize=A4, invariant=1)
    c.setTitle("Synthetic workshop invoice " + case)
    c.setFont("Helvetica-Bold", 20)
    c.drawString(48, 780, "INVOICE")
    c.setFont("Helvetica", 10)
    for y, text in [(752, "PROVISIONAL DEMONSTRATION PACK - SYNTHETIC DATA"), (715, "Supplier: Synthetic Office Supply (SUP-001)"), (695, f"Invoice number: INV-{index:03d}    Date: 2026-10-01"), (675, f"Purchase order: PO-{index:03d}    Currency: EUR"), (655, "Bank account: DEMO-BANK-001 (fictional)")]:
        c.drawString(48, y, text)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(48, 610, "Line / Description")
    c.drawString(260, 610, "Qty")
    c.drawString(310, 610, "UOM")
    c.drawString(370, 610, "Price EUR")
    c.drawString(470, 610, "Net EUR")
    c.line(48, 602, 548, 602)
    c.setFont("Helvetica", 11)
    c.drawString(48, 580, "L1 / Archive boxes")
    c.drawString(260, 580, "10" if case != "missing-evidence" else "[unreadable]")
    c.drawString(330, 580, "EA")
    c.drawString(390, 580, "12.00")
    c.drawString(485, 580, "120.00")
    c.drawString(370, 520, "Net: EUR 120.00")
    c.drawString(370, 500, "VAT 19%: EUR 22.80")
    c.setFont("Helvetica-Bold", 12)
    c.drawString(370, 475, "Total: EUR 142.80")
    c.setFont("Helvetica", 10)
    c.drawString(48, 410, "No payment or accounting action is authorized by this invoice.")
    if case == "missing-evidence":
        c.drawString(48, 390, "Source quantity is unavailable; do not infer it from other records.")
    c.drawString(48, 48, "Synthetic training material - freely redistributable - Page 1 of 1")
    c.save()
    digest = hashlib.sha256(pdf.read_bytes()).hexdigest()
    ref = {"invoice_id": case, "page": 1, "sha256": digest}
    invoice = {"id": case, "supplier_id": "SUP-001", "invoice_number": f"INV-{index:03d}", "po_id": f"PO-{index:03d}", "bank_account": "DEMO-BANK-001", "currency": "EUR", "net": "120.00", "tax": "22.80", "gross": "142.80", "lines": [{"id": "L1", "description": "Archive boxes", "quantity": "100" if case != "matching" else "10", "uom": "EA", "unit_price": "12.00", "net": "120.00", "page_ref": ref}]}
    extraction = {"version": "synthetic-extraction-v1", "source": "verified-fixture", "invoice_sha256": digest, "original": invoice, "candidate": invoice}
    (DATA / "extractions" / f"{case}.json").write_text(json.dumps(extraction, indent=2) + "\n")
    evidence = {"id": f"{case}:page1:quantity", "page_ref": ref, "field": "lines.L1.quantity", "value": "10" if case != "missing-evidence" else "", "confidence": "clear" if case != "missing-evidence" else "unavailable", "excerpt": "L1 Archive boxes | 10 EA | EUR 12.00 | EUR 120.00" if case != "missing-evidence" else "Quantity is [unreadable] in source page.", "origin": "recorded-page-observation"}
    (DATA / "observations" / f"{case}.json").write_text(json.dumps([evidence], indent=2) + "\n")
