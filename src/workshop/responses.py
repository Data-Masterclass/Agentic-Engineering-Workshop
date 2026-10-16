"""Bounded Responses transport; tools still execute in the prepared runtime."""
import json
import os
from decimal import Decimal

import httpx


MAX_INPUT_BYTES = 3_000_000
MAX_RESPONSE_BYTES = 262_144  # Includes opaque encrypted reasoning, not just final JSON.


def input_items(messages):
    """Translate the workshop's text/image messages without changing their data."""
    items = []
    for message in messages:
        content = message["content"]
        if isinstance(content, list):
            content = [
                {"type": "input_text", "text": part["text"]} if part["type"] == "text"
                else {"type": "input_image", "image_url": part["image_url"]["url"]}
                for part in content
            ]
        items.append({"role": message["role"], "content": content})
    return items


class ResponsesClient:
    """Configured, bounded Responses transport without application policy."""
    def __init__(self, *, transport=None):
        if os.getenv("WORKSHOP_MODE") != "live" or os.getenv("WORKSHOP_LIVE_ACK") != "approved-paid-calls":
            raise ValueError("live calls require deliberate approved-paid-calls opt-in")
        self.url = os.environ["WORKSHOP_BASE_URL"].rstrip("/")
        url = httpx.URL(self.url)
        if url.scheme != "https" or not url.host or "YOUR-" in self.url or url.userinfo or url.query or url.fragment or url.path != "/v1":
            raise ValueError("configure an approved HTTPS gateway base ending in /v1")
        self.model = os.environ["WORKSHOP_MODEL"]
        self.key = os.environ["WORKSHOP_API_KEY"]
        if not self.model.strip() or not self.key.strip():
            raise ValueError("model alias and scoped key are required")
        self.cost = Decimal(os.environ["WORKSHOP_MAX_CALL_USD"])
        if not self.cost.is_finite() or self.cost <= 0:
            raise ValueError("positive finite worst-case request cost required")
        # Explicit, per-model configuration; never infer capability from an alias.
        self.effort = os.getenv("WORKSHOP_REASONING_EFFORT") or None
        if self.effort not in (None, "none", "minimal", "low", "medium", "high", "xhigh", "max"):
            raise ValueError("invalid reasoning effort")
        self.max_output_tokens = int(os.getenv("WORKSHOP_MAX_OUTPUT_TOKENS", "4096"))
        if not 1 <= self.max_output_tokens <= 8192:
            raise ValueError("output token limit must be between 1 and 8192")
        self._transport = transport

    def response(self, items, *, tools=(), instructions="", schema=None):
        json_instruction = "Return a JSON object when not calling a function."
        body = {
            "model": self.model,
            # JSON mode checks input messages, even with separate instructions.
            "input": [{"role": "system", "content": json_instruction}, *items],
            "max_output_tokens": self.max_output_tokens,
            "text": {"format": {"type": "json_object"}},
            "instructions": json_instruction + instructions,
            "store": False,
            "include": ["reasoning.encrypted_content"],
            "stream": False,
        }
        if schema is not None:
            body["text"]["format"] = {"type": "json_schema", "name": "workshop_output", "strict": True, "schema": schema}
        if self.effort is not None:
            body["reasoning"] = {"effort": self.effort}
        if tools:
            body.update(tools=list(tools), tool_choice="auto", parallel_tool_calls=False)
        if len(json.dumps(body).encode()) > MAX_INPUT_BYTES:
            raise ValueError("model input too large")
        try:
            # httpx has no retries by default. Do not use inherited proxies or auth.
            with httpx.Client(timeout=25, follow_redirects=False, trust_env=False, transport=self._transport) as client:
                with client.stream("POST", self.url + "/responses", headers={"Authorization": "Bearer " + self.key}, json=body) as response:
                    if response.status_code != 200:
                        raise RuntimeError(f"gateway HTTP {response.status_code}")
                    raw = bytearray()
                    for chunk in response.iter_bytes():
                        raw.extend(chunk)
                        if len(raw) > MAX_RESPONSE_BYTES:
                            raise ValueError("gateway output too large")
        except httpx.HTTPError:
            # Exceptions can contain URLs/headers. Keep transport details private.
            raise RuntimeError("gateway transport failed") from None
        try:
            payload = json.loads(raw)
        except (ValueError, UnicodeError):
            raise ValueError("invalid gateway response JSON") from None
        if not isinstance(payload, dict) or payload.get("status") != "completed":
            raise ValueError("gateway response not completed; no retry")
        output = payload.get("output")
        if not isinstance(output, list) or not output:
            raise ValueError("gateway response has no output")
        for item in output:
            if not isinstance(item, dict) or item.get("type") not in ("reasoning", "function_call", "message"):
                raise ValueError("unsupported gateway output item")
            if item.get("type") == "message":
                if item.get("role") != "assistant" or item.get("status") not in (None, "completed") or not isinstance(item.get("content"), list):
                    raise ValueError("invalid gateway message")
                if any(not isinstance(c, dict) or c.get("type") != "output_text" or not isinstance(c.get("text"), str) for c in item["content"]):
                    raise ValueError("gateway refusal or unsupported message content")
        return output

    @staticmethod
    def json_output(output):
        if any(item["type"] == "function_call" for item in output):
            raise ValueError("unexpected function call")
        text = "".join(c["text"] for item in output if item["type"] == "message" for c in item["content"])
        if len(text.encode()) > 65536:
            raise ValueError("structured output too large")
        try:
            result = json.loads(text)
        except ValueError:
            raise ValueError("invalid gateway structured output") from None
        if not isinstance(result, dict):
            raise ValueError("gateway structured output must be an object")
        return result

    def request(self, messages, *, schema=None):
        """Send one independent JSON request; conversation state belongs to the caller."""
        return self.json_output(self.response(input_items(messages), schema=schema))
