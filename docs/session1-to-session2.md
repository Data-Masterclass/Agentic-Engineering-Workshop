# Move from Session 1 to Session 2

Use this at the instructor's Session 2 handoff. `main` remains the Session 1
starter. `starter/session-2` adds the prepared Session 2 tools, synthetic
PDFs and comparison runner. **Merge it into your own work; do not switch directly
to the instructor checkpoint.** Your Session 1 tool, agent, prompt and graph stay
in their existing files. Session 2 runs separately under `workshop.session2`; it
does not silently replace or extend your Session 1 agent.

Run these commands from your clone with the workshop virtual environment active.

## 1. Save your Session 1 work

Inspect your changes, then create your personal continuation branch:

```sh
git status --short
git switch -c my-session-2
```

If those names already exist from an earlier attempt, stop and inspect the
branches with the instructor; do not reset them or force their replacement.
If you have uncommitted exercise edits, save the three files explicitly:

```sh
git add src/workshop/tools.py src/workshop/agent.py src/workshop/graph.py
git commit -m "Save my Session 1 exercise"
```

Skip that add/commit step if your edits are already committed. Review and commit
any other intentional source/document edits individually. Do not use `git add .`
for this handoff. Keep `.env`, keys and generated results outside commits.
If `git status --short` still lists changes or untracked files, resolve them with the instructor before merging. Do not discard
or automatically stash files just to obtain a clean status.

Create a saved Session 1 branch **after** committing your work:

```sh
git branch session-1-saved
```

## 2. Bring in the Session 2 checkpoint

This fetch downloads Git objects; it does not call a model or change your files.
The merge brings in the checkpoint while retaining your Session 1 commits:

```sh
git fetch origin
git merge --no-edit origin/starter/session-2
```

The prepared checkpoint leaves `src/workshop/tools.py`, `agent.py` and `graph.py`
unchanged relative to the Session 1 starter. Confirm that your versions survived
byte for byte; the following diff should print nothing and exit successfully:

```sh
git diff --exit-code session-1-saved -- src/workshop/tools.py src/workshop/agent.py src/workshop/graph.py
git merge-base --is-ancestor session-1-saved HEAD
git status --short
```

If Git reports conflicts, stop. Do not choose "ours"/"theirs" for every file or
replace your exercise with a reference solution. Before resolving anything, you
can return to the clean pre-merge state using `git merge --abort`; your committed
work and `session-1-saved` remain available. Ask the instructor to inspect the
specific conflict. A successful merge needs no abort. To rerun only Session 1
later, use its normal commands on your current branch; no branch switch is needed.

## 3. Verify your saved Session 1 work offline

With dependencies from initial setup already installed, refresh the editable
package metadata without dependency downloads:

```sh
python -m pip install --no-index --no-deps --no-build-isolation -e .
python -m workshop.cli check --case reading-conflict
python -m workshop.cli check --case missing-evidence
python -m pytest -q
```

Session 1's `check` is always offline. `NOT_IMPLEMENTED_YET` means a TODO remains;
completed supported work reports `SUPPORTED_OUTCOME`. Regressions need attention.
Do not run the `original_scaffold` assertions as a completion gate: they describe
the untouched starter, not your implementations.

Next, open `docs/session2.md`. Run its Step 1 offline wiring check **once**, then
prepare your prompt change and follow its approved live experiment. The transition
does not run that check again or grant live access. Scripted replies check wiring,
not prompt quality.

After merging, `outputs/` is ignored. This does not untrack files previously
committed: if you accidentally committed credentials, stop and tell the instructor. Do not push your work as part
of this handoff. Live access is a separate instructor-controlled step; these
instructions neither configure credentials nor enable public inference.

After merging, open `docs/session2.md` for the Session 2 instructions.
