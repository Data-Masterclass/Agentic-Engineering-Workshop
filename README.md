# Agent Engineering Workshop

**Start with the [participant workshop guide](docs/workshop-guide.md)** for the invoice scenario, the full four-Part route, and what you will build, compare and review. Then use the session instructions below for commands.

For installation, follow [Session 1 setup](docs/session1.md#before-class-install-and-check-the-environment).
`main` contains the Session 1 starter. Keep one clone and your own work; merge
later checkpoints using the [branch and transition guide](docs/branches.md).
The links below open each session's published instructions, including files that
are not present in your checkout until you merge that checkpoint.

## Workshop flow

| Session | What you do |
| --- | --- |
| [Session 1](https://github.com/Data-Masterclass/Agentic-Engineering-Workshop/blob/starter/session-1/docs/session1.md) | Build the PDF tool, investigation agent and graph: three coding TODOs. |
| [Session 2](https://github.com/Data-Masterclass/Agentic-Engineering-Workshop/blob/starter/session-2/docs/session2.md) | Check the prepared investigator offline, then run one approved live prompt comparison on two scenarios. |
| [Session 3](https://github.com/Data-Masterclass/Agentic-Engineering-Workshop/blob/starter/session-3/docs/session3.md) | Inspect and export the same saved Session 2 experiment; explain whether to keep, reject or defer the change. |
| [Session 4](https://github.com/Data-Masterclass/Agentic-Engineering-Workshop/blob/starter/session-4/docs/session4.md) | Inspect lead/specialist roles and mock supplier correspondence; approve or reject a manual email draft recommendation. |

Advanced groups can [start at Session 2](https://github.com/Data-Masterclass/Agentic-Engineering-Workshop/blob/starter/session-4/docs/advanced-route.md) without
completing Session 1 TODOs. Sessions 2–4 supply their implementation.

## Setup and results

Use Python 3.11, Git and your editor. Follow the setup guide above, then the guide
for your current session. No account, gateway or key is needed for offline
checks; dependency installation needs internet access. Keep your environment
between sessions. Do not replace your exercise files with checkpoint versions.

Live experiments require instructor-approved access, settings and spending.
Fixed scripted responses check wiring; they do not measure prompt improvements.
Session 3 inspection and export make no new model calls. A further live experiment
is optional and needs separate approval.

Session 1 writes local reports under `state/`; later sessions use `outputs/`.
Keep generated results, `.env`, keys and `.venv/` out of Git. Session 4 reports
contain correspondence and draft text and are not supported by the Session 3
sharing exporter. Run `python -m pytest -q` for offline support checks; unfinished
Session 1 TODOs have their own progress checks.

The [participant brief](docs/participant-brief.md) and [hints](docs/session1-hints.md)
explain Session 1's contracts. The [synthetic demonstration pack](docs/data-contract.md)
is for learning. Prepared validation recommends an outcome for separate human
review. No payment, accounting action or email sending occurs. Session 4 approval
only permits including the exact draft as a recommended manual follow-up.
