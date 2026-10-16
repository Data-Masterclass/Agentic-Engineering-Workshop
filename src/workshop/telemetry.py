"""Opt-in instructor telemetry. No optional imports or network activity by default."""
from contextlib import contextmanager
from contextvars import ContextVar, copy_context
import json
import os
import re
import warnings

_active = ContextVar("workshop_instructor_tracer", default=None)
_provider = None
_warned = False
ENDPOINT = "http://127.0.0.1:6006/v1/traces"
HIDDEN = {"apikey", "authorization", "password", "secret", "token", "accesstoken",
          "refreshtoken", "masterkey", "credential", "credentials", "reasoning",
          "encryptedcontent", "chainofthought"}


def clean(value):
    """Keep business context, omit credentials, image bodies and private reasoning."""
    if isinstance(value, dict):
        if value.get("type") == "reasoning":
            return {"type": "omitted_private_reasoning"}
        if value.get("type") in ("input_image", "image_url"):
            return {"type": "omitted_image"}
        return {k: "[omitted]" if re.sub(r"[^a-z]", "", k.lower()) in HIDDEN else clean(v)
                for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean(v) for v in value if not isinstance(v, dict) or v.get("type") != "reasoning"]
    if isinstance(value, str):
        if value.startswith(("{", "[")):
            try:
                return json.dumps(clean(json.loads(value)), ensure_ascii=False)
            except (ValueError, TypeError):
                pass
        if value.startswith("data:"):
            return "[data URI omitted]"
        return re.sub(r"\b(?:sk-[A-Za-z0-9_-]{8,}|Bearer\s+[A-Za-z0-9._~+/-]+=*)", "[omitted]", value, flags=re.I)
    return value


def _json(value):
    text = json.dumps(clean(value), ensure_ascii=False)
    # Bound span attributes without creating an invalid JSON payload.
    if len(text.encode()) > 60000:
        return json.dumps({"omitted": "content exceeds trace attribute bound"})
    return text


def _notice():
    global _warned
    if not _warned:
        _warned = True
        try:
            warnings.warn("Instructor tracing unavailable; workflow continues without it.", RuntimeWarning, stacklevel=2)
        except Warning:
            pass  # Warning-as-error settings must not stop the investigation.


def _get_tracer():
    global _provider
    if os.environ.get("WORKSHOP_TRACING") != "phoenix":
        return None
    try:
        if _provider is None:
            from opentelemetry.sdk.trace import TracerProvider
            from opentelemetry.sdk.trace.export import BatchSpanProcessor
            from opentelemetry.sdk.resources import Resource
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
            import requests

            class LocalSession(requests.Session):
                def request(self, *args, **kwargs):
                    kwargs["allow_redirects"] = False
                    return super().request(*args, **kwargs)

            session = LocalSession()
            session.trust_env = False  # No proxy/netrc credentials for local data.
            exporter = OTLPSpanExporter(endpoint=ENDPOINT, timeout=1,
                headers={"Content-Type": "application/x-protobuf"}, session=session)
            provider = TracerProvider(resource=Resource({
                "service.name": "workshop-instructor", "openinference.project.name": "workshop-session3"}))
            provider.add_span_processor(BatchSpanProcessor(exporter, max_queue_size=256,
                max_export_batch_size=32, schedule_delay_millis=500))
            _provider = provider  # Private provider; never replace global instrumentation.
        return _provider.get_tracer("workshop.instructor")
    except Exception:
        _notice()
        return None


@contextmanager
def session():
    token = _active.set(_get_tracer())
    try:
        yield
    finally:
        _active.reset(token)


class Observation:
    def __init__(self, span=None):
        self.span = span

    @contextmanager
    def activate(self):
        """Attach a non-current parent only while this graph node executes."""
        scope = None
        if self.span is not None:
            try:
                from opentelemetry.trace import use_span
                scope = use_span(self.span, end_on_exit=False, record_exception=False, set_status_on_exception=False)
                scope.__enter__()
            except Exception:
                scope = None
                _notice()
        try:
            yield
        finally:
            if scope is not None:
                try:
                    scope.__exit__(None, None, None)
                except Exception:
                    _notice()

    def end(self):
        if self.span is not None:
            try:
                self.span.end()
            except Exception:
                _notice()
            finally:
                self.span = None

    def error(self, description):
        if self.span is not None:
            try:
                from opentelemetry.trace import Status, StatusCode
                self.span.set_status(Status(StatusCode.ERROR, description))
            except Exception:
                _notice()

    def output(self, value):
        if self.span is not None:
            try:
                self.span.set_attribute("output.value", _json(value))
                self.span.set_attribute("output.mime_type", "application/json")
            except Exception:
                _notice()


def start_span(name, kind, inputs):
    """Own a span across graph nodes without holding a context token between them."""
    tracer = _active.get()
    if tracer is not None:
        try:
            return Observation(tracer.start_span(name, attributes={
                "openinference.span.kind": kind, "input.value": _json(inputs),
                "input.mime_type": "application/json"}))
        except Exception:
            _notice()
    return Observation()


@contextmanager
def span(name, kind, inputs):
    """Tracing failures cannot replace workflow results or exception messages."""
    tracer = _active.get()
    scope = None
    observation = Observation()
    if tracer is not None:
        try:
            scope = tracer.start_as_current_span(name, record_exception=False, set_status_on_exception=False,
                attributes={"openinference.span.kind": kind, "input.value": _json(inputs),
                            "input.mime_type": "application/json"})
            observation = Observation(scope.__enter__())
        except Exception:
            scope = None
            _notice()
    try:
        yield observation
    except BaseException as exc:
        if observation.span is not None:
            try:
                from opentelemetry.trace import Status, StatusCode
                observation.span.set_status(Status(StatusCode.ERROR, type(exc).__name__))
            except Exception:
                _notice()
        raise
    finally:
        if scope is not None:
            try:
                scope.__exit__(None, None, None)  # Never record raw exception payloads.
            except Exception:
                _notice()


def bound(fn):
    """Capture parent context before Budget.bounded starts its worker thread."""
    context = copy_context()
    return lambda: context.run(fn)


def flush():
    """Bounded explicit flush for short instructor CLI runs; not used per tool."""
    if _provider is not None and os.environ.get("WORKSHOP_TRACING") == "phoenix":
        try:
            return _provider.force_flush(timeout_millis=2000)
        except Exception:
            _notice()
    return True
