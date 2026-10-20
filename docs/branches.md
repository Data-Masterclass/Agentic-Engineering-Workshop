# Workshop branches and transitions

Keep your work in one clone and merge each next starter. The guides below save
intentional edits and check that earlier exercise files survive. Ignored local
configuration and results stay in place; do not discard work to obtain a clean
status or merge reference answers over it.

| Branch | Exercise |
| --- | --- |
| `main` / `starter/session-1` | Build the PDF tool, investigation agent and graph. |
| `starter/session-2` | Run a prompt comparison with a separate prepared investigator. |
| `starter/session-3` | Inspect, compare and export the saved experiment. |
| `starter/session-4` | Inspect lead/specialist delegation and review a draft recommendation. |

1. Begin with [Session 1 setup](session1.md#before-class-install-and-check-the-environment).
2. Follow [Session 1 → 2](https://github.com/Data-Masterclass/Agentic-Engineering-Workshop/blob/starter/session-2/docs/session1-to-session2.md), then [Session 2](https://github.com/Data-Masterclass/Agentic-Engineering-Workshop/blob/starter/session-2/docs/session2.md).
3. Follow [Session 2 → 3](https://github.com/Data-Masterclass/Agentic-Engineering-Workshop/blob/starter/session-2/docs/session2-to-session3.md), then [Session 3](https://github.com/Data-Masterclass/Agentic-Engineering-Workshop/blob/starter/session-3/docs/session3.md). Keep the complete Session 2 experiment and configuration.
4. Follow [Session 3 → 4](https://github.com/Data-Masterclass/Agentic-Engineering-Workshop/blob/starter/session-4/docs/session3-to-session4.md), then [Session 4](https://github.com/Data-Masterclass/Agentic-Engineering-Workshop/blob/starter/session-4/docs/session4.md).

These links open the guide on the checkpoint where it exists, so you can read it
before merging. `main` remains the Session 1 code checkpoint. For the prepared
Sessions 2–4, advanced groups may use the [route starting at Session 2](https://github.com/Data-Masterclass/Agentic-Engineering-Workshop/blob/starter/session-4/docs/advanced-route.md).

Session 3's `compare`, `context` and `export` inspect saved results without model
calls. If no live experiment exists, use its labelled offline fallback. Fixed
scripts cannot measure prompt improvement. A further live experiment is optional
and needs instructor approval. Session 4's scripted exercise needs no mailbox,
tracing service or live key and sends nothing.

Keep `.env`, keys and generated results local; [.env.example](../.env.example)
describes settings. Merging a checkpoint does not grant live access.
