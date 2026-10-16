# Agent Engineering Workshop

**Session 2 checkpoint.** Compare one prompt change on the same model across two invoice scenarios. Follow [the Session 1 → 2 transition](docs/session1-to-session2.md) before opening [Session 2](docs/session2.md).

## Workshop flow

| Session | What you do |
| --- | --- |
| [Session 1](docs/session1.md) | Build a PDF tool, investigation agent and graph. |
| [Session 2](docs/session2.md) | Run one offline wiring check, then an approved live prompt experiment. |
| Session 3, after merging `starter/session-3` | Read an offline trace demo, then run an approved live change-and-compare experiment and inspect/export its saved results locally. |

First installation: follow [Session 1 setup](docs/session1.md#before-class-install-and-check-the-environment) using Python 3.11, Git and your editor. No account, gateway or key is needed for offline checks. Installation downloads ordinary Python dependencies.

Between sessions, keep your own branch and virtual environment; merge the next starter using the transition guide. Do not create another clone or replace your completed exercise files. [Branch and transition instructions](docs/branches.md) explain the sequence.

## Your work and results

Session 1 has three TODOs in `src/workshop/tools.py`, `src/workshop/agent.py` and `src/workshop/graph.py`. [The participant brief](docs/participant-brief.md) and [hints](docs/session1-hints.md) explain their contracts. Sessions 2 and 3 use a separate prepared investigator; they preserve your Session 1 code and add no implementation TODOs.

Offline fixed responses check the workflow; they do not evaluate prompt improvements. Live experiments require instructor-approved access, settings and spending. You use your own generated reports and traces; no private reference files are needed.

Session 1 writes local reports under `state/`. Sessions 2 and 3 write configuration and results under `outputs/`. Keep generated results, `.env`, keys and `.venv/` out of Git. Run `python -m pytest -q` for offline support checks; unfinished Session 1 TODOs have their own progress checks.

The data is a small [synthetic demonstration pack](docs/data-contract.md). Tools retrieve evidence; prepared validation determines a recommendation for separate human review. The workshop performs no payment or accounting action.
