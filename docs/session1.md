# Session 1: build an invoice investigation

## Before class: install and check the environment

Use Python 3.11, Git and your editor. Python 3.11.15 on macOS arm64 is verified;
other platforms/Python versions have not been verified. Clone this public
repository using HTTPS, then run commands from its root. No GitHub login is
needed to clone; dependency installation needs internet access.

```sh
git clone https://github.com/Data-Masterclass/Agentic-Engineering-Workshop.git
cd Agentic-Engineering-Workshop
python3 -m venv .venv
source .venv/bin/activate
export WORKSHOP_MODE=offline
python -m pip install -r requirements.lock
python -m pip install --no-deps --no-build-isolation -e .
python -m pip check
workshop seed
workshop preflight
```

Windows activation: `.venv\Scripts\activate`. Installation downloads ordinary dependencies; subsequent offline runs need no credentials, LiteLLM or Langfuse. Optional coding assistants are funded by you/your employer. `.env.example` documents settings; `.env` is not automatically loaded. Default mode is offline; use `export WORKSHOP_MODE=offline` if your shell previously enabled live calls.

`seed` resets only `state/workshop.sqlite`. `preflight` verifies fixture hashes, selected packets, PDF rendering and a prepared matching LangGraph smoke check. It never evaluates learner TODOs, so it remains useful after edits. Complete setup before class.

## Before coding: think in LangGraph

Start with [Thinking in LangGraph](https://docs.langchain.com/oss/python/langgraph/thinking-in-langgraph) as an introduction to the design approach: begin with the process, identify each step's job, choose shared state, then connect the steps. Use the invoice investigation as your example while reading.

In this exercise:

- [State](https://docs.langchain.com/oss/python/langgraph/graph-api#state) is the case notebook: the current invoice candidate, flagged checks and obtained evidence.
- [Nodes](https://docs.langchain.com/oss/python/langgraph/graph-api#nodes) do the work: validation, investigation, tool execution, applying findings and finalization. A node can run ordinary Python or call a model.
- [Edges](https://docs.langchain.com/oss/python/langgraph/graph-api#edges) connect those jobs: fixed transitions continue the process; conditional transitions choose whether to investigate, use a tool, revalidate or finish.

The state and node helpers are supplied. Your graph task connects them with LangGraph's API.

## The exercise: three TODOs, about 20 minutes

Use `data/invoices/reading-conflict.pdf` throughout: extraction reads quantity 100; the page shows 10. You will write a tool, create an investigation agent and connect the graph. [Hints](session1-hints.md) provide signatures and a short connection table.

### 1. Write the PDF review tool (~4 minutes)

Complete `review_pdf_page` in `src/workshop/tools.py`. Call the supplied `read_page(invoice_id, page)` and return its unchanged observations in the typed tool-response shape. This is the callable tool the agent requests. The reader, transport, rendering, argument/source checks and bounds are provided. Do not change invoice values here.

### 2. Create the investigation agent (~6 minutes)

Complete `investigate` and refine `PROMPT` in `src/workshop/agent.py`. Inspect the extracted invoice, flagged checks/questions and obtained PDF observations; use the prepared `runtime.ask` client/parser to propose a page request, supported findings or a handoff. The agent chooses what evidence is useful; prepared Python accepts/rejects corrections and determines the recommendation.

Investigation receives an allowlisted view: `original_extraction`, `candidate`, flagged `checks`, investigation `questions`, actual PDF `evidence` and accepted `correction_history`. Raw business records and completeness metadata stay with prepared validation, outside graph state. Passing checks, internal check details and prior proposed results are not sent to the agent. The supplied `runtime` argument is an ask-only client; credentials, clocks and enforcement stay in prepared support. Snapshot edits cannot register evidence. Prompts are formatted at call time.

### 3. Wire the graph (~10 minutes)

Complete `build_graph` in `src/workshop/graph.py`. `prepared_graph(nodes)` returns a LangGraph `StateGraph` with the five nodes registered. You connect them using [`add_edge`](https://docs.langchain.com/oss/python/langgraph/graph-api#normal-edges) for fixed transitions and [`add_conditional_edges`](https://docs.langchain.com/oss/python/langgraph/graph-api#conditional-edges) for choices based on the current state, then return the [compiled graph](https://docs.langchain.com/oss/python/langgraph/graph-api#compiling-your-graph).

Use `nodes.route_investigation` as the conditional selector after `investigate`: it returns the route for tools, findings or finalization. The [connection table](session1-hints.md#todo-3-wire-the-graph-10-minutes) lists the other supplied selectors. Validate first, return page observations to the investigator, revalidate accepted findings, and finish every terminal route.

```sh
workshop check --case reading-conflict
python -m pytest -q
```

`check` always uses offline fixed responses, even in a live-configured shell. It reports `NOT_IMPLEMENTED_YET` for safe unfinished tool/agent/graph work, `SUPPORTED_OUTCOME` for supported case behavior, or `REGRESSION` (exit 1) for failure/inconsistency. The first two exit 0. It checks evidence/history/revalidation where applicable, not prompt quality or completion of every TODO. Keep test expectations unchanged.

The recoverable case is the required exercise. You can also try these additional cases:

```sh
workshop check --case matching
workshop check --case missing-evidence
workshop run --case reading-conflict
```

Matching skips investigation. Missing evidence remains unresolved and hands off; terminal failures/confirmed blocking issues escalate. All recommendations require separate human review; no payment/accounting action exists. Only PDF page review is model-selected in this exercise.

Open the printed `state/<case>/review.html` in your browser. Inspect checks, observations, originals/current values and accepted corrections; `review.json` and `trace.jsonl` provide structured details. Reports are overwritten on rerun. Human review has no automated deadline.

Default `python -m pytest -q` verifies support/progress compatibility before and after edits. To check the original unedited scaffold separately: `python -m pytest -q -m original_scaffold`. These describe the unedited starter and are not participant completion gates.

Save your work in your own clone:

```sh
git status --short
git add src/workshop/tools.py src/workshop/agent.py src/workshop/graph.py
git commit -m "Complete my Session 1 exercise"
```

Keep `state/`, `.env` and credentials out of Git. No push is required.

## Optional live configuration

`workshop run --case reading-conflict` preserves the supplied extraction by default, including the deliberate quantity 100 error. In live mode only investigation and PDF review use the provider, so the recovery loop remains testable. The report records extraction source `verified-fixture` and live page evidence separately. This is an explicit input selection, not fallback after a failed live call. To test initial extraction too, opt in with `workshop run --case reading-conflict --extraction-source live`; a correct extraction of 10 may then pass validation without calling the agent/tool. `check` remains entirely offline regardless of this option or inherited environment settings.

Offline behavior never silently falls back from a failed live call. `WORKSHOP_MODE=live` plus `WORKSHOP_LIVE_ACK=approved-paid-calls` deliberately enables the Responses API client; `.env.example` lists required variables. A verified HTTPS gateway base ending in `/v1`, model alias, scoped key, total spend allowance and **worst-case per-call cost** must be supplied by an instructor. The client calls `/v1/responses` for investigation, extraction and image-based PDF review. The allowance conservatively reserves that worst-case cost before every model call (including extraction, live page review and tool follow-ups); it is not a metered billing integration. Incorrect cost configuration cannot enforce a real gateway spending cap.

For a verified reasoning model, the instructor may set `WORKSHOP_REASONING_EFFORT=low` (or another supported effort). Omit it for a model without reasoning support such as GPT-4o mini. No temperature is forced. `WORKSHOP_MAX_OUTPUT_TOKENS` defaults to 4096, accepts 1–8192 and includes reasoning tokens as well as visible output. Recalculate the conservative reservation for the chosen model, maximum input/image size and output limit before live use. Incomplete output terminates the run; it never automatically buys another attempt.

The provided transport advertises the native `review_pdf_page` function. It returns a validated proposal through the same `runtime.ask` contract, leaving the participant tool, agent and graph TODOs to be completed. The graph executes the tool through the prepared reader; only successfully validated observations are returned to the model with the matching call ID. There is no hidden tool loop. Stateless requests use `store: false` and retain encrypted reasoning/output items in memory for the run, outside graph snapshots and local traces. This setting does not itself establish a provider zero-retention agreement or disable gateway logging. A new runtime resets the conversation; the configured alias/key must stay fixed during a run.

PDF review uses a strict JSON output schema fixing the supported `lines.L1.quantity` field, live origin and selected page reference. The configured model/gateway must support structured outputs; an unsupported schema is an explicit failure, without retry or fallback to a weaker format. Runtime checks still reject an unsupported field rather than silently rewriting evidence.

Live extraction is separately bounded to one attempt and 30 seconds, with its cost deducted from the investigation's remaining allowance. Investigation allows at most 12 tool attempts, 8 model attempts and 120 seconds, including failures. A live page review consumes both attempt types. The HTTP timeout is 25 seconds, complete request JSON is limited to 3 MB, response bytes (including encrypted reasoning) to 256 KiB, and final structured JSON to 64 KiB; stricter investigation/evidence limits also apply. Accumulated conversation history counts toward the input bound. No automatic retries, redirect following or hosted tools are configured. A timed-out remote request cannot be recalled; its cost stays reserved and the run terminates. Human review has no automated deadline.

The offline support tests cover transport parsing, reasoning continuity, page
requests and failure/budget handling without provider calls. Actual model behaviour
requires a separately approved live run. Use only the endpoint, alias and limits
released by your instructor; a historical rehearsal does not grant live access.

## Next session

When you finish, follow [Move from Session 1 to Session 2](session1-to-session2.md).
