---
name: pr-review
description: Run a thorough code review of a pull request covering file-level risk, line-level findings, CI status, and review threads. Use when asked to review a PR by number or URL, or on /pr-review <num>; for Dash Core final merge-gate decisions, use dash-pr-final-review.
---

# PR Review

Run a thorough, evidence-backed code review of a single GitHub pull request.

For **Dash Core final merge-gate calls** (`MERGE` / `BLOCK`), use `dash-pr-final-review` instead. For **Bitcoin Core backports into Dash Core**, run `backport-pr-codereview` alongside this review.

## Workflow

1. **Gather PR state.** Fetch metadata, diff, CI checks, and open review threads with `gh` — or use the bundled packet helper (`scripts/review_pr.py`, next to this file) for a quick structured snapshot:

   ```bash
   python3 scripts/review_pr.py <PR_NUMBER> [--repo owner/repo] [--json-only]
   ```

   Treat any heuristic flags from `review_pr.py` as starting prompts, never as confirmed findings.

2. **Read the real diff and surrounding code.** Inspect `gh pr diff` and read callers/callees in a local checkout when behavior is non-obvious. Do not review from the PR title or summary alone.

3. **Review across four passes:**
   - **Correctness & edge cases:** does the patch solve the stated problem without regressions, broken callers, or dropped invariants?
   - **Security & reliability:** input validation, auth/trust boundaries, error paths, concurrency/lifetimes, consensus or state safety.
   - **Scope & design:** minimal change, clean fit with existing patterns, no accidental refactoring or scope creep.
   - **Tests & CI:** do tests actually prove the change? Distinguish genuine patch failures from CI flakes/infra issues.

4. **Check discussion context.** Read unresolved human and bot review threads; note what is already answered, superseded, or still open.

5. **Conclude clearly:** `APPROVED`, `APPROVED WITH SUGGESTIONS`, or `REQUIRES CHANGES`.

## Output contract

1. **Verdict** (`APPROVED`, `APPROVED WITH SUGGESTIONS`, or `REQUIRES CHANGES`) + 1–3 sentence summary.
2. **Findings** ordered by severity (`high`, `medium`, `low`), each with `file:line`, observed behavior, and concrete fix.
3. **CI & thread status** — failing/pending checks and any open review threads that matter.
4. **Gaps / not verified** — anything you could not run or inspect.

## Guardrails

- Base every finding on observed code behavior, not style nitpicks.
- Do not post comments or formal GitHub reviews unless asked. When posting on GitHub, follow `leaving-pr-comments`.
- If required checks are failing or the branch conflicts with base, escalate to `REQUIRES CHANGES` unless the user explicitly scopes the review to code only.
