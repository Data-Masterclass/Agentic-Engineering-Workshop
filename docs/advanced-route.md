# Advanced route: start at Session 2

Use this route if your group already understands tools, state, and basic agent
loops. Sessions 2–4 supply a prepared investigator independently of Session 1;
you do not need to complete its three TODOs. Allow about 2.5–3 hours including a
15-minute orientation on invoice evidence and deterministic policy.

## 1. Install from the Session 2 checkpoint

Use Python 3.11, Git, and your editor. This public HTTPS clone needs no GitHub
login; dependency installation needs internet access.
Create your own participant branch:

```sh
git clone --branch starter/session-2 https://github.com/Data-Masterclass/Agentic-Engineering-Workshop.git
cd Agentic-Engineering-Workshop
git switch -c participant/my-work
python3 -m venv .venv
source .venv/bin/activate
export WORKSHOP_MODE=offline
python -m pip install -r requirements.lock
python -m pip install --no-deps --no-build-isolation -e .
python -m pip check
python -m pytest -q
```

On Windows activate with `.venv\Scripts\activate`. Installation downloads ordinary
Python dependencies; subsequent scripted runs need no keys. This support suite
allows unfinished Session 1 TODOs. Do not run the `original_scaffold` checks as a
completion requirement for this route.

This guide first appears on Session 4. If viewing it before class, keep the guide
open while you clone Session 2. Keep one clone, branch, and virtual environment
throughout the sessions.

## 2. Establish the single investigator — Session 2

Run the offline wiring check:

```sh
python -m workshop.session2 --mode scripted --config exercises/session2/variants.json --output outputs/session2-wiring
```

Then follow [Session 2](session2.md), starting with its prompt-change exercise.
Skip its Session 1 transition prerequisite. Understand the six evidence tools,
selected coverage, and the distinction between an agent's explanation and the
validator's recommendation. Allow 35–45 minutes. Live access and spending require
instructor approval; fixed scripts do not evaluate prompt changes.

## 3. Diagnose one change — Session 3

Follow [Session 2 → 3](session2-to-session3.md), then [Session 3](session3.md).
Preserve your prior edits, configuration and complete Session 2 experiment through
the merge. Inspect and export that same experiment without new model calls, then
explain whether to keep, reject or defer the prompt change. A second live batch
is optional. Use the labelled offline fallback if no live results exist. Allow
35–45 minutes.

## 4. Delegate and review — Session 4

Follow [Session 3 → 4](session3-to-session4.md), then [Session 4](session4.md).
Predict four follow-ups, inspect the mocked sent/received correspondence, and
approve or reject a draft recommendation. Allow 60–75 minutes. No required coding
TODOs, sending integration, or real mailbox access are involved.

You finish with an evidence-backed explanation of both investigation behavior
and the human approval boundary. Keep local configuration, results, and notes
private. This route demonstrates a small centralized lead–specialist flow;
it does not prove that multiple agents outperform a generalist.
