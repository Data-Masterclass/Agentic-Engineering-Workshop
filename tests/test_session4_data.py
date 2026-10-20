import copy
import hashlib
import io
import json

from PIL import Image
import pytest

from workshop.session2 import pdf
from workshop.session2.data import case, digest
from workshop.session2.policy import validate
from workshop.session2.tools import EvidenceTools
from workshop.session4.data import SCENARIOS, correspondence_snapshot, invoice_packet
from workshop.session4.tools import CorrespondenceLookup, TOOL


def collect_evidence(packet):
    tools = EvidenceTools(packet)
    try:
        for name, args in [
            ("review_pdf_page", {"page": 1}),
            ("get_supplier", {"supplier_id": "SUP-1"}),
            ("get_purchase_order", {"order_id": "PO-7"}),
            ("get_receipts", {"order_id": "PO-7"}),
            ("get_invoice_history", {"supplier_id": "SUP-1", "invoice_number": "INV / 204"}),
        ]:
            tools.execute(name, args)
        return copy.deepcopy(tools.evidence)
    finally:
        tools.close()


def test_correspondence_alone_distinguishes_first_two_scenarios():
    first = invoice_packet("supplier-request")
    second = invoice_packet("request-pending")
    assert first == second
    assert first["invoice"]["id"] == "CP4-101"
    assert first["source_hash"] == digest(first["records"])
    first["records"]["suppliers"][0]["id"] = "changed"
    assert invoice_packet("supplier-request") == second
    assert correspondence_snapshot("supplier-request") != correspondence_snapshot("request-pending")
    assert invoice_packet("posted-copy") == case("posted-copy")


@pytest.mark.parametrize("name", SCENARIOS[:3])
def test_nonblocking_packets_work_with_existing_evidence_and_policy(name):
    packet = invoice_packet(name)
    original = copy.deepcopy(packet)
    evidence = collect_evidence(packet)
    result = validate(packet["invoice"], evidence)
    assert packet == original
    assert result["recommendation"] == "NEEDS_CLARIFICATION"
    checks = {check["id"]: check["status"] for check in result["checks"]}
    assert checks["supplier_bank"] == checks["order_terms"] == checks["arithmetic"] == "pass"
    assert checks["posted_copy"] == checks["mandatory_coverage"] == "unresolved"
    page = evidence[0]["records"][0]
    assert page["page_ref"] == packet["invoice"]["page_ref"]
    assert page["origin"] == "recorded-page-observation"
    if name == "internal-receipts":
        assert checks["source_quantity"] == "pass"
        assert checks["receipt_support"] == "unresolved"
        assert evidence[3]["records"][0]["quantity"] == "6"
    else:
        assert checks["source_quantity"] == "unresolved"
        assert checks["receipt_support"] == "pass"
        assert page["confidence"] == "unavailable"
        assert page["value"] == ""
        assert page["excerpt"] == "[unreadable]"
    assert packet["invoice"]["quantity"] == "10"
    # An empty selected query is still obtained evidence, not complete coverage.
    assert evidence[-1]["tool"] == "get_invoice_history"
    assert evidence[-1]["records"] == []
    assert evidence[-1]["coverage"] == "selected"


def test_posted_copy_packet_still_contains_genuine_blocking_evidence():
    packet = invoice_packet("posted-copy")
    tools = EvidenceTools(packet)
    try:
        evidence = tools.execute("get_invoice_history", {"supplier_id": "SUP-1", "invoice_number": "INV / 204"})
        assert evidence["records"][0]["id"] == "LEDGER-9"
        result = validate(packet["invoice"], tools.evidence)
        assert result["recommendation"] == "ESCALATE"
        assert next(c for c in result["checks"] if c["id"] == "posted_copy")["status"] == "blocking"
    finally:
        tools.close()


@pytest.mark.parametrize("identity", ["CP4-101", "CP4-102"])
def test_new_pdf_sources_have_verified_bounded_page_images(identity):
    raw, reference = pdf.verified_source(identity)
    png, rendered_ref = pdf.page_image(identity, 1)
    assert raw.startswith(b"%PDF-")
    assert hashlib.sha256(raw).hexdigest() == reference["sha256"]
    assert rendered_ref == reference
    assert len(png) <= pdf.MAX_IMAGE_BYTES
    with Image.open(io.BytesIO(png)) as image:
        assert 500 <= image.width <= 1000
        assert 800 <= image.height <= 1200
        assert image.width * image.height <= pdf.MAX_RENDER_PIXELS


def test_original_pdf_bytes_and_manifest_hashes_are_unchanged():
    original = {
        "order-gap": "1ac8cef6deedaa1d7579af411fea9b8f874c8055205cfc1bde83ce1fc425fb92",
        "posted-copy": "395694a31cc306c3809e889ffceb3bb2c283bd1db8ecdde61c20bd41380106b0",
    }
    manifest = json.loads((pdf.ASSETS / "manifest.json").read_text())
    for identity, expected in original.items():
        assert manifest[identity] == expected
        assert hashlib.sha256((pdf.ASSETS / f"{identity}.pdf").read_bytes()).hexdigest() == expected


def test_new_source_hash_tampering_is_rejected(tmp_path, monkeypatch):
    for source in pdf.ASSETS.iterdir():
        (tmp_path / source.name).write_bytes(source.read_bytes())
    (tmp_path / "CP4-101.pdf").write_bytes(b"%PDF- tampered")
    monkeypatch.setattr(pdf, "ASSETS", tmp_path)
    with pytest.raises(ValueError, match="source hash"):
        pdf.verified_source("CP4-101")
    with pytest.raises(ValueError, match="outside"):
        pdf.verified_source("../CP4-101")


def test_snapshots_contain_scoped_ordered_sent_and_received_mail():
    old = correspondence_snapshot("supplier-request")
    current = correspondence_snapshot("request-pending")
    assert old["messages"] == current["messages"][:2]
    assert [m["message_id"] for m in current["messages"]] == ["MAIL-101", "MAIL-102", "MAIL-201", "MAIL-202"]
    assert [m["direction"] for m in current["messages"]] == ["sent", "received", "sent", "received"]
    assert current["messages"][-1]["body"] == "We will send a legible copy of INV / 204 tomorrow."
    assert all("INV-199" in m["subject"] for m in old["messages"])
    for snapshot in (old, current):
        assert snapshot["coverage"] == "selected"
        assert snapshot["as_of"] == "2026-10-19T10:00:00Z"
        assert snapshot["buyer_id"] == "BUYER-1" and snapshot["supplier_id"] == "SUP-1"
        assert snapshot["contact"] == {"email": "billing@workshop-supplier.example", "reference": "CONTACT-BUYER-1-SUP-1"}
        assert [m["sent_at"] for m in snapshot["messages"]] == sorted(m["sent_at"] for m in snapshot["messages"])
        assert not {"expected_action", "pending", "resolved", "recommendation"}.intersection(snapshot)
        for message in snapshot["messages"]:
            assert set(message) == {"message_id", "thread_id", "direction", "sent_at", "from", "to", "subject", "body"}
            assert {message["from"], message["to"]} == {"ap@training-buyer.example", "billing@workshop-supplier.example"}


def test_lookup_registers_a_detached_actual_snapshot():
    packet = invoice_packet("supplier-request")
    snapshot = correspondence_snapshot("supplier-request")
    lookup = CorrespondenceLookup(packet["invoice"], snapshot)
    assert lookup.result is None and lookup.calls == 0
    snapshot["contact"]["email"] = "untrusted@example.test"
    result = lookup.execute({"supplier_id": "SUP-1"})
    assert lookup.calls == 1
    assert result == correspondence_snapshot("supplier-request")
    result["messages"][0]["body"] = "changed"
    exposed = lookup.result
    exposed["contact"]["email"] = "changed@example.test"
    assert lookup.result == correspondence_snapshot("supplier-request")
    with pytest.raises(ValueError, match="one attempt"):
        lookup.execute({"supplier_id": "SUP-1"})
    assert lookup.calls == 2


@pytest.mark.parametrize("arguments", [
    {"supplier_id": "OTHER"},
    {"supplier_id": "SUP-1", "buyer_id": "OTHER"},
    {"supplier_id": "SUP-1", "snapshot": "current-thread"},
    {"supplier_id": "SUP-1", "query": "all mail"},
    {"supplier_id": 1}, {},
])
def test_bad_lookup_arguments_consume_attempt_and_never_register_result(arguments):
    lookup = CorrespondenceLookup(invoice_packet("supplier-request")["invoice"], correspondence_snapshot("supplier-request"))
    with pytest.raises(ValueError):
        lookup.execute(arguments)
    assert lookup.calls == 1 and lookup.result is None
    with pytest.raises(ValueError, match="one attempt"):
        lookup.execute({"supplier_id": "SUP-1"})
    assert lookup.calls == 2 and lookup.result is None


@pytest.mark.parametrize("key,value", [("buyer_id", "OTHER"), ("supplier_id", "OTHER"), ("coverage", "complete")])
def test_lookup_refuses_snapshot_scope_or_coverage_mismatch(key, value):
    snapshot = correspondence_snapshot("supplier-request")
    snapshot[key] = value
    with pytest.raises(ValueError):
        CorrespondenceLookup(invoice_packet("supplier-request")["invoice"], snapshot)


def test_empty_selected_mail_is_supported_without_changing_contact():
    snapshot = correspondence_snapshot("supplier-request")
    snapshot["messages"] = []
    lookup = CorrespondenceLookup(invoice_packet("supplier-request")["invoice"], snapshot)
    result = lookup.execute({"supplier_id": "SUP-1"})
    assert result["messages"] == [] and result["coverage"] == "selected"
    assert result["contact"] == snapshot["contact"]


@pytest.mark.parametrize("loader", [invoice_packet, correspondence_snapshot])
def test_unknown_scenario_is_rejected(loader):
    with pytest.raises(ValueError, match="unknown"):
        loader("../unknown")


def test_only_correspondence_capability_is_a_strict_read_lookup():
    assert TOOL["name"] == "read_supplier_correspondence"
    assert TOOL["type"] == "function" and TOOL["strict"] is True
    assert set(TOOL["parameters"]["properties"]) == {"supplier_id"}
    assert TOOL["parameters"]["additionalProperties"] is False
