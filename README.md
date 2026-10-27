# CLG: Context Freeze v1

A local prototype that helps a developer resume an interrupted task. You pick a
Git repository and a short terminal excerpt, review a redacted preview, and save
a structured restart note. Check Git state again before you resume.

**Inference defaults to an offline mock.** The mock leaves the task and blocker as
unknown instead of guessing. A Meta Model API provider (`provider='meta'`) exists
in `clg/core.py`, but it has never made a live call: it needs `MODEL_API_KEY`,
and no key, credits or billing are configured. The mock remains the default in
both interfaces.

## Run

Requires Python 3.10+ and Git. No third-party Python packages.

```sh
python3 -m unittest discover -s tests -v
python3 demo.py
python3 -m clg.ui --repo /path/to/your/demo/repo
```

Open the loopback address the app prints. Start with a synthetic repository.
There is also a CLI:

```sh
python3 -m clg --repo /path/to/demo/repo --selection /path/to/selected.txt
```

Review the preview, then repeat with `--approve DIGEST --out /new/path/freeze.json`.
The UI downloads a JSON note after approval. Neither interface executes next steps.

## What works

- Explicit repository and optional selected text, capped at 12,000 characters.
- Read-only branch, commit and tracked changed filenames. No source contents or global history.
- Heuristic secret and path redaction. Approval is bound to the exact preview digest.
- Validated evidence inventory and one to three evidence-linked next steps.
- A warning when the branch or commit changed. Any tracked dirty state needs manual review.
- Exclusive CLI save that never silently overwrites an existing note.
- Loopback-only UI with request-token and origin/host checks.

## Limits

Redaction is not a guarantee. Review every field before saving or sharing.
Untracked files, external state and dirty file contents are not checked.
A restart note is not a source backup. The UI is an early prototype, not hardened
multi-user software. Not implemented: model calls, automatic commands, camera
sensing, a phone companion and measured fatigue detection.

Still to build: a verified live Meta call, failure-mode evaluation and a recorded
working demo. This is not a finished hackathon submission.

## Build provenance

This implementation began on October 26, 2026, after 12:47 pm America/Toronto,
following the kickoff. It does not copy implementation from the older private
Context Freeze repository or the separate morning prototype. The earlier concept
predates the event. Actual development times are retained, and no eligibility
certification is made.

Python and browser code use only their standard libraries. No third-party code,
model weights, assets or dependency packages are bundled. No license grant is
included at this stage.
