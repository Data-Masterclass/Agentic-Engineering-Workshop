"""Four sequential executions and local evidence, not a benchmark service."""
import csv
import html
from importlib.metadata import version
import json
import os
from pathlib import Path
import subprocess
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field
from .checkpoint import LiveTransport, PROMPT, ScriptedTransport, run
from .data import case, digest
from .tools import ARGUMENTS


class Variant(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,40}$")
    model: str = Field(min_length=1, max_length=100)
    prompt: str = Field(default=PROMPT, max_length=12000)
    enabled_tools: list[str] = Field(default_factory=lambda: list(ARGUMENTS))
    reasoning_effort: str = "low"
    max_output_tokens: int = Field(default=2048, ge=1, le=8192)
    max_call_usd: str = "0.05"
    run_allowance_usd: str = "0.40"


def actions(name, reverse=False):
    """Visible scripted examples, deliberately not adaptive investigator logic."""
    calls = [
        {"name": "review_pdf_page", "arguments": {"page": 1}},
        {"name": "get_supplier", "arguments": {"supplier_id": "SUP-1"}},
        {"name": "search_purchase_orders", "arguments": {"supplier_id": "SUP-1", "requisition": "REQ-2"}},
        {"name": "get_purchase_order", "arguments": {"order_id": "PO-7"}},
        {"name": "get_receipts", "arguments": {"order_id": "PO-7"}},
        {"name": "get_invoice_history", "arguments": {"supplier_id": "SUP-1", "invoice_number": "INV / 204"}},
    ]
    if name == "posted-copy":
        calls = [calls[-1]]
    elif reverse:
        calls[0], calls[1] = calls[1], calls[0]
    return calls + [{"note": "Scripted evidence path completed.", "handoff": "Selected coverage remains unresolved."}]


def score(result, expected):
    """Private labels are passed only after execution, never into the investigator."""
    if expected is None:
        return None
    checks = {c["id"]: c["status"] for c in result["checks"]}
    obtained = {e["tool"] for e in result["evidence"] if e["records"]}
    outcomes = {
        "recommendation": result["recommendation"] == expected["recommendation"],
        "checks": all(checks.get(k) == v for k, v in expected.get("checks", {}).items()),
        "evidence": all(obtained.intersection(group) for group in expected.get("evidence_any_of", [])),
        "original_preserved": result["candidate"] == result["original"],
        "no_unsupported_corrections": not result["corrections"],
        "no_terminal_failure": result["terminal"] is None,
    }
    return {**outcomes, "passed": all(outcomes.values())}


def _client(variant, mode, name, index):
    if mode == "scripted":
        return ScriptedTransport(actions(name, reverse=bool(index)))
    if variant.model.startswith("CONFIGURE_"):
        raise ValueError("replace placeholder model aliases before live execution")
    # Gateway URL and key remain in process environment, never configuration/results.
    updates = {"WORKSHOP_MODEL": variant.model, "WORKSHOP_REASONING_EFFORT": variant.reasoning_effort,
               "WORKSHOP_MAX_OUTPUT_TOKENS": str(variant.max_output_tokens), "WORKSHOP_MAX_CALL_USD": variant.max_call_usd}
    previous = {key: os.environ.get(key) for key in updates}
    try:
        os.environ.update(updates)
        return LiveTransport()
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def experiment(output, variants, *, mode="scripted", labels=None):
    if mode not in ("scripted", "live"):
        raise ValueError("unsupported execution mode")
    variants = [Variant.model_validate(v) for v in variants]
    if len(variants) != 2 or len({v.id for v in variants}) != 2:
        raise ValueError("provide exactly two distinctly named variants")
    for variant in variants:
        if not set(variant.enabled_tools) <= set(ARGUMENTS):
            raise ValueError("unknown enabled tool")
        amount = Decimal(variant.run_allowance_usd)
        cost = Decimal(variant.max_call_usd)
        if not amount.is_finite() or amount < 0 or not cost.is_finite() or cost <= 0:
            raise ValueError("invalid spending configuration")
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    module = Path(__file__).resolve()
    root = module.parents[3]
    revision = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, check=False).stdout.strip() or "unavailable"
    status = subprocess.run(["git", "status", "--porcelain"], cwd=root, capture_output=True, text=True, check=False)
    dirty = bool(status.stdout.strip()) if status.returncode == 0 else None
    sources = sorted(module.parent.glob("*.py")) + [module.parents[1] / name for name in ("responses.py", "runtime.py", "schemas.py", "pack.py", "agent.py", "tools.py", "views.py")]
    source_hash = digest({str(path.relative_to(root)): path.read_text() for path in sources})
    dependencies = {name: version(name) for name in ("langgraph", "pydantic", "httpx")}
    (output / "configuration.json").write_text(json.dumps({"mode": mode, "variants": [v.model_dump() for v in variants], "code": revision, "code_dirty": dirty, "implementation_sha256": source_hash, "dependencies": dependencies}, indent=2))
    rows = []
    for name in ("order-gap", "posted-copy"):
        for index, variant in enumerate(variants):
            directory = output / name / variant.id / "run-1"
            directory.mkdir(parents=True)
            try:
                client = _client(variant, mode, name, index)
                result = run(case(name), client, allowance=Decimal(variant.run_allowance_usd), prompt=variant.prompt, enabled_tools=variant.enabled_tools)
            except Exception as exc:
                # Preserve visible failure rows without copying credentials/error payloads.
                result = {"terminal": f"setup failed: {type(exc).__name__}", "recommendation": "ESCALATE", "trace": [], "attempts": {"models": 0, "tools": 0}, "elapsed_seconds": None, "actual_cost_usd": None, "reserved_usd": "0", "usage": None, "execution_mode": mode, "checks": [], "evidence": [], "candidate": None, "original": None, "corrections": []}
            evaluation = score(result, (labels or {}).get(name))
            result["evaluation"] = evaluation
            trace = result.pop("trace")
            (directory / "review.json").write_text(json.dumps(result, indent=2))
            (directory / "trace.jsonl").write_text("".join(json.dumps(event) + "\n" for event in trace))
            (directory / "review.html").write_text("<!doctype html><meta charset=utf-8><title>Session 2 review</title><h1>" + html.escape(name + " / " + variant.id) + "</h1><pre>" + html.escape(json.dumps(result, indent=2)) + "</pre>")
            rows.append({"case": name, "variant": variant.id, "run": 1, "model": variant.model if mode == "live" else "offline-script", "configured_model": variant.model,
                         "mode": result["execution_mode"], "recommendation": result["recommendation"], "terminal": result["terminal"], "models": result["attempts"]["models"], "tools": result["attempts"]["tools"],
                         "elapsed_seconds": result["elapsed_seconds"], "actual_cost_usd": result["actual_cost_usd"], "reserved_usd": result["reserved_usd"], "usage": result["usage"], "evaluation_passed": None if evaluation is None else evaluation["passed"],
                         "code": revision, "code_dirty": dirty, "implementation_sha256": source_hash, **result.get("versions", {})})
    (output / "comparison.json").write_text(json.dumps(rows, indent=2))
    with (output / "comparison.csv").open("w", newline="") as stream:
        fields = list(dict.fromkeys(key for row in rows for key in row))
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    return rows
