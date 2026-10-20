# Move from Session 2 to Session 3

Merge the next starter into your own participant branch. This adds Session 3
instructions and inspection/export tools while preserving your earlier code.
Do not switch to a reference branch or merge reference answers over your work.

## 1. Save your current work

From your existing clone, with the workshop environment active:

```sh
git status --short
```

Review and commit your intentional source/configuration changes, staging specific
files. Keep `.env`, keys and `outputs/` out of commits.
Continue only when `git status --short` is clean. Do not discard or automatically
stash work just to clear the status.

## 2. Merge the checkpoint and check your files

```sh
git branch session-2-saved
git fetch origin
git merge --no-edit origin/starter/session-3
git diff --exit-code session-2-saved -- src/workshop/tools.py src/workshop/agent.py src/workshop/graph.py exercises/session2/variants.json
git merge-base --is-ancestor session-2-saved HEAD
git status --short
```

`session-2-saved` is a new local branch pointing to your committed work; creating it
does not switch branches. The file diff should print nothing and the status should
be clean. Your Git-ignored `outputs/` configuration and results stay local.

If that saved branch already exists, inspect it with the instructor instead of
replacing it. If the merge reports conflicts, stop and ask for help. Before
resolving them, `git merge --abort` returns to the clean pre-merge state. Do not
choose “ours” or “theirs” for every file.

## 3. Continue the exercise

Reuse your environment; the participant commands need no new dependencies. Refresh
the editable installation offline if needed:

```sh
python -m pip install --no-index --no-deps --no-build-isolation -e .
```

After merging, open `docs/session3.md`. Inspect and export the complete saved
Session 2 experiment without new model calls. If live results are unavailable,
use the labelled offline fallback and record “prompt effect not measured.” A
further live experiment is optional and needs separate approval. This merge does
not grant live access or require another experiment.
