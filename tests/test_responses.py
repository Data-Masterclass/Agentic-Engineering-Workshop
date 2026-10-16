"""Responses wire contracts using only httpx.MockTransport; sockets are denied."""
import json
import socket
from decimal import Decimal

import httpx
import pytest

from workshop.pack import fixture, observations
from workshop.runtime import Budget, IncompleteExercise, LiveClient, Runtime, Terminal
from workshop.scripts import interaction_examples
from workshop.responses import MAX_RESPONSE_BYTES


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def deny(*args, **kwargs):
        raise AssertionError("network forbidden in offline Responses tests")
    monkeypatch.setattr(socket.socket, "connect", deny)
    monkeypatch.setattr(socket.socket, "connect_ex", deny)
    monkeypatch.setenv("WORKSHOP_MODE", "live")
    monkeypatch.setenv("WORKSHOP_LIVE_ACK", "approved-paid-calls")
    monkeypatch.setenv("WORKSHOP_BASE_URL", "https://gateway.invalid/v1")
    monkeypatch.setenv("WORKSHOP_MODEL", "test-alias")
    monkeypatch.setenv("WORKSHOP_API_KEY", "SYNTHETIC-KEY-NEVER-EXPORT")
    monkeypatch.setenv("WORKSHOP_MAX_CALL_USD", "0.02")
    monkeypatch.delenv("WORKSHOP_REASONING_EFFORT", raising=False)
    monkeypatch.delenv("WORKSHOP_MAX_OUTPUT_TOKENS", raising=False)


def completed(*items):
    return {"status": "completed", "output": list(items)}


def message(value):
    return {"type": "message", "id": "msg_test", "role": "assistant", "status": "completed",
            "content": [{"type": "output_text", "text": json.dumps(value), "annotations": []}]}


def function(name="review_pdf_page", args=None, call_id="call_test"):
    return {"type": "function_call", "id": "fc_test", "status": "completed", "name": name,
            "arguments": json.dumps(args if args is not None else {"invoice_id": "reading-conflict", "page": 1}),
            "call_id": call_id}


REASONING = {"type": "reasoning", "id": "rs_test", "summary": [], "encrypted_content": "OPAQUE-REASONING-DO-NOT-TRACE"}
MESSAGES = [{"role": "user", "content": "Return JSON about this invoice."}]


def client_for(*responses):
    pending = iter(responses)
    requests = []
    def handle(request):
        requests.append(request)
        response = next(pending)
        if isinstance(response, Exception):
            raise response
        return response if isinstance(response, httpx.Response) else httpx.Response(200, json=response)
    return LiveClient(transport=httpx.MockTransport(handle)), requests


def state_for(case="reading-conflict"):
    return {"candidate": fixture(case).candidate.model_dump(mode="json"),
            "checks": [{"id": "lines.L1.quantity", "status": "unresolved", "detail": "PRIVATE-VALIDATION-DETAIL"}]}


def live_observations(case="reading-conflict"):
    rows = [e.model_dump(mode="json") for e in observations(case, 1)]
    for row in rows:
        row["origin"] = "live-page-review"
    return rows


def test_responses_request_and_output_with_reasoning_before_text(monkeypatch):
    monkeypatch.setenv("WORKSHOP_REASONING_EFFORT", "low")
    client, requests = client_for(completed(REASONING, message({"handoff": "Review required"})))
    assert client.investigation(MESSAGES)["handoff"] == "Review required"
    request = requests[0]
    body = json.loads(request.content)
    assert request.method == "POST" and str(request.url) == "https://gateway.invalid/v1/responses"
    assert request.headers["authorization"] == "Bearer SYNTHETIC-KEY-NEVER-EXPORT"
    assert body["model"] == "test-alias" and body["input"][1:] == MESSAGES
    assert body["input"][0] == {"role": "system", "content": "Return a JSON object when not calling a function."}
    assert body["reasoning"] == {"effort": "low"}
    assert body["text"] == {"format": {"type": "json_object"}}
    assert body["max_output_tokens"] == 4096
    assert body["store"] is False and body["stream"] is False
    assert body["include"] == ["reasoning.encrypted_content"]
    assert body["parallel_tool_calls"] is False
    assert body["tools"][0]["name"] == "review_pdf_page" and body["tools"][0]["strict"] is True
    assert not {"messages", "max_tokens", "temperature", "response_format", "previous_response_id", "conversation"} & body.keys()


def test_non_reasoning_model_omits_reasoning_configuration(monkeypatch):
    monkeypatch.setenv("WORKSHOP_MODEL", "gpt-4o-mini")
    client, requests = client_for(completed(message({"observations": []})))
    assert client.request(MESSAGES) == {"observations": []}
    body = json.loads(requests[0].content)
    assert "reasoning" not in body and "temperature" not in body and "tools" not in body


@pytest.mark.parametrize("operation", ["investigation", "review"])
def test_json_mode_works_when_caller_does_not_mention_json(operation, monkeypatch):
    import workshop.tools as module
    monkeypatch.setattr(module, "page_image", lambda *_: b"test-png")
    rows = live_observations()
    requests = []
    def endpoint(request):
        body = json.loads(request.content)
        requests.append(body)
        # Match the upstream JSON-mode requirement, including image requests.
        text = " ".join(
            item["content"] if isinstance(item.get("content"), str)
            else " ".join(part.get("text", "") for part in item.get("content", []))
            for item in body["input"]
        )
        if "json" not in text.lower():
            return httpx.Response(400, json={"error": {"message": "input must mention JSON"}})
        result = {"handoff": "Review required"} if operation == "investigation" else {"observations": rows}
        return httpx.Response(200, json=completed(message(result)))
    client = LiveClient(transport=httpx.MockTransport(endpoint))
    messages = [{"role": "user", "content": "Inspect the invoice."}]
    if operation == "investigation":
        assert client.investigation(messages)["handoff"] == "Review required"
        assert messages == [{"role": "user", "content": "Inspect the invoice."}]
    else:
        assert client.review("reading-conflict", 1) == rows
    assert len(requests) == 1


def test_official_function_example_without_optional_status_is_supported():
    call = function()
    del call["status"]
    client, _ = client_for(completed(call))
    assert client.investigation(MESSAGES)["tool_requests"][0]["name"] == "review_pdf_page"


def test_native_tool_round_trip_preserves_reasoning_and_actual_evidence(monkeypatch):
    import workshop.tools as module
    monkeypatch.setattr(module, "page_image", lambda *_: b"test-png")
    findings = interaction_examples("reading-conflict")[1]
    rows = live_observations()
    client, requests = client_for(completed(REASONING, function()),
                                  completed(message({"observations": rows})),
                                  completed(message(findings)))
    runtime = Runtime(fixture("reading-conflict"), client, Budget(allowance=Decimal(".10")))
    state = state_for()
    first = runtime.ask("Choose relevant evidence", state)
    assert len(requests) == 1  # Returning a call never executes it automatically.
    records = runtime.review(first.tool_requests[0].model_dump(),
                             lambda invoice, page, reader: {"observations": reader(invoice, page)})
    final = runtime.ask("Use obtained evidence", state)
    assert final.findings.corrections and records[0].id in runtime.evidence
    from workshop.validation import apply_findings
    corrected = apply_findings(state["candidate"], final.findings.model_dump(), runtime)
    assert corrected["lines"][0]["quantity"] == "10"
    assert str(runtime.extraction.original.lines[0].quantity) == "100"
    assert runtime.budget.models == 3 and runtime.budget.tools == 1
    assert runtime.budget.reserved == Decimal(".06")
    followup = json.loads(requests[2].content)["input"]
    assert REASONING in followup and function() in followup
    outputs = [item for item in followup if item.get("type") == "function_call_output"]
    assert outputs == [{"type": "function_call_output", "call_id": "call_test", "output": json.dumps({"observations": rows})}]
    page_input = json.loads(requests[1].content)["input"][1]["content"]
    assert page_input[1] == {"type": "input_image", "image_url": "data:image/png;base64,dGVzdC1wbmc="}
    assert REASONING not in json.loads(requests[1].content)["input"]
    exported = json.dumps(runtime.events + [runtime.notebook()])
    for secret in (REASONING["encrypted_content"], "call_test", "SYNTHETIC-KEY-NEVER-EXPORT", "PRIVATE-VALIDATION-DETAIL"):
        assert secret not in exported
    assert "PRIVATE-VALIDATION-DETAIL" not in requests[0].content.decode()


def test_live_extraction_uses_responses_image_and_shared_reservation(monkeypatch):
    from workshop.extraction import extract
    import workshop.tools as module
    monkeypatch.setattr(module, "page_image", lambda *_: b"test-png")
    raw = fixture("reading-conflict").model_dump(mode="json")
    raw["source"] = "live-vlm"
    client, requests = client_for(completed(message(raw)))
    result, remaining = extract("reading-conflict", client, Decimal(".10"))
    assert result.source == "live-vlm" and remaining == Decimal(".08")
    body = json.loads(requests[0].content)
    assert body["input"][1]["content"][1]["type"] == "input_image" and "tools" not in body


def test_pending_call_needs_a_validated_result_and_run_reset_clears_history():
    client, requests = client_for(completed(REASONING, function()))
    client.investigation(MESSAGES)
    with pytest.raises(ValueError, match="validated tool result"):
        client.investigation(MESSAGES)
    with pytest.raises(ValueError, match="does not match"):
        client.record_tool_result({"name": "review_pdf_page", "invoice_id": "matching", "page": 1}, [])
    Runtime(fixture("matching"), client)  # A new case must not inherit opaque state.
    assert not client._investigation._history and client._investigation._pending is None
    assert len(requests) == 1


def test_invalid_reader_provenance_never_becomes_a_function_output(monkeypatch):
    import workshop.tools as module
    monkeypatch.setattr(module, "page_image", lambda *_: b"test-png")
    rows = live_observations()
    rows[0]["page_ref"]["sha256"] = "0" * 64
    client, requests = client_for(completed(REASONING, function()), completed(message({"observations": rows})))
    runtime = Runtime(fixture("reading-conflict"), client, Budget(allowance=Decimal(".10")))
    request = runtime.ask("Review evidence", state_for()).tool_requests[0]
    with pytest.raises(Terminal):
        runtime.review(request.model_dump())
    with pytest.raises(Terminal):
        runtime.ask("Try again", state_for())
    assert runtime.budget.tools == 1 and runtime.budget.models == 2
    assert not runtime.evidence and not any(i.get("type") == "function_call_output" for i in client._investigation._history)
    assert len(requests) == 2


@pytest.mark.original_scaffold
def test_unfinished_participant_tool_stays_unfinished():
    from workshop.tools import review_pdf_page
    client, requests = client_for(completed(REASONING, function()))
    runtime = Runtime(fixture("reading-conflict"), client, Budget(allowance=Decimal(".10")))
    request = runtime.ask("Review evidence", state_for()).tool_requests[0]
    with pytest.raises(IncompleteExercise, match="TODO 1"):
        runtime.review(request.model_dump(), review_pdf_page)
    assert len(requests) == 1 and runtime.budget.models == runtime.budget.tools == 1


@pytest.mark.parametrize("status", [401, 429, 503, 500, 307])
def test_http_errors_do_not_retry_follow_redirect_or_export_provider_body(status):
    client, requests = client_for(httpx.Response(status, text="SECRET-PROVIDER-BODY", headers={"Location": "https://other.invalid"}))
    runtime = Runtime(fixture("reading-conflict"), client, Budget(allowance=Decimal(".10")))
    with pytest.raises(Terminal, match=f"gateway HTTP {status}") as error:
        runtime.ask("Check", state_for())
    assert "SECRET-PROVIDER-BODY" not in str(error.value)
    assert runtime.budget.reserved == Decimal(".02") and len(requests) == 1
    with pytest.raises(Terminal):
        runtime.ask("Retry", state_for())
    assert len(requests) == 1


def test_transport_error_is_sanitized_and_reserved():
    client, requests = client_for(httpx.ReadTimeout("SECRET-TRANSPORT-DETAIL"))
    runtime = Runtime(fixture("reading-conflict"), client, Budget(allowance=Decimal(".10")))
    with pytest.raises(Terminal, match="gateway transport failed") as error:
        runtime.ask("Check", state_for())
    assert "SECRET-TRANSPORT-DETAIL" not in str(error.value)
    assert runtime.budget.reserved == Decimal(".02") and len(requests) == 1


@pytest.mark.parametrize("payload", [
    {"status": "incomplete", "incomplete_details": {"reason": "max_output_tokens"}, "output": []},
    {"status": "failed", "error": {"message": "SECRET-ERROR"}},
    {"choices": [{"message": {"content": "{}"}}]},
    completed(), completed(REASONING), completed({"type": "web_search_call"}),
    completed({"type": "message", "role": "assistant", "status": "completed", "content": [{"type": "refusal", "refusal": "SECRET-REFUSAL"}]}),
    completed(message(["not-an-object"])),
    completed(message({"tool_requests": [{"name": "review_pdf_page", "invoice_id": "reading-conflict", "page": 1}]})),
])
def test_bad_or_incomplete_output_terminates_without_retry_or_payload_export(payload):
    client, requests = client_for(payload)
    runtime = Runtime(fixture("reading-conflict"), client, Budget(allowance=Decimal(".10")))
    with pytest.raises(Terminal) as error:
        runtime.ask("Check", state_for())
    assert "SECRET-" not in str(error.value) and len(requests) == 1
    assert runtime.budget.reserved == Decimal(".02")


@pytest.mark.parametrize("items", [
    [function(name="arbitrary_sql")],
    [function(args={"invoice_id": "reading-conflict", "page": True})],
    [function(args={"invoice_id": "reading-conflict", "page": 1, "url": "SECRET-ARG"})],
    [{**function(), "arguments": "not JSON SECRET-ARG"}],
    [{**function(), "call_id": ""}],
    [{**function(), "status": "in_progress"}],
    [function(), function(call_id="second")],
    [{"type": "reasoning", "summary": []}, function()],
])
def test_invalid_function_calls_are_never_executed(items):
    client, requests = client_for(completed(*items))
    runtime = Runtime(fixture("reading-conflict"), client, Budget(allowance=Decimal(".10")))
    with pytest.raises(Terminal) as error:
        runtime.ask("Check", state_for())
    assert runtime.budget.models == 1 and runtime.budget.tools == 0
    assert not runtime.evidence and "SECRET-ARG" not in str(error.value) and len(requests) == 1


def test_duplicate_function_call_id_is_rejected():
    client, requests = client_for(completed(function()), completed(function()))
    request = client.investigation(MESSAGES)["tool_requests"][0]
    client.record_tool_result(request, [])
    with pytest.raises(ValueError, match="invalid gateway function"):
        client.investigation(MESSAGES)
    assert len(requests) == 2


@pytest.mark.parametrize("args", [{"invoice_id": "matching", "page": 1}, {"invoice_id": "reading-conflict", "page": 2}])
def test_runtime_rejects_out_of_scope_native_arguments_before_page_request(args):
    client, requests = client_for(completed(function(args=args)))
    runtime = Runtime(fixture("reading-conflict"), client, Budget(allowance=Decimal(".10")))
    request = runtime.ask("Check", state_for()).tool_requests[0]
    with pytest.raises(Terminal, match="outside selected"):
        runtime.review(request.model_dump())
    assert len(requests) == 1 and runtime.budget.tools == 1


def test_followup_cannot_exceed_shared_spend_allowance():
    client, requests = client_for(completed(function()))
    runtime = Runtime(fixture("reading-conflict"), client, Budget(allowance=Decimal(".02")))
    request = runtime.ask("Check", state_for()).tool_requests[0]
    with pytest.raises(Terminal, match="spending allowance"):
        runtime.review(request.model_dump())
    assert len(requests) == 1 and runtime.budget.reserved == Decimal(".02")
    assert runtime.budget.tools == 1 and runtime.budget.models == 2


def test_each_model_turn_counts_and_attempt_limit_prevents_http():
    client, requests = client_for(*(completed(message({"handoff": "Review"})) for _ in range(8)))
    runtime = Runtime(fixture("reading-conflict"), client, Budget(allowance=Decimal("1")))
    for _ in range(8):
        runtime.ask("Check", state_for())
    with pytest.raises(Terminal, match="model attempts exhausted"):
        runtime.ask("Check", state_for())
    assert len(requests) == 8 and runtime.budget.reserved == Decimal(".16")


def test_large_response_and_accumulated_input_are_bounded():
    client, requests = client_for(httpx.Response(200, content=b" " * (MAX_RESPONSE_BYTES + 1)))
    with pytest.raises(ValueError, match="output too large"):
        client.request(MESSAGES)
    client._investigation._history = [{"role": "user", "content": "x" * 3_000_000}]
    with pytest.raises(ValueError, match="input too large"):
        client.investigation(MESSAGES)
    assert len(requests) == 1


@pytest.mark.parametrize("variable,value", [
    ("WORKSHOP_LIVE_ACK", "not-approved"), ("WORKSHOP_MODE", "offline"),
    ("WORKSHOP_BASE_URL", "http://gateway.invalid/v1"),
    ("WORKSHOP_BASE_URL", "https://user:secret@gateway.invalid/v1"),
    ("WORKSHOP_BASE_URL", "https://gateway.invalid/v1?key=secret"),
    ("WORKSHOP_REASONING_EFFORT", "invalid"),
    ("WORKSHOP_MAX_OUTPUT_TOKENS", "0"), ("WORKSHOP_MAX_OUTPUT_TOKENS", "8193"),
    ("WORKSHOP_MAX_CALL_USD", "NaN"),
])
def test_invalid_configuration_cannot_create_live_client(monkeypatch, variable, value):
    monkeypatch.setenv(variable, value)
    with pytest.raises(ValueError):
        client_for()
