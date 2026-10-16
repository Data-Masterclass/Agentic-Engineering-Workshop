"""New synthetic training records, not admitted customer cases or private labels."""
import copy
import hashlib
import json
from .pdf import page_reference

DATA_VERSION = "synthetic-session2-v2"
POLICY_VERSION = "selected-evidence-page-corroboration-v2"


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def case(name):
    if name not in ("order-gap", "posted-copy"):
        raise ValueError("unknown synthetic training case")
    invoice = {
        "id": name, "buyer_id": "BUYER-1", "supplier_id": "SUP-1",
        "invoice_number": "INV / 204", "po_id": None if name == "order-gap" else "PO-7",
        "requisition": "REQ-2", "product": "Calibration kit", "quantity": "10",
        "uom": "units", "unit_price": "25.00", "net": "250.00",
        "bank_account": "DE-SYNTHETIC-001",
        "page_ref": page_reference(name),
    }
    order = {
        "id": "PO-7", "buyer_id": "BUYER-1", "supplier_id": "SUP-1",
        "requisition": "REQ-2", "product": "Calibration kit", "quantity": "10",
        "uom": "unit", "unit_price": "25.00",
    }
    records = {
        "suppliers": [{"id": "SUP-1", "buyer_id": "BUYER-1", "bank_account": "DE-SYNTHETIC-001"}],
        "orders": [order],
        "receipts": [{"id": "REC-3", "order_id": "PO-7", "quantity": "10", "uom": "units", "status": "accepted"}],
        "history": [] if name == "order-gap" else [{
            "id": "LEDGER-9", "buyer_id": "BUYER-1", "supplier_id": "SUP-1",
            "invoice_number": "INV-204", "net": "250.00", "status": "posted",
        }],
        # Offline wiring uses this labelled recording; live mode reads the PDF image.
        "pages": [{"page": 1, "page_ref": invoice["page_ref"], "field": "quantity", "value": "10", "confidence": "clear", "excerpt": "Calibration kit | 10 | units", "origin": "recorded-page-observation"}],
    }
    return copy.deepcopy({"invoice": invoice, "records": records, "source_hash": digest(records)})
