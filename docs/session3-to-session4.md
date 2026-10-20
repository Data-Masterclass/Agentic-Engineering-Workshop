# Move from Session 3 to Session 4

Merge the next starter into your own participant branch. This adds a completed
LangGraph follow-up exercise; it preserves your earlier implementation,
configuration, and ignored local outputs. There are no new coding TODOs.

## 1. Save your current work

From your existing clone, with the workshop environment active:

```sh
git status --short
```

Review and commit intentional source/configuration edits, staging specific files.
Keep `.env`, keys, `outputs/`, and private results out of commits. Continue with a
clean working tree; do not discard or automatically stash work to clear it.

## 2. Merge the checkpoint and verify earlier work

```sh
git branch session-3-saved
git fetch origin
git merge --no-edit origin/starter/session-4
git diff --exit-code session-3-saved -- src/workshop/tools.py src/workshop/agent.py src/workshop/graph.py exercises/session2/variants.json exercises/session3/variants.json
git merge-base --is-ancestor session-3-saved HEAD
git status --short
```

The saved branch is a local checkpoint; the command does not switch branches.
The diff should print nothing, and status should be clean. If the saved branch
already exists, inspect it with your instructor rather than replacing it. If
there are conflicts, stop and ask for help; `git merge --abort` returns to the
clean pre-merge state. Do not choose all “ours” or “theirs.”

## 3. Run the prepared follow-up

Reuse the environment. Session 4 uses the existing LangGraph dependency; it needs
no new service, mailbox account, or model SDK. Refresh the editable installation
offline if necessary:

```sh
python -m pip install --no-index --no-deps --no-build-isolation -e .
```

Open [Session 4](session4.md). Predict the four paths, run its scripted batch,
and inspect approval/rejection. The optional live rehearsal needs separate
instructor-approved settings and spending. Merging a checkpoint grants no live
access. Do not merge a reference branch over your exercise work.
