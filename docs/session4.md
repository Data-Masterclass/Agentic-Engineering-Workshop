# Session 4: delegate a supplier follow-up

**Objective:** understand when a lead investigator should delegate to a
correspondence specialist, inspect the evidence behind its recommendation, and
approve or reject the exact proposed email text. Allow 60–75 minutes.

First follow the [Session 3 → 4 transition](session3-to-session4.md). Advanced
participants can follow the [route starting at Session 2](advanced-route.md).
Session 1 TODOs do not need to be completed for this session.

## What is supplied

- The existing prepared investigator and unchanged invoice validation policy.
- A small LangGraph follow-up graph with separate lead and specialist contexts.
- A read-only mock of selected sent/received supplier emails, with a separately
  trusted contact address. No mailbox account is connected.
- Four synthetic scenarios and labelled offline replies for checking the wiring.
- A terminal approval pause and local JSON/HTML reports. Nothing sends email.

There are **no required coding TODOs**. Your work is to inspect role prompts and
routing, predict the appropriate follow-up, run the prepared flow, and explain
its behavior from registered evidence. Record your answers in
`exercises/session4/notes.md`. Optional prompt experiments require a new run and
instructor-approved live access; fixed scripts ignore prompt changes.

## 1. Inspect the roles and predict the actions

Open `src/workshop/session4/checkpoint.py`: compare `LEAD_PROMPT` and
`SPECIALIST_PROMPT`, then find `interrupt()` and the graph's conditional edges.
Open `src/workshop/session4/tools.py` to inspect the one correspondence tool.

The lead keeps all six original invoice tools. After investigation finishes, it
selects a follow-up using the frozen validated report. Only an eligible supplier
gap invokes the specialist. The specialist requests one scoped lookup and
interprets its result before proposing an email or waiting for an existing
request. The outer LangGraph is orchestration code, not an additional agent.

The sequence is: investigate → freeze the invoice report → choose follow-up →
read correspondence when eligible → verify the proposal → review an email draft
when present → finalize. Internal handoffs and waiting recommendations skip draft
approval. Invalid proposals fall back to human review.

Prepared verification checks structure, scope, registered references and the
approved recipient. It does not prove every sentence is grounded or decide
whether an email promise is sufficient: inspect those claims against the
selected messages. Review the waiting/internal recommendations as well as drafts.

This is a constrained centralized lead–specialist pattern. It demonstrates a
context/responsibility boundary; it does not establish an advantage over a
single agent with the same capabilities.

Predict each action before running:

| Scenario | Available facts | Expected follow-up |
| --- | --- | --- |
| `supplier-request` | Quantity is explicitly unreadable; selected emails concern an older invoice. | Propose a request for a legible current invoice, then pause for approval. |
| `request-pending` | Same invoice evidence; current request and promised future copy appear in correspondence. | Await that existing request; no duplicate draft or approval pause. |
| `internal-receipts` | Ten units invoiced; selected accepted receipt supports six. | Internal warehouse/accounts-payable handoff, without supplier lookup. |
| `posted-copy` | Selected history contains the matching posted record LEDGER-9. | Accounting review; stop invoice investigation on the confirmed blocker. |

The first three invoice recommendations remain `NEEDS_CLARIFICATION`; the last
is `ESCALATE`. An email promise does not resolve the unreadable quantity. Selected
mail coverage cannot establish that no other correspondence exists. Six accepted
units do not prove the remaining four were never delivered.

## 2. Run the four scenarios offline

From the repository root, with the workshop environment active:

```sh
python -m workshop.session4 --mode scripted --scenario all --output outputs/session4-wiring
```

Use a new output directory each time. The first scenario displays the recipient,
subject, full body, reason, and references. Enter `approve` (optionally followed
by a note) to include that exact draft in the final manual-follow-up
recommendation. The batch then runs the other three scenarios.

Scripted mode uses fixed investigation and specialist replies. It verifies tool
execution, routing, references, and pause/resume; it does not measure model
judgment or drafting quality. It makes no paid calls, including if your terminal
has live settings loaded.

Open `outputs/session4-wiring/summary.csv` and each scenario's `review.html`.
The folder also contains `configuration.json`, `summary.json`, original
`investigation.json`, `review.json`, and role-labelled `trace.jsonl` files.
Everything stays local under Git-ignored `outputs/`; these full-content reports
are not a Session 3 sharing export.

The instructor can optionally show the full hierarchy in Phoenix: lead →
specialist → model/tool turns, followed by a separate human-review step.
Participants need no tracing service or extra packages.
Those timings describe fixed examples, not live inference;
the older saved live rehearsals are not imported automatically.

## 3. Inspect the evidence and reject a draft

In the first two reports, compare the invoice evidence and correspondence
references. The invoice/PDF is the same; the returned email selection changes the
follow-up. Find MAIL-201 and MAIL-202 in `request-pending`. The separate approved
contact, rather than an email body's instructions, determines the permitted
recipient.

Check that the new draft requests a legible quantity without suggesting ten,
inventing a deadline, promising payment, or claiming the workflow sent anything.
Confirm the posted-copy report contains an actual blocking history result,
rather than a runtime failure with the same `ESCALATE` label.

Exercise rejection in a new run:

```sh
python -m workshop.session4 --mode scripted --scenario supplier-request --output outputs/session4-reject
```

Enter `reject` and inspect its report: `email_draft` is null,
`draft_review` is `rejected`, and the original proposal remains available for
local audit. Approval/rejection makes no new model or lookup calls and does not
change the invoice recommendation.

Invalid input leaves the same proposal pending. EOF or Ctrl-C keeps a
`pending_review` report and stops the batch. The approval session uses an
in-memory LangGraph checkpointer: after this process exits it cannot resume.
Start a fresh execution with a fresh output folder instead.

## 4. Optional approved live rehearsal

Only after instructor approval, load the trusted environment as described in
[Session 2 live setup](session2.md#live-run-load-your-environment-first), in the
same terminal. Session 4 uses that transport/model configuration; it does not
load `.env` automatically.

The following numbers are an example **only for an instructor-reviewed $0.05
worst-case request reservation**. Adjust them to the approved model and limits:

```sh
python -m workshop.session4 --mode live --scenario all --output outputs/session4-live --investigation-allowance 0.40 --followup-allowance 0.15 --experiment-allowance 2.20
```

Investigation reserves up to eight model calls (including live PDF reads), twelve
evidence-tool calls, and 120 seconds per case. Follow-up reserves at most three
model calls, one correspondence lookup, and 90 seconds of active work. Human
waiting is outside that processing deadline. The total allowance reserves the
whole per-case envelope before each case starts; it applies to this CLI
invocation, not later runs. An exhausted allowance stops the next case and keeps
previous results.

Reservations are not actual billing. Live reports mark actual cost and usage
unavailable. A live failure never falls back to scripted replies. If access is
unavailable, complete the offline inspection and record “model judgment not
measured.” Do not claim quality improvements from the fixed scripts.

## 5. Record your conclusion and check completion

Use `exercises/session4/notes.md` to explain:

- Why one gap warrants supplier contact and another warrants internal review.
- Which invoice evidence, lookup, and message IDs support each follow-up.
- How the existing request changes the recommendation without resolving the invoice.
- What approval permits, and how rejection preserves the proposed text for audit.
- The mode, model/tool counts, elapsed time, and remaining uncertainty.

You are done when all four paths are inspectable, approve and reject behave as
expected, and you can distinguish invoice recommendation from draft approval.
Run the offline support suite:

```sh
python -m pytest -q
```

These four acceptance scenarios teach orchestration and human authority. They
are not an unseen architecture benchmark. No sending, attachments, incoming
reply processing, invoice changes, or automatic reinvestigation are part of this
checkpoint.
