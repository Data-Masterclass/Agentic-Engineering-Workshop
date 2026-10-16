"""Inspect existing Session 2 artifacts; only demo executes, always scripted."""
import hashlib
import html
import json
import math
from pathlib import Path
import re
from decimal import Decimal, InvalidOperation
import zipfile

from ..session2 import runner
from ..session2.checkpoint import PROMPT
from ..session2.data import case, digest, DATA_VERSION, POLICY_VERSION
from ..session2.tools import ARGUMENTS, TOOLS
from ..trace_view import render

CASES = ("order-gap", "posted-copy")
ROLES = ("baseline", "candidate")
CHECKS = {"source_quantity", "supplier_bank", "order_terms", "receipt_support", "posted_copy", "arithmetic", "mandatory_coverage"}
STATUSES = {"pass", "unresolved", "blocking"}
RECOMMENDATIONS = {"READY_FOR_APPROVAL", "NEEDS_CLARIFICATION", "ESCALATE"}
HEX = re.compile(r"^[0-9a-f]{64}$")


def read_file(root, relative, limit=524288):
    path = root / relative
    resolved = path.resolve(strict=True)
    if not resolved.is_relative_to(root) or any(p.is_symlink() for p in (path, *path.parents) if p != root and p.is_relative_to(root)):
        raise ValueError("artifact paths must stay inside the experiment without symlinks")
    with path.open("rb") as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise ValueError("artifact exceeds the inspection byte bound")
    return raw


def load_json(raw):
    def invalid(_):
        raise ValueError("non-finite JSON numbers are unsupported")
    return json.loads(raw, parse_constant=invalid)


def count(value, maximum):
    if type(value) is not int or not 0 <= value <= maximum:
        raise ValueError("invalid recorded count")
    return value


def amount(value):
    if value is None:
        return None
    if not isinstance(value, str) or len(value) > 64:
        raise ValueError("cost must be a bounded decimal string or null")
    try:
        number = Decimal(value)
    except InvalidOperation:
        raise ValueError("invalid decimal cost") from None
    if not number.is_finite() or not 0 <= number <= 1000000 or (number and number.adjusted() < -12):
        raise ValueError("invalid decimal cost")
    return format(number, "f")


def elapsed(value):
    if value is None:
        return None
    if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 600:
        raise ValueError("invalid elapsed seconds")
    return value


def changes(variants):
    if len(variants) != 2 or variants[0].id == variants[1].id:
        raise ValueError("provide two distinct variants in baseline/candidate order")
    dumps = [v.model_dump(exclude={"id"}) for v in variants]
    for value in dumps:
        tools = value["enabled_tools"]
        if len(tools) != len(set(tools)) or not set(tools) <= set(ARGUMENTS):
            raise ValueError("unsupported or repeated enabled tool")
        value["enabled_tools"] = sorted(tools)
        if value["reasoning_effort"] not in {"none", "minimal", "low", "medium", "high", "xhigh", "max"}:
            raise ValueError("unsupported reasoning effort")
        amount(value["max_call_usd"])
        amount(value["run_allowance_usd"])
    changed = [key for key in dumps[0] if dumps[0][key] != dumps[1][key]]
    if len(changed) != 1 or changed[0] not in {"prompt", "enabled_tools"}:
        raise ValueError("change exactly one setting: prompt OR enabled_tools; keep other settings matched")
    return changed[0]


def demo(output):
    """Same engine/data, one tool-permission change; no live client is created."""
    baseline = {"id": "baseline", "model": "CONFIGURE_APPROVED_ALIAS", "prompt": PROMPT}
    candidate = dict(baseline, id="candidate", enabled_tools=[name for name in ARGUMENTS if name != "review_pdf_page"])
    return runner.experiment(output, [baseline, candidate], mode="scripted")


def inspect_experiment(source):
    """Validate the fixed teaching comparison and construct only allowed fields."""
    root = Path(source).resolve(strict=True)
    configuration = load_json(read_file(root, "configuration.json"))
    if not isinstance(configuration, dict):
        raise ValueError("configuration must be an object")
    variants = [runner.Variant.model_validate(v) for v in configuration["variants"]]
    changed = changes(variants)
    mode = configuration["mode"]
    if mode not in {"scripted", "live"}:
        raise ValueError("unknown experiment mode")
    implementation = configuration["implementation_sha256"]
    if not isinstance(implementation, str) or not HEX.fullmatch(implementation):
        raise ValueError("missing implementation fingerprint")
    dirty = configuration["code_dirty"]
    if dirty is not None and type(dirty) is not bool:
        raise ValueError("invalid code dirty marker")
    rows = load_json(read_file(root, "comparison.json"))
    if not isinstance(rows, list) or len(rows) != 4:
        raise ValueError("exactly four case/variant runs are required")
    indexed = {}
    for row in rows:
        key = (row["case"], row["variant"], row["run"])
        if key in indexed:
            raise ValueError("duplicate comparison run")
        indexed[key] = row
    expected = {(name, v.id, 1) for name in CASES for v in variants}
    if set(indexed) != expected:
        raise ValueError("case/variant manifest differs from the frozen pair")
    projected, views = [], {}
    for name in CASES:
        packet = case(name)
        for role, variant in zip(ROLES, variants):
            row = indexed[name, variant.id, 1]
            folder = Path(name) / variant.id / "run-1"
            report = load_json(read_file(root, folder / "review.json"))
            trace_raw = read_file(root, folder / "trace.jsonl", 2000000)
            lines = [line for line in trace_raw.decode("utf-8").splitlines() if line.strip()]
            if len(lines) > 5000:
                raise ValueError("too many trace events")
            events = [load_json(line) for line in lines]
            if not all(isinstance(e, dict) for e in events):
                raise ValueError("trace events must be objects")
            if not isinstance(report, dict) or not isinstance(report.get("versions"), dict):
                raise ValueError("missing per-run provenance")
            versions = report["versions"]
            expected_versions = {"data": DATA_VERSION, "policy": POLICY_VERSION,
                "data_source_sha256": packet["source_hash"],
                "pdf_source_sha256": packet["invoice"]["page_ref"]["sha256"],
                "prompt": digest(variant.prompt),
                "tool_schema_sha256": digest([t for t in TOOLS if t["name"] in variant.enabled_tools])}
            if any(versions.get(k) != v or row.get(k) != v for k, v in expected_versions.items()):
                raise ValueError("case/configuration provenance is not matched")
            if any(row.get(k) != configuration[k] for k in ("code", "code_dirty", "implementation_sha256")):
                raise ValueError("implementation provenance is not matched")
            if row["configured_model"] != variant.model or row["model"] != (variant.model if mode == "live" else "offline-script"):
                raise ValueError("configured model differs from the recorded run")
            for key, field in (("terminal", "terminal"), ("recommendation", "recommendation"), ("elapsed_seconds", "elapsed_seconds"), ("reserved_usd", "reserved_usd"), ("actual_cost_usd", "actual_cost_usd")):
                if row.get(key) != report.get(field):
                    raise ValueError("comparison summary differs from the per-run report")
            expected_mode = "live-investigator/live-page-review/synthetic-sqlite-tools" if mode == "live" else "scripted-wiring-only"
            if row["mode"] != expected_mode or report["execution_mode"] != expected_mode:
                raise ValueError("run mode differs from configuration")
            attempts = report["attempts"]
            models = count(attempts["models"], 8)
            tools = count(attempts["tools"], 12)
            if row["models"] != models or row["tools"] != tools:
                raise ValueError("attempt summary differs from the per-run report")
            statuses = {c["id"]: c["status"] for c in report["checks"]}
            if len(report["checks"]) != len(CHECKS) or set(statuses) != CHECKS or not set(statuses.values()) <= STATUSES:
                raise ValueError("unexpected validation checks")
            validations = [e for e in events if e.get("event") == "validation"]
            returned = [e.get("evidence") for e in events if e.get("event") == "tool_result"]
            if (not validations or validations[-1].get("checks") != report["checks"]
                    or returned != report["evidence"]
                    or any(not isinstance(e, dict) or e.get("source_hash") != packet["source_hash"] for e in returned)
                    or any(e.get("event") == "terminal" for e in events) != (report["terminal"] is not None)):
                raise ValueError("trace and report evidence/outcome do not correspond")
            if report["original"] != packet["invoice"]:
                raise ValueError("original invoice differs from the frozen case")
            recommendation = report["recommendation"]
            expected_recommendation = "ESCALATE" if report["terminal"] is not None else validations[-1].get("recommendation")
            if recommendation != expected_recommendation:
                raise ValueError("recommendation differs from the final trace outcome")
            if recommendation not in RECOMMENDATIONS or not isinstance(report["original"], dict) or not isinstance(report["candidate"], dict):
                raise ValueError("missing supported outcome/original")
            usage = report.get("usage")
            # Only these numeric counts may leave the laptop; never copy usage objects.
            usage = {k: count(usage[k], 10000000) for k in ("input_tokens", "output_tokens")} if isinstance(usage, dict) and all(k in usage for k in ("input_tokens", "output_tokens")) else None
            projected.append({"case": name, "variant_role": role, "run": 1,
                "recommendation": recommendation, "execution_failed": report["terminal"] is not None,
                "checks": statuses, "models": models, "tools": tools,
                "original_preserved": report["original"] == report["candidate"],
                "correction_count": count(len(report["corrections"]), 100),
                "elapsed_seconds": elapsed(report["elapsed_seconds"]),
                "actual_cost_usd": amount(report["actual_cost_usd"]),
                "reserved_usd": amount(report["reserved_usd"]), "usage": usage,
                "source_sha256": versions["data_source_sha256"],
                "pdf_sha256": versions["pdf_source_sha256"],
                "trace_sha256": hashlib.sha256(trace_raw).hexdigest()})
            # Session 1's local viewer can show numeric correction readings.
            # Sharing Session 3 must never expose those raw values, even if an
            # imported trace contains extra Session 1 events. Preserve ordinals.
            shareable = ("validation", "tool_requested", "tool_result", "page_read", "answer", "terminal")
            safe_events = [e if e.get("event") in shareable else {"event": "omitted"} for e in events]
            view = render(safe_events).replace("<h1>Workshop workflow trace</h1>", f"<h1>Workshop workflow trace</h1><p>Recorded source mode: {mode}. This view makes no model calls.</p>")
            views[f"traces/{name}-{role}.html"] = view.encode()
    configs = []
    for role, v in zip(ROLES, variants):
        configs.append({"variant_role": role, "model_sha256": digest(v.model), "prompt_sha256": digest(v.prompt),
            "enabled_tools": sorted(v.enabled_tools), "reasoning_effort": v.reasoning_effort,
            "max_output_tokens": v.max_output_tokens, "max_call_usd": amount(v.max_call_usd),
            "run_allowance_usd": amount(v.run_allowance_usd)})
    code = configuration["code"]
    projection = {"format": "workshop-session3-v1", "input_mode": mode,
        "comparison_makes_model_calls": False, "changed_field": changed,
        "interpretation": "scripted_prompt_effect_not_measured" if mode == "scripted" and changed == "prompt" else "scripted_tool_permission_boundary_only" if mode == "scripted" else "live_observation_not_a_general_ranking",
        "code_commit": code if isinstance(code, str) and re.fullmatch(r"[0-9a-f]{40}", code) else None,
        "code_dirty": dirty, "implementation_sha256": implementation,
        "dependencies_sha256": digest(configuration["dependencies"]), "variants": configs, "runs": projected}
    return projection, views


NOTICE = """Workshop Session 3 projected export
Only allowlisted settings, fingerprints, numeric results and regenerated trace views
are included. Raw prompts, aliases, invoice/evidence contents, notes, identifiers,
errors, private reasoning, credentials and source run directories are omitted.
Fingerprints establish correspondence/integrity, not authenticated provenance.
Scripted prompt changes do not measure model quality. Scripted tool-denial examples
show a deterministic permission boundary, not an adaptive model response.
Missing actual cost/usage stays null; reservations are not actual billing.
Review this bundle before sharing. Human approval remains separate.
"""


def bundle_contents(source):
    projection, views = inspect_experiment(source)
    encoded = json.dumps(projection, indent=2).encode()
    def cell(value):
        return html.escape("unavailable" if value is None else str(value))
    rows = "".join("<tr>" + "".join("<td>" + cell(value) + "</td>" for value in (
        r["case"], r["variant_role"], "stopped" if r["execution_failed"] else "completed",
        r["recommendation"], r["models"], r["tools"],
        round(r["elapsed_seconds"], 3) if r["elapsed_seconds"] is not None else None,
        r["actual_cost_usd"], r["reserved_usd"])) + "</tr>" for r in projection["runs"])
    links = " ".join(f"<a href='{name}'>{name.removeprefix('traces/').removesuffix('.html')}</a>" for name in views)
    page = ("<!doctype html><html lang='en'><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<meta http-equiv='Content-Security-Policy' content=\"default-src 'none'; style-src 'unsafe-inline'\">"
        "<title>Session 3 comparison</title><style>body{font:16px system-ui;max-width:1100px;margin:32px auto;padding:20px}"
        "table{border-collapse:collapse}td,th{padding:10px;border:1px solid #ccc;text-align:left}pre{white-space:pre-wrap;overflow-wrap:anywhere}</style>"
        "<h1>Session 3 projected comparison</h1><pre>" + html.escape(NOTICE) + "</pre>"
        + "<p>Changed setting: " + cell(projection["changed_field"]) + "; source mode: " + cell(projection["input_mode"]) + "</p>"
        + "<table><thead><tr>" + "".join("<th>" + name + "</th>" for name in (
            "Case", "Variant", "Execution", "Recommendation", "Model attempts", "Tools", "Elapsed seconds", "Actual USD", "Reserved USD"))
        + "</tr></thead><tbody>" + rows + "</tbody></table><p>Projected traces: " + links + "</p>"
        + "<details><summary>Projected configuration and provenance</summary><pre>"
        + html.escape(encoded.decode()) + "</pre></details></html>").encode()
    files = {"README.txt": NOTICE.encode(), "comparison.json": encoded, "comparison.html": page, **views}
    files["manifest.json"] = json.dumps({"format": "workshop-session3-v1", "files": {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}}, indent=2).encode()
    return files


def destination(source, output):
    root = Path(source).resolve(strict=True)
    target = Path(output)
    if target.resolve().is_relative_to(root):
        raise ValueError("destination must be outside the source experiment")
    return target


def compare(source, output):
    files = bundle_contents(source)
    target = destination(source, output)
    target.mkdir(mode=0o700, parents=True, exist_ok=False)
    for name, data in files.items():
        path = target / name
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(data)
    return target


def export(source, output):
    files = bundle_contents(source)
    target = destination(source, output)
    if target.suffix != ".zip":
        raise ValueError("export destination must end in .zip")
    # Exclusive creation never overwrites an existing archive or follows its symlink.
    with zipfile.ZipFile(target, mode="x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    return target
