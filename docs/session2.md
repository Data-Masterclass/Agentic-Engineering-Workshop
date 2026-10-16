# Session 2: compare two investigation prompts

**Objective:** test whether one prompt change improves an investigation while
keeping its evidence and recommendation supported. You will compare two prompts
on the same model across two scenarios, then explain what the results establish.

First follow the [transition guide](session1-to-session2.md). It preserves your
Session 1 code and adds a separate prepared investigator under `workshop.session2`.
There are no new implementation TODOs in this session.

## What is supplied

- An investigator that chooses read-only supplier, purchase-order, receipt,
  invoice-history and PDF-review tools.
- Synthetic invoice PDFs and local SQLite business records for two scenarios.
- Prepared validation that checks returned evidence and determines a
  recommendation for human review. The original invoice is preserved.
- A runner that saves four executions and a comparison summary locally.

| Scenario | Investigation question | Expected result for this scenario |
| --- | --- | --- |
| `order-gap` | Can we find the related purchase order and check the extracted quantity against the PDF? | `NEEDS_CLARIFICATION`: selected history and coverage gaps remain. |
| `posted-copy` | Do matching history records show that this invoice is already recorded in the accounting system? | `ESCALATE`: confirmed blocking evidence requires human review. |

Both prompts receive the same scenarios and available tools. A discovered order
association does not rewrite a missing printed PO. An empty search does not prove
absence, and neither the model nor a tool can approve an invoice.

## 1. Check the runner offline

From the repository root, with your workshop environment active:

```sh
python -m workshop.session2 --mode scripted --config exercises/session2/variants.json --output outputs/session2-wiring
```

Use a new output directory each time. `scripted` is the offline mode: fixed replies
check the workflow without model calls. They do not respond to prompt edits or
measure quality. You only need this one offline wiring check.

## 2. Choose one prompt change

Prepare an editable configuration with the default settings and prompt expanded:

```sh
python - <<'PY'
import json
from pathlib import Path
from workshop.session2.runner import Variant
source = json.loads(Path("exercises/session2/variants.json").read_text())
variants = [Variant.model_validate(v).model_dump() for v in source]
for variant in variants:
    variant["model"] = "CONFIGURE_APPROVED_ALIAS"
with Path("outputs/session2-variants.json").open("x") as output:
    output.write(json.dumps(variants, indent=2))
PY
```

The config command creates a new file; reuse your existing copy when repeating.
Open `outputs/session2-variants.json`. Leave the baseline prompt unchanged and edit
only the second prompt. For example, ask it to check invoice history first and
confirm that the supplier, invoice number and amount match before investigating
other questions. Note down the expected effect.

In `outputs/session2-variants.json`, replace `CONFIGURE_APPROVED_ALIAS` in
**both `model` fields** with the same alias supplied by your instructor:

```json
"model": "YOUR_APPROVED_ALIAS"
```

Use the instructor's values for `reasoning_effort`, `max_output_tokens`,
`max_call_usd` and `run_allowance_usd` in both entries. Keep every setting except
the second prompt identical. These JSON settings override the corresponding
environment variables. The selected model handles investigation and PDF reading.

A two-model comparison is an optional alternative: keep the prompt and other
compatible settings matched. Do not change the model and prompt together.

## 3. Run the live experiment

**Two scenarios × two configurations = four live executions**, giving two paired
comparisons. Run only after your instructor approves access and spending. If live
access is unavailable, save your configuration and hypothesis, then ask your
instructor before proceeding. The offline wiring check cannot evaluate your
prompt change.

### Live run: load your environment first

Only after the instructor approves access and spending, create or edit `.env` in
the repository root using `.env.example`. Set these entries with your gateway URL
and personal virtual key:

```dotenv
WORKSHOP_MODE=live
WORKSHOP_LIVE_ACK=approved-paid-calls
WORKSHOP_BASE_URL=https://YOUR-APPROVED-GATEWAY/v1
WORKSHOP_API_KEY=YOUR_VIRTUAL_KEY
```

In **bash or zsh (macOS/Linux)**, load the file into your current terminal:

```sh
set -a
source .env
set +a
```

Then run from that same terminal, using a new output directory:

```sh
python -m workshop.session2 --mode live --config outputs/session2-variants.json --output outputs/session2-live
```

Use only your own trusted `.env`; keep it out of Git. Python does not load it
automatically. Inspect `outputs/session2-live/` in the next step.

Each execution has its own configured allowance; there is no shared experiment
budget in this runner. Do not treat those allowances as actual charges.

## 4. Inspect and explain the results

Open `outputs/session2-live/comparison.csv` in a spreadsheet for the four-row
summary from your live experiment. Compare the two configurations **within each
scenario**. Follow up in:

```text
outputs/session2-live/<scenario>/<variant-id>/run-1/review.html
outputs/session2-live/<scenario>/<variant-id>/run-1/trace.jsonl
```

Variant IDs are the `id` values in your copied configuration. The review shows
checks, returned evidence and the final outcome; the trace shows event order.
The runner also saves `comparison.json` and the exact run configuration. Session 2
has individual HTML reviews and a CSV summary, without a combined HTML dashboard.

Record the prompt change, tool path, recommendation, remaining gaps, attempts,
elapsed time and whether the result supports your hypothesis. Actual live cost
and usage are currently unavailable in the general runner (`null`); reservations
are not billing. Use separately verified instructor accounting only when supplied.

## Discuss the decision to keep a change

> “We made this scenario cheaper. Before adopting the change, we need to check what it made worse elsewhere.”

To check whether a change helps across different situations, you would need to generate and review scenarios covering the capabilities and risks that matter to your application. Establish a baseline, then run the same set of scenarios for each experiment and compare the results for each capability. Ask your instructor about **Risk Eval**,
Agentic Blue's solution for this approach.

This workshop keeps the two-scenario exercise; no broader evaluation suite or
Risk Eval integration is implemented here.

Our two scenarios demonstrate the comparison process; a broader eval suite would support the decision to keep the change.

You are done when you can show both paired comparisons, explain what stayed fixed
and what changed, and state what your evidence can and cannot establish. Keep your
configuration and results locally in Git-ignored `outputs/`; do not commit results,
keys or `.env`. Run `python -m pytest -q` for the offline support checks.

## Next session

When you finish, follow [Move from Session 2 to Session 3](session2-to-session3.md).
