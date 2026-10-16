"""Prepared selected context is loaded for private deterministic validation."""
import hashlib
import json
import sqlite3
from pathlib import Path
from .schemas import Extraction, Evidence

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
CASES = ("matching", "reading-conflict", "missing-evidence")

def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def seed(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    sql = (DATA / "seed.sql").read_text()
    with sqlite3.connect(path) as db:
        db.executescript(sql)

def load_packet(invoice_id: str, path: Path):
    if invoice_id not in CASES:
        raise ValueError("unknown demonstration case")
    with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as db:
        db.row_factory = sqlite3.Row
        packet = {}
        for table in ("suppliers", "purchase_orders", "po_lines", "receipts", "invoice_history", "coverage"):
            # Table names are a fixed allowlist; values are bound parameters.
            packet[table] = [dict(r) for r in db.execute(f"SELECT * FROM {table} WHERE case_id = ?", (invoice_id,))]
        return packet

def fixture(invoice_id: str):
    if invoice_id not in CASES:
        raise ValueError("unknown case")
    result = Extraction.model_validate_json((DATA / "extractions" / f"{invoice_id}.json").read_text())
    path = DATA / "invoices" / f"{invoice_id}.pdf"
    if result.invoice_sha256 != sha256(path):
        raise ValueError("invoice hash differs from verified extraction")
    if result.original != result.candidate:
        raise ValueError("fixture must preserve the initial candidate")
    for line in result.original.lines:
        if line.page_ref.invoice_id != invoice_id or line.page_ref.sha256 != result.invoice_sha256:
            raise ValueError("invalid extraction page reference")
    return result

def observations(invoice_id, page):
    if invoice_id not in CASES:
        raise ValueError("unknown case")
    records = json.loads((DATA / "observations" / f"{invoice_id}.json").read_text())
    return [Evidence.model_validate(r) for r in records if r["page_ref"]["page"] == page]
