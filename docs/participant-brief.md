# Session 1 participant brief

Complete **three small TODOs in about 20 minutes**: write the PDF review tool, create the investigation agent, and wire the graph. Basic Python is enough; a coding assistant is optional. Complete [installation/preflight](session1.md#before-class-install-and-check-the-environment) before class. No diagram or workflow-mapping assignment is required.

Use one recoverable invoice: `reading-conflict` reads quantity **100** in extraction, while its source page shows **10** Archive boxes at EUR 12.00 each. Matching and missing-evidence cases are available as additional examples.

## Your three TODOs

| TODO | Input → work → output | Boundary / provided support |
|---|---|---|
| 1. PDF review tool (~4 min) | Invoice ID/page → call supplied reader → structured page observations | Tool observes; it never edits the invoice. Rendering, transport, source/argument checks and limits are provided. |
| 2. Investigation agent (~6 min) | Extracted invoice, flagged questions and actual PDF observations → propose useful evidence request, findings or handoff | Agent proposes; prepared Python checks evidence, accepts corrections and determines the recommendation. Client and structured parser are provided. |
| 3. Wire the graph (~10 min) | Registered prepared/learner nodes → add connections/conditional edges → compiled runnable graph | Provided routing selects tools/findings/handoff. Validate first; revalidate accepted findings; always finalize before human review. |

The three edit locations are `src/workshop/tools.py` (TODO 1), `src/workshop/agent.py` (TODO 2), and `src/workshop/graph.py` (TODO 3). [Hints](session1-hints.md) name the interfaces and required connections without supplying the completed tool, agent or graph.

The **tool observes, the agent chooses what to investigate, and the graph controls when they run**. `review_pdf_page(invoice_id, page)` is the only model-selected tool, constrained to the current invoice and page 1. Business lookup tools are not part of this exercise. No arbitrary paths, URLs or SQL. Invoice/retrieved text is data, not instructions.

## Inspect the shared case notebook

| Field | Meaning |
|---|---|
| `original_extraction` | Original values, extraction source/version and PDF hash |
| `candidate` | Current invoice values after accepted prepared handling |
| `checks` / `questions` | Sanitized flagged identifiers/statuses and questions; no passing-check internals or business-record values |
| `result` (workflow only) | Latest proposed requests/findings/handoff for routing; not sent back in the investigation view |
| `evidence` | Actual page observations returned through the tool |
| `correction_history` | Accepted before/after values and supporting evidence IDs |
| `handoff` / `terminal` / `recommendation` | Explanation, terminal condition and prepared recommendation |

The workflow keeps proposed results for routing; the learner investigation receives only the permitted view above, excluding `result`, terminal internals and raw records. Prepared validation privately retains supplier/order/line/receipt/history records and source-completeness metadata, then rechecks accepted findings against them. The agent gets an ask-only client, not the full runtime. Prepared support owns credentials/clocks/bounds; editing a snapshot does not register evidence. This is an inspectable teaching boundary, not tamper-proof isolation from someone editing the repository.

PO/receipt agreement flags a possible misreading but cannot prove what the invoice says. Direct clear page evidence can support a quantity correction; ambiguous, unavailable or conflicting readings stay unresolved. Citations establish provenance, not factual correctness. Original 100 and accepted history remain inspectable.

## Provided validation context

| Contents | Selected Session 1 packet |
|---|---|
| Supplier master | One synthetic supplier and fictional bank account per case |
| Purchase orders | One relevant PO per case |
| PO lines | One Archive boxes line, 10 EA at EUR 12.00 |
| Receipts | Selected receipts; missing case explicitly unavailable |
| Invoice history | One illustrative historic invoice; separate complete duplicate-scope assertion where available |
| Source completeness (metadata) | Read-only metadata retained by validation; not an investigation log or agent input |

The SQLite database is a **small provisional synthetic pack**, with deliberately limited scope. The prepared loader supplies the selected packet to validation only. The Session 1 agent receives no supplier/PO/receipt/history records or completeness metadata. Validation uses its retained packet and registered page evidence; it does not secretly retrieve more records. The complete duplicate-scope assertion covers only the selected supplier/invoice-number query as of 2026-10-01; the illustrative history alone is not proof of no duplicate.

## Exception categories to discuss

| Category | Example | Session 1 behavior |
|---|---|---|
| Missing/misread fields | Quantity 100 versus source 10 | Page review may support a quantity reading correction |
| Supplier/bank discrepancies | Bank differs from supplied master | Confirmed bank conflict escalates; no model editing of bank/supplier IDs |
| Missing/ambiguous order matches | No single supplied PO/line | Unresolved; no invented IDs or hidden lookup |
| Price/quantity/UOM | PO disagreement or incompatible units | Flag discrepancy; no implicit unit conversion |
| Receipts/coverage | Missing receipt pack or incomplete scope | Remains unresolved, never treated as zero/no issue |
| Totals/currency | Line maths, VAT, gross, currency conflict | Deterministic EUR/cents/19% VAT checks; confirmed currency conflict escalates |
| Duplicate candidates | Same supplier/invoice number | Exact supplied match blocks; unavailable complete scope stays unresolved |

## Try it and review

Run `workshop check --case reading-conflict` and `python -m pytest -q`. Inspect checks, page observations and correction history in the printed review/trace. The check distinguishes unfinished tool/agent/graph work from supported behavior and regression; no test-expectation edits are needed.

Offline mode uses **fixed model responses**, independent of prompts. It tests interactions, not reasoning or prompt improvements. The original starter hands off explicitly until the TODOs are completed. Live VLM mode requires deliberate configuration and later approval/verification; live errors never silently use fixtures.

All mandatory checks must pass for `READY_FOR_APPROVAL`. Missing evidence stays `NEEDS_CLARIFICATION`; blocking issues/terminal failures `ESCALATE`. Investigation allows 12 tool attempts, 8 model attempts and 120 seconds, including failures. A model-backed page read consumes both applicable attempt types. No progress/exhaustion prevents reentry. Human review is separate, with no automated deadline and no payment/accounting actions.
