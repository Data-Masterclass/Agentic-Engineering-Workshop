"""Private local context views, deliberately separate from the sharing exporter."""
import html
import json
from pathlib import Path
import re

from .core import CASES, ROLES, destination, inspect_experiment, load_json, read_file


# Defence in depth for accidental credential/reasoning fields. This is not a
# general-purpose secret scanner: detailed business content must stay local.
HIDDEN = {"apikey", "authorization", "password", "secret", "token", "accesstoken",
          "refreshtoken", "masterkey", "credential", "credentials", "reasoning",
          "encryptedcontent", "chainofthought"}


def redact(value):
    if isinstance(value, dict):
        return {k: "[omitted]" if re.sub(r"[^a-z]", "", k.lower()) in HIDDEN else redact(v)
                for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v) for v in value]
    if isinstance(value, str):
        return re.sub(r"\b(?:sk-[A-Za-z0-9_-]{8,}|Bearer\s+[A-Za-z0-9._~+/-]+=*)", "[omitted]", value, flags=re.I)
    return value


def block(value):
    return "<pre>" + html.escape(json.dumps(redact(value), indent=2, ensure_ascii=False)) + "</pre>"


def page(title, body):
    return ("<!doctype html><html lang='en'><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<meta http-equiv='Content-Security-Policy' content=\"default-src 'none'; style-src 'unsafe-inline'\">"
        "<title>" + html.escape(title) + "</title><style>"
        "body{font:16px system-ui;max-width:1050px;margin:32px auto;padding:20px;color:#182430;background:#f7f9fb}"
        "section{background:white;border:1px solid #ccd5df;border-radius:8px;margin:18px 0;padding:18px}"
        "pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:14px}summary{cursor:pointer}"
        ".notice{padding:16px;background:#fff1cc;border:1px solid #c8a044}h2{font-size:20px}"
        "</style><h1>" + html.escape(title) + "</h1>"
        "<p class='notice'><strong>Private local view.</strong> Includes invoice and evidence content. "
        "Keep this directory local; it is excluded from the Session 3 sharing export. "
        "Credential-field masking is only a precaution, not a guarantee of safe sharing.</p>"
        + body + "</html>")


def render_context(events, report, variant, *, mode, title):
    """Render recorded inputs/outputs, never reconstruct an API conversation."""
    body = "<p>Recorded source mode: " + html.escape(mode) + ". Viewing this page makes no model calls.</p>"
    body += ("<p>The timeline shows recorded validation context, model-selected tool arguments, returned evidence "
             "and the final answer when recorded. Exact model request/response bodies and private reasoning "
             "were not saved. This is not a transcript of every model input or an explanation of its intent. "
             "PDF image bytes are not embedded; page references and returned observations are shown.</p>")
    body += "<section><h2>Original invoice — investigation input</h2>" + block(report["original"]) + "</section>"
    body += ("<details><summary>Configured investigation prompt and available tools</summary>"
             + block({k: variant[k] for k in ("prompt", "enabled_tools") if k in variant}) + "</details>")
    body += "<h2>Recorded workflow, in execution order</h2>"
    fields = {
        "validation": ("Validation context / deterministic recommendation", ("checks", "recommendation", "association")),
        "tool_requested": ("Model output → tool input", ("name", "arguments")),
        "tool_result": ("Tool output → evidence available to the model", ("evidence",)),
        "page_read": ("PDF reader output", ("page_ref", "mode", "observations")),
        "answer": ("Final investigator output", ("note", "handoff")),
        "terminal": ("Execution stopped", ("error",)),
    }
    for ordinal, event in enumerate(events, 1):
        selected = fields.get(event.get("event"))
        if selected is None:
            body += f"<p>Event {ordinal}: unsupported event omitted.</p>"
            continue
        label, keys = selected
        content = block({k: event[k] for k in keys if k in event})
        # Keep tool I/O visible for judging the choice; validation snapshots can
        # be expanded immediately before/after the action they contextualise.
        if event["event"] == "validation":
            content = "<details><summary>Checks, evidence citations and recommendation</summary>" + content + "</details>"
        body += f"<section id='event-{ordinal}'><h2>{ordinal}. {label}</h2>{content}</section>"
    body += "<section><h2>Saved final outcome</h2>"
    if report.get("answer") is None:
        body += "<p>No final investigator answer was recorded. See the deterministic outcome and any execution stop below.</p>"
    body += block({k: report.get(k) for k in ("answer", "recommendation", "checks", "association", "terminal")})
    body += "</section>"
    return page(title, body)


def context(source, output):
    """Generate four private views from validated saved artifacts, without calls."""
    projection, _ = inspect_experiment(source)
    root = Path(source).resolve(strict=True)
    configuration = load_json(read_file(root, "configuration.json"))
    files = {}
    for name in CASES:
        for role, variant in zip(ROLES, configuration["variants"]):
            folder = Path(name) / variant["id"] / "run-1"
            report = load_json(read_file(root, folder / "review.json"))
            events = [load_json(line) for line in read_file(root, folder / "trace.jsonl", 2000000).decode().splitlines() if line.strip()]
            filename = f"{name}-{role}.html"
            files[filename] = render_context(events, report, variant, mode=projection["input_mode"], title=f"{name} / {role} — recorded context")
    links = "<ul>" + "".join(f"<li><a href='{name}'>{name.removesuffix('.html')}</a></li>" for name in files) + "</ul>"
    files["index.html"] = page("Private Session 3 traces with context", links)
    target = destination(source, output)
    target.mkdir(mode=0o700, parents=True, exist_ok=False)
    for name, content in files.items():
        path = target / name
        with path.open("x", encoding="utf-8") as stream:
            stream.write(content)
        path.chmod(0o600)
    return target
