# Workshop branches and transitions

Stay on your own participant branch and merge the next starter at each handoff.
Your saved exercise edits and ignored local results remain in the same clone.

| Branch | Exercise |
| --- | --- |
| `main` / `starter/session-1` | Build the Session 1 PDF tool, investigation agent and graph. |
| `starter/session-2` | Adds a separate prepared investigator and two-scenario prompt experiment. |
| `starter/session-3` | Adds an offline trace demo, a live one-change experiment, inspection and export. |

Start Session 1 from `main` or `starter/session-1`. Before merging Session 2, follow
[Move from Session 1 to Session 2](session1-to-session2.md). It saves your work and
checks that your three exercise files survive unchanged.

After the Session 2 merge, `docs/session2-to-session3.md` explains the next handoff.

Session 2 uses `workshop.session2`, a prepared investigator separate from your
Session 1 agent. Run its offline wiring check once, then configure and run the
approved live experiment. Step 4 inspects your own `outputs/session2-live/` results.

Session 3 begins with an offline demo for learning to read traces. Its live
experiment also uses the Session 2 runner; `workshop.session3 compare`, `context`
and `export` inspect saved results locally without model calls. Prompt improvement
cannot be measured using fixed offline replies.

The session guides and your own generated results are sufficient for these
exercises. Live access and spending need instructor approval. Keep `.env`, keys
and generated results local; [.env.example](../.env.example) describes settings.
