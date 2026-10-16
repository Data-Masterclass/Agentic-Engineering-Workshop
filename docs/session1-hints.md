# Session 1 hints: tool, agent and graph

Edit `src/workshop/tools.py`, `src/workshop/agent.py` and `src/workshop/graph.py` for TODOs 1, 2 and 3 respectively. Three TODOs stay incomplete; this guide gives contracts and connections, not a completed solution.

## TODO 1: write the PDF review tool (~4 minutes)

In `src/workshop/tools.py`, signature: `review_pdf_page(invoice_id, page, read_page)`.

The executor supplies `read_page`, a prepared reader bound to the validated current invoice/page. Call it once with those arguments. It returns a list of structured observations (`id`, `page_ref`, `field`, `value`, `confidence`, `excerpt`, `origin`). Return a dictionary with an `observations` key holding that unchanged list; `PageReviewResult` defines the response schema.

The stub returns `None`, producing an explicit unfinished-tool handoff if reached. Empty/unavailable source evidence is different. Do not invent/change readings, identifiers or references, mutate the invoice, retrieve business records, or open arbitrary paths/URLs. The prepared executor verifies the response against what the reader actually returned and registers evidence only after checks pass. Offline reading uses recorded page observations; live reading would call the configured VLM within tool/model/time/spend limits.

## TODO 2: create the investigation agent (~6 minutes)

In `src/workshop/agent.py`, signature: `investigate(state, runtime)`.

Inspect current `candidate`, `original_extraction`, sanitized flagged `checks`, investigation `questions`, obtained PDF `evidence` and accepted `correction_history`. Business records/completeness metadata stay privately with validation; passing-check internals and previous `result` are absent. The `runtime` argument exposes only `ask`, not records, clients, credentials or traces. Write/refine `PROMPT` to describe when page evidence is useful and when unresolved evidence should lead to a handoff.

Use `runtime.ask(PROMPT, state)` for bounded transport and typed parsing. Return its `InvestigationResult` as `.model_dump(mode="json")`. It proposes at most one page request, structured findings/corrections, or an explained handoff. The agent does not call the tool directly or approve the invoice; the graph/executor perform requests and prepared Python validates corrections.

A request has `name="review_pdf_page"`, current `invoice_id`, `page=1`. Findings contain `evidence_ids`, `corrections`, `note`; a correction contains `field`, `value`, `evidence_id`. The supported field is exactly `lines.L1.quantity`; the evidence ID is a separate identifier. Only supported clear line-quantity readings can amend this Session 1 candidate. Snapshot edits do not create evidence. Offline model responses are fixed examples and ignore prompt changes.

Findings may accompany an explained handoff. Prepared handling checks proposed corrections and revalidates them before finalization; a handoff prevents further model/tool requests. It does not bypass evidence checks or make a recommendation on the agent's authority.

## TODO 3: wire the graph (~10 minutes)

In `src/workshop/graph.py`, signature: `build_graph(nodes)`.

`prepared_graph(nodes)` registers `validate`, `investigate`, `tools`, `findings`, `finalize` without connecting them. Replace the safe `scaffold(nodes)` fallback with this unconnected graph, add the connections below and return `.compile()`. `START`/`END` are already imported. CLI/progress launchers already attach your tool and agent to the prepared nodes.

| From | Destination / provided conditional selector |
|---|---|
| START | validate |
| validate | `nodes.policy`: investigate or finalize |
| investigate | `nodes.route_investigation`: tools, findings or finalize |
| tools | `nodes.after_tools`: investigate or finalize |
| findings | `nodes.after_findings`: validate or finalize |
| finalize | END |

Use `add_edge(source, target)` for fixed connections and `add_conditional_edges(source, selector, {route_value: node_name})` for choices. The routing choice is already supplied, so it is not a fourth TODO. `workshop.graph.run` executes with a recursion backstop, retains the last completed state on failure, and always performs deterministic final validation.

Matching must skip investigation. Page observations return to the agent; accepted findings return to validation. Missing evidence gets an explained handoff. No progress/failure/exhaustion is terminal. Human review stays separate.

Run `workshop check --case reading-conflict` and `python -m pytest -q`. Safe unfinished work is `NOT_IMPLEMENTED_YET`; supported fixed-case behavior is `SUPPORTED_OUTCOME`; failures are `REGRESSION`. The optional `-m original_scaffold` tests describe the unedited starter and are not completion gates. These checks cannot establish prompt quality or prove every TODO is complete.
