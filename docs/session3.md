# Session 3: inspect, improve and share

**Objective:** use a trace to identify one problem, test one change on both
scenarios, and explain whether the evidence supports keeping it. Finish by
reviewing an export you could share.

First follow the [Session 3 transition guide](session2-to-session3.md). Your earlier
code and configuration stay intact. There are no new implementation TODOs.

## What is supplied

- An offline example with a completed investigation and an investigation that
  stops because a requested tool is not permitted.
- Detailed local traces showing the invoice, questions, tool inputs and results.
- A comparison check that requires exactly one changed setting, and an exporter
  that leaves out private content.

The two scenarios stay the same: `order-gap` needs clarification because evidence
is incomplete; `posted-copy` escalates when matching history shows the invoice is
already recorded. No model or tool can approve an invoice.

Use a new output directory or ZIP name for each run. The trace demo and saved-run
inspection/export are offline. The experiment in Step 3 makes paid model calls
and requires instructor approval.

## 1. Inspect the offline trace demo

```sh
python -m workshop.session3 demo --output outputs/session3-demo
python -m workshop.session3 compare --input outputs/session3-demo --output outputs/session3-demo-view
python -m workshop.session3 context --input outputs/session3-demo --output outputs/session3-demo-context
```

Open:

- `outputs/session3-demo-view/comparison.html` for the four-run summary.
- `outputs/session3-demo-context/index.html` for detailed trace links.

In `order-gap`, compare baseline and candidate. The candidate removes permission
to review the PDF; the fixed script still requests that tool and is stopped.
This demonstrates a tool-access check, not a model making a poor decision.
Scripted replies ignore prompt edits: use this demo to practise reading traces,
not to evaluate your prompt change.

In the detailed trace, expand the validation checks before a tool call. Inspect
its arguments, returned evidence and the checks afterward. Note the event number
that explains the difference. Keep detailed traces local: they contain invoice
and evidence content.

The instructor can show timed traces in Phoenix. You do not need to install it;
your detailed HTML traces are sufficient for the exercise.

## 2. Choose one change

Prepare a local configuration with default settings, including `enabled_tools`,
expanded so you can edit them:

```sh
python - <<'PY'
import json
from pathlib import Path
from workshop.session2.runner import Variant
source = json.loads(Path("exercises/session3/variants.json").read_text())
variants = [Variant.model_validate(v).model_dump() for v in source]
with Path("outputs/session3-variants.json").open("x") as output:
    output.write(json.dumps(variants, indent=2))
PY
```

If your copy already exists, reuse it or choose another filename; do not overwrite
previous work. On the starter branch, baseline and candidate begin identical.

Leave `baseline` unchanged. Edit only the candidate's **`prompt`** or
**`enabled_tools`**. For a tool change, use the names in
`src/workshop/session2/tools.py`. Keep the model, other settings, scenarios and
code identical. This comparison does not accept model changes. If no supported
setting changes, or more than one changes, comparison is rejected.

For example, change the prompt to check matching invoice-history records earlier.
Write your hypothesis in `exercises/session3/notes.md` and note down the expected
effect before running. Do not change validation rules or scenario data to improve
the result.

In `outputs/session3-variants.json`, replace `CONFIGURE_APPROVED_ALIAS` in both
`model` fields with the same approved alias. Use the instructor-reviewed
`reasoning_effort`, `max_output_tokens`, `max_call_usd` and `run_allowance_usd`
values in both entries. These JSON settings override the environment settings.

## 3. Run and inspect the live experiment

Only after instructor approval, follow the [Session 2 live setup](session2.md#live-run-load-your-environment-first)
to configure and load your trusted `.env` in the same terminal. Use your copied
Session 3 configuration and a new output directory:

```sh
python -m workshop.session2 --mode live --config outputs/session3-variants.json --output outputs/session3-live
```

This reuses Session 2's runner: **two scenarios × baseline/candidate = four live
executions**, giving two paired comparisons. Each execution has its own allowance;
the runner does not enforce one shared experiment budget.

Inspect those saved live results locally; these commands make no model calls:

```sh
python -m workshop.session3 compare --input outputs/session3-live --output outputs/session3-live-view
python -m workshop.session3 context --input outputs/session3-live --output outputs/session3-live-context
```

Open `outputs/session3-live-view/comparison.html`. Use
`outputs/session3-live-context/index.html` to inspect the evidence behind its
results. The comparison checks that settings, source data and code match, apart
from your selected change.

If live access is unavailable, save your configuration and hypothesis and ask
your instructor before proceeding. You can practise inspection and export on
`outputs/session3-demo` using a new ZIP name, but record **“effect not measured”**
for prompt
improvement. A scripted tool denial establishes access enforcement, not how a
model would adapt. `demo` is always scripted; `compare`, `context` and `export`
only read saved runs.

## 4. Record your decision

In `exercises/session3/notes.md`, record:

- Your change, expected effect and a relevant trace event number.
- The outcome, remaining gaps, model/tool attempts and elapsed time for both scenarios.
- Actual cost if available; otherwise write “unavailable.” The ordinary live
  runner reports cost/usage as `null`; reservations are not actual charges.
- **Keep, reject or defer** the change, with a reason based on both scenarios
  and what your execution mode can establish.

Two scenarios demonstrate the comparison process; they do not establish quality
across a broader evaluation suite. A recommendation still requires human review.

## 5. Review the sharing export

```sh
python -m workshop.session3 export --input outputs/session3-live --output outputs/session3-share.zip
```

Open the ZIP and review its contents before sharing. It contains a limited
comparison summary, four restricted trace views, a README and a file-hash manifest.
It leaves out full prompts, model aliases, notes, invoice/evidence text, PDFs,
credentials and private reasoning. It does not upload or send anything.

Keep your full configuration, notes, raw reports and detailed traces locally;
they are not included in this export. Results in `outputs/` are Git-ignored.

You are done when you can explain your change and conclusion using both scenarios,
point to supporting trace events, and open the reviewed ZIP. Run
`python -m pytest -q` for the offline support checks. Keep your earlier TODOs and
tests intact.
