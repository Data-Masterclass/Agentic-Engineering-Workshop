"""Rebuild newly authored, deterministic synthetic invoices (development dependency)."""
import hashlib
import json
from pathlib import Path
from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas


def main():
    assets = Path(__file__).resolve().parents[2] / "src/workshop/session2/assets"
    assets.mkdir(exist_ok=True)
    manifest = {}
    for name in ("order-gap", "posted-copy"):
        path = assets / f"{name}.pdf"
        doc = canvas.Canvas(str(path), pagesize=A4, invariant=True)
        doc.setTitle("Synthetic workshop invoice " + name)
        doc.setAuthor("Agent Engineering Workshop")
        width, height = A4
        doc.setFillColor(HexColor("#152B3C"))
        doc.rect(0, height - 140, width, 140, fill=1, stroke=0)
        doc.setFillColor(HexColor("#79DFC0"))
        doc.setFont("Helvetica-Bold", 11)
        doc.drawString(45, height - 42, "AGENT ENGINEERING WORKSHOP / SYNTHETIC FIXTURE")
        doc.setFillColor(HexColor("#FFFFFF"))
        doc.setFont("Helvetica-Bold", 28)
        doc.drawString(45, height - 87, "INVOICE" if name == "order-gap" else "INVOICE COPY")
        doc.setFont("Helvetica", 12)
        doc.drawString(45, height - 116, "Invoice number: INV / 204     |     Issue date: 15 October 2026")
        doc.setFillColor(HexColor("#152B3C"))
        doc.setFont("Helvetica-Bold", 13)
        doc.drawString(45, 662, "Workshop Supply Co. (fictional)")
        doc.setFont("Helvetica", 11)
        for y, text in [(640, "Supplier ID: SUP-1"), (620, "Bank account: DE-SYNTHETIC-001"), (589, "Bill to: Training Buyer (fictional)"), (569, "Buyer ID: BUYER-1"), (538, "Requisition: REQ-2"), (518, "PO reference: " + ("-" if name == "order-gap" else "PO-7"))]:
            doc.drawString(45, y, text)
        doc.setFillColor(HexColor("#EAF3F4"))
        doc.rect(45, 440, width - 90, 32, fill=1, stroke=0)
        doc.setFillColor(HexColor("#152B3C"))
        doc.setFont("Helvetica-Bold", 10)
        for x, label in [(54, "Description"), (275, "Quantity"), (340, "Unit"), (400, "Unit price"), (484, "Net EUR")]:
            doc.drawString(x, 452, label)
        doc.setFont("Helvetica", 11)
        for x, text in [(54, "Calibration kit"), (294, "10"), (340, "units"), (416, "25.00"), (493, "250.00")]:
            doc.drawString(x, 414, text)
        doc.setStrokeColor(HexColor("#D7E4E8"))
        doc.line(45, 394, width - 45, 394)
        for y, label, value in [(359, "Net total EUR", "250.00"), (335, "VAT 19% EUR", "47.50"), (300, "Gross total EUR", "297.50")]:
            doc.setFont("Helvetica-Bold" if y == 300 else "Helvetica", 12)
            doc.drawString(350, y, label)
            doc.drawRightString(width - 45, y, value)
        doc.setFont("Helvetica", 10)
        doc.drawString(45, 211, "Fictional training document. No payment or external action is requested.")
        if name == "posted-copy":
            doc.drawString(45, 190, "Copy for review; consult the supplied selected history records.")
        doc.setStrokeColor(HexColor("#D7E4E8"))
        doc.line(45, 91, width - 45, 91)
        doc.setFont("Helvetica", 9)
        doc.drawString(45, 72, "Newly authored synthetic material / fixture v2")
        doc.drawRightString(width - 45, 72, "Page 1 of 1")
        doc.save()
        manifest[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    (assets / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")


if __name__ == "__main__":
    main()
