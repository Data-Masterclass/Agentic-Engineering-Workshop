import copy
import io
import json
from decimal import Decimal
import time

from PIL import Image
import httpx
import pytest

from workshop.session2 import pdf
from workshop.session2.checkpoint import LiveTransport, ScriptedTransport, run
from workshop.session2.data import case
from workshop.session2.policy import validate
from workshop.session2.runner import actions
from workshop.session2.tools import EvidenceTools


def observation(name="order-gap", *, live=True):
    row = copy.deepcopy(case(name)["records"]["pages"][0])
    del row["page"]
    row["origin"] = "live-page-review" if live else "recorded-page-observation"
    return row


class FakeLive(ScriptedTransport):
    live = True
    cost = Decimal("0.01")

    def __init__(self, script):
        super().__init__(script)
        self.page_requests = []

    def request(self, messages, *, schema=None):
        self.page_requests.append((messages, schema))
        return {"observations": [observation()]}


@pytest.mark.parametrize("name", ["order-gap", "posted-copy"])
def test_verified_fixture_is_single_bounded_readable_png(name):
    raw, reference = pdf.verified_source(name)
    assert raw.startswith(b"%PDF-")
    png, rendered_reference = pdf.page_image(name, 1)
    assert reference == rendered_reference == case(name)["invoice"]["page_ref"]
    with Image.open(io.BytesIO(png)) as image:
        assert 500 <= image.width <= 1000
        assert 800 <= image.height <= 1200
        assert image.width * image.height <= pdf.MAX_RENDER_PIXELS


def test_changed_pdf_source_rejected_before_rendering(tmp_path, monkeypatch):
    for source in pdf.ASSETS.iterdir():
        (tmp_path / source.name).write_bytes(source.read_bytes())
    (tmp_path / "order-gap.pdf").write_bytes(b"%PDF- changed")
    monkeypatch.setattr(pdf, "ASSETS", tmp_path)
    with pytest.raises(ValueError, match="source hash"):
        pdf.page_image("order-gap", 1)


@pytest.mark.parametrize("name,page", [("../order-gap", 1), ("order-gap", 2), ("order-gap", True)])
def test_page_render_rejects_untrusted_path_or_page(name, page):
    with pytest.raises(ValueError):
        pdf.page_image(name, page)


def test_live_page_read_uses_actual_image_and_strict_source_schema():
    client = FakeLive([])
    records = pdf.read_page(client, "order-gap", 1)
    assert records[0]["origin"] == "live-page-review"
    messages, schema = client.page_requests[0]
    image = messages[0]["content"][1]["image_url"]["url"]
    assert image.startswith("data:image/png;base64,")
    assert schema["$defs"]["PageObservation"]["properties"]["field"]["const"] == "quantity"
    assert schema["$defs"]["PageObservation"]["properties"]["origin"]["enum"] == ["live-page-review"]
    assert schema["$defs"]["PageRef"]["properties"]["sha256"]["enum"] == [pdf.page_reference("order-gap")["sha256"]]
    assert "unit_price" not in json.dumps(schema)


@pytest.mark.parametrize("mutation", [
    {"field": "lines.L1.quantity"}, {"origin": "recorded-page-observation"},
    {"confidence": "certain"}, {"value": "NaN"}, {"value": "1000001"},
    {"value": "not a number"}, {"excerpt": ""},
    {"page_ref": {"invoice_id": "order-gap", "page": True, "sha256": "a" * 64}},
    {"page_ref": {"invoice_id": "posted-copy", "page": 1, "sha256": "a" * 64}},
])
def test_bad_page_observation_cannot_enter_registry(mutation):
    tools = EvidenceTools(case("order-gap"))
    bad = {**observation(), **mutation}
    with pytest.raises(ValueError):
        tools.execute("review_pdf_page", {"page": 1}, page_reader=lambda *args: [bad])
    assert not tools.evidence
    tools.close()


def test_page_reread_uses_same_model_time_and_spending_budget():
    client = FakeLive(actions("order-gap"))
    result = run(case("order-gap"), client, allowance=Decimal("0.08"))
    assert result["terminal"] is None
    assert result["attempts"] == {"models": 8, "tools": 6}
    assert result["reserved_usd"] == "0.08"
    assert len(client.page_requests) == 1
    assert result["candidate"] == result["original"]
    assert result["actual_cost_usd"] is None
    assert any(event["event"] == "page_read" for event in result["trace"])
    assert next(c for c in result["checks"] if c["id"] == "source_quantity")["status"] == "pass"


def test_no_page_model_call_if_shared_allowance_cannot_cover_reread():
    client = FakeLive(actions("order-gap"))
    result = run(case("order-gap"), client, allowance=Decimal("0.01"))
    assert result["terminal"] is not None
    assert client.count == 1
    assert not client.page_requests
    assert result["evidence"] == []
    assert result["reserved_usd"] == "0.01"


def test_business_records_do_not_substitute_for_source_quantity():
    script = [action for action in actions("order-gap") if action.get("name") != "review_pdf_page"]
    result = run(case("order-gap"), ScriptedTransport(script))
    checks = {c["id"]: c["status"] for c in result["checks"]}
    assert checks["order_terms"] == checks["receipt_support"] == "pass"
    assert checks["source_quantity"] == "unresolved"
    assert result["recommendation"] == "NEEDS_CLARIFICATION"


def test_ambiguous_reading_and_conflicting_reading_remain_unresolved():
    for change in ({"confidence": "ambiguous"}, {"value": "100"}):
        tools = EvidenceTools(case("order-gap"))
        tools.execute("review_pdf_page", {"page": 1}, page_reader=lambda *args: [{**observation(), **change}])
        result = validate(case("order-gap")["invoice"], tools.evidence)
        assert next(c for c in result["checks"] if c["id"] == "source_quantity")["status"] == "unresolved"
        tools.close()


def test_offline_page_recording_is_explicit_and_has_no_vlm_call():
    tools = EvidenceTools(case("order-gap"))
    result = tools.execute("review_pdf_page", {"page": 1})
    assert result["mode"] == "synthetic-recorded"
    assert result["records"][0]["origin"] == "recorded-page-observation"
    tools.close()


@pytest.mark.parametrize("name", ["order-gap", "posted-copy"])
def test_actual_responses_wire_has_strict_schema_and_input_image(monkeypatch, name):
    settings = {"WORKSHOP_MODE": "live", "WORKSHOP_LIVE_ACK": "approved-paid-calls", "WORKSHOP_BASE_URL": "https://gateway.example/v1", "WORKSHOP_MODEL": "test-only-model", "WORKSHOP_API_KEY": "test-only-key", "WORKSHOP_MAX_CALL_USD": "0.01"}
    for key, value in settings.items():
        monkeypatch.setenv(key, value)
    bodies = []
    def handle(request):
        assert len(request.content) < 48000
        body = json.loads(request.content)
        bodies.append(body)
        return httpx.Response(200, json={"status": "completed", "output": [{"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": json.dumps({"observations": [observation(name)]})}]}]})
    client = LiveTransport(transport=httpx.MockTransport(handle))
    assert pdf.read_page(client, name, 1)[0]["value"] == "10"
    body = bodies[0]
    assert body["text"]["format"]["type"] == "json_schema"
    assert body["text"]["format"]["strict"] is True
    assert body["store"] is False
    assert body["input"][1]["content"][1]["type"] == "input_image"
    assert "tools" not in body


def test_timed_out_page_read_cannot_register_late_evidence():
    class SlowLive(FakeLive):
        def request(self, *args, **kwargs):
            time.sleep(0.12)
            return super().request(*args, **kwargs)
    client = SlowLive(actions("order-gap"))
    result = run(case("order-gap"), client, allowance=Decimal("0.08"), seconds=0.06)
    assert result["terminal"] is not None
    assert result["reserved_usd"] == "0.02"
    time.sleep(0.15)
    assert not result["evidence"]
    assert not any(event["event"] == "page_read" for event in result["trace"])
