# CLG (Context Freeze v1): architecture and decision record

The constraint: nothing is inferred, sent or saved until you approve the exact redacted preview, and no generated next-step command is executed.

## System walk

`collect()` runs read-only git commands (branch, HEAD commit, tracked changed filenames) with GIT_CONFIG_GLOBAL pointed at /dev/null, prompts disabled and a 5-second timeout per call. Selected text is capped at 12,000 characters. Redaction rewrites private-key blocks, authorization lines, bearer tokens, known key shapes (sk-, gh[pousr]_, AKIA), api-key/password-style assignments and local home paths in the selected text, the branch name and the filename list; filenames that look sensitive are dropped and counted. The cleaned snapshot is hashed (SHA-256 over canonical JSON) and shown as a preview whose warnings travel with it. Approving a different digest than the preview's is refused. The restart note is then written, by the offline mock (default) or the opt-in Meta provider.

## Decision records

### D1. Offline mock by default, honest unknowns

- Choice: the default restart note marks the task and blocker "Unknown" instead of guessing, and its next steps tell the user to confirm the task themselves (clg/core.py, mock_restart). The note is explicitly labelled "OFFLINE MOCK - no Meta inference".
- Evidence: the Meta provider (`provider='meta'`) has never made a live call; it needs MODEL_API_KEY and no key, credits or billing are configured (README).
- Not yet built: a verified live Meta call, failure-mode evaluation, a recorded working demo (README's own list).

### D2. Approval binds the exact bytes

- Choice: the preview's digest is SHA-256 over the canonical cleaned snapshot; `check_preview` compares with hmac.compare_digest and a mismatched approval digest raises, so an approval cannot be replayed against edited contents.
- Alternative: approve-by-button with no digest; rejected because the user would not know what they approved.

### D3. Redaction with the limits printed on it

- Choice: heuristic redaction plus filename filtering, and the preview itself carries the warning "Heuristic redaction is not a secret guarantee. Review every visible field." plus "A summary does not save unstaged source changes."
- Limits: redaction is pattern-based; untracked files, external state and dirty file contents are not covered (README limits).

### D4. Loopback-only UI, no ambient authority

- Choice (clg/ui.py): the server binds loopback, checks the Host header, embeds a per-launch random token in the page, sends a strict CSP (default-src 'none'), no-store and nosniff headers, and logs nothing about the selected evidence.
- Evidence: tests/test_ui.py and tests/test_core.py (unittest, no third-party packages).

### D5. Build provenance is part of the design

- The README records that implementation began October 26, 2026 after the hackathon kickoff, that it does not copy the older private Context Freeze repository or the separate morning prototype, and that no license grant is included yet. This file intentionally keeps that record visible rather than folding it into a features list.

## Interview questions this doc should let the owner answer

- What can an attacker learn from the preview page, and what three mechanisms stop them?
- Why does the mock return "Unknown" instead of a plausible guess?
- An approval digest from yesterday is presented against today's preview. What happens?
