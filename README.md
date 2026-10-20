# Agent Engineering Workshop

**Session 4 starter.** Delegate a supplier follow-up, inspect selected correspondence, and approve or reject an email draft recommendation. Follow [the Session 3 → 4 transition](docs/session3-to-session4.md), then [Session 4](docs/session4.md). Advanced groups can [start at Session 2](docs/advanced-route.md) without completing Session 1 TODOs.

## Workshop flow

| Session | What you do |
| --- | --- |
| [Session 1](docs/session1.md) | Build a PDF tool, investigation agent and graph. |
| [Session 2](docs/session2.md) | Run one offline wiring check, then an approved live prompt experiment. |
| [Session 3](docs/session3.md) | Read an offline trace demo, then run an approved live change-and-compare experiment and inspect/export its saved results locally. |
| [Session 4](docs/session4.md) | Inspect lead/specialist roles, consult mock supplier correspondence, and review a manual email draft using LangGraph approval. |

First installation: follow [Session 1 setup](docs/session1.md#before-class-install-and-check-the-environment) using Python 3.11, Git and your editor. No account, gateway or key is needed for offline checks. Installation downloads ordinary Python dependencies.

Between sessions, keep your own branch and virtual environment; merge the next starter using the transition guide. Do not create another clone or replace your completed exercise files. [Branch and transition instructions](docs/branches.md) explain the sequence.

## Your work and results

Session 1 has three TODOs in `src/workshop/tools.py`, `src/workshop/agent.py` and `src/workshop/graph.py`. [The participant brief](docs/participant-brief.md) and [hints](docs/session1-hints.md) explain their contracts. Sessions 2–4 use a separate prepared investigator; they preserve your Session 1 code and add no implementation TODOs. Session 4 supplies the graph: predict, run, inspect and explain its four follow-up scenarios.

Offline fixed responses check the workflow; they do not evaluate prompt improvements. Live experiments require instructor-approved access, settings and spending. You use your own generated reports and traces; no private reference files are needed.

Session 1 writes local reports under `state/`. Sessions 2–4 write configuration and results under `outputs/`. Session 4 reports contain full correspondence and draft text; keep them local. Keep generated results, `.env`, keys and `.venv/` out of Git. Run `python -m pytest -q` for offline support checks; unfinished Session 1 TODOs have their own progress checks.

The data is a small [synthetic demonstration pack](docs/data-contract.md). Tools retrieve evidence; prepared validation determines a recommendation for separate human review. The workshop performs no payment or accounting action.

Session 4 draft approval permits including the exact text as a recommended manual follow-up. It does not send email or approve the invoice; no mailbox account is connected.
