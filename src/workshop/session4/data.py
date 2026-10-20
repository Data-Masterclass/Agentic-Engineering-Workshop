"""Synthetic follow-up cases; expected actions remain in tests, not model inputs."""
import copy
import json
from pathlib import Path

from workshop.session2.data import case, digest
from workshop.session2.pdf import page_reference

DATA_VERSION = "synthetic-session4-v1"
SCENARIOS = ("supplier-request", "request-pending", "internal-receipts", "posted-copy")
CORRESPONDENCE = Path(__file__).with_name("assets") / "correspondence.json"


def _check_scenario(name):
    if name not in SCENARIOS:
        raise ValueError("unknown synthetic follow-up scenario")


def invoice_packet(name):
    """Load a detached Session 2 packet without adding follow-up outcome labels."""
    _check_scenario(name)
    if name == "posted-copy":
        return case("posted-copy")
    packet = case("order-gap")
    invoice = packet["invoice"]
    invoice["id"] = "CP4-102" if name == "internal-receipts" else "CP4-101"
    invoice["po_id"] = "PO-7"
    invoice["page_ref"] = page_reference(invoice["id"])
    page = packet["records"]["pages"][0]
    page["page_ref"] = copy.deepcopy(invoice["page_ref"])
    if name == "internal-receipts":
        packet["records"]["receipts"][0]["quantity"] = "6"
    else:
        page.update(value="", confidence="unavailable", excerpt="[unreadable]")
    packet["source_hash"] = digest(packet["records"])
    return packet


def correspondence_snapshot(name):
    """Select mock mail server-side; the tool cannot choose another snapshot."""
    _check_scenario(name)
    fixture = json.loads(CORRESPONDENCE.read_text())
    if fixture["version"] != DATA_VERSION:
        raise ValueError("unknown correspondence fixture version")
    key = "current-thread" if name == "request-pending" else "previous-thread"
    snapshot = copy.deepcopy(fixture["snapshots"][key])
    snapshot["contact"] = copy.deepcopy(fixture["contact"])
    return snapshot
