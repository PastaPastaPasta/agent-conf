---
name: security-report-investigator
description: Validate security reports, audit findings, bug bounty submissions, or vulnerability claims before making code changes. Use when Codex needs to independently investigate a reported security issue from scratch, confirm or refute the finding, reassess the reported severity, and produce a regression test or equivalent automated proof for any confirmed issue.
---

# Security Report Investigator

Investigate security claims from first principles. Do not trust the report's diagnosis, exploitability claim, or severity rating without independent evidence.

## Inputs

Collect:
- The full report text, proof-of-concept, reproduction steps, and claimed severity
- File paths, commits, branches, or version ranges implicated by the report
- Deployment assumptions, attacker capabilities, and any trust-boundary context
- User constraints for scope, testing, commits, or push behavior

If the report is missing file references, search for the affected code. If the report is ambiguous, state the assumptions you are validating.

## Workflow

1. Reframe the claim precisely.
Define the alleged asset at risk, attacker preconditions, entry point, vulnerable invariant, and claimed impact. Separate the reporter's theory from the concrete behavior you still need to verify.

2. Investigate from scratch.
Read the relevant code and surrounding logic. Trace data flow, privilege boundaries, validation layers, state transitions, persistence, and any existing mitigations. Check adjacent tests and historical fixes when they affect exploitability.

3. Reproduce or refute the issue.
Build the smallest realistic automated proof:
- Prefer a regression test in the package's normal test suite.
- Use an isolated exploit harness only when a normal test cannot express the issue cleanly.
- The proof must fail on vulnerable code and pass after the fix.

Never mark a report as confirmed without a concrete automated proof. If the issue cannot be reproduced after sufficient investigation, refute it or mark it partial with clear reasoning; do not paper over uncertainty with speculative fixes.

4. Decide the verdict.
Classify exactly one:
- `CONFIRMED`: the reported security issue is real as described or materially equivalent.
- `REFUTED`: the reported issue is not real in the current code or deployment model.
- `PARTIAL`: there is a real issue, but the report misstates the root cause, exploit path, scope, or remediation.

5. Reassess severity independently.
Rate severity from observed behavior, not from the report. Evaluate:
- required privileges
- attacker-controlled input reachability
- confidentiality, integrity, and availability impact
- blast radius and default exposure
- exploit reliability and required user interaction
- existing mitigations or configuration gates

State whether the reporter's severity is `accurate`, `overstated`, or `understated`, and explain why.

6. Take action only when warranted.
- For `CONFIRMED`: add the failing regression test first, implement the minimal correct fix, rerun the proof and relevant checks, then commit and push when repository policy permits.
- For `PARTIAL`: add the failing regression test for the real issue, implement only the corrected fix, and explain why the original report is incomplete or inaccurate.
- For `REFUTED`: do not edit code.

For agent-created commits, use `git commit -m "<message>"`.

7. Summarize outcome.
State the verdict, severity assessment, automated proof used, files changed if any, checks run, and any residual risk.

## Test Requirement

Treat the regression test as part of the investigation, not as optional cleanup.

- For `CONFIRMED` and `PARTIAL`, always add a regression test or equivalent automated proof artifact that demonstrates the issue before the fix and passes after the fix.
- If the natural reproduction path is destructive or too slow, reduce it to the smallest safe deterministic test that still proves the vulnerable behavior.
- If no such proof can be built, do not claim high-confidence confirmation.

## Optional Isolated Worktree

Use a dedicated worktree when isolating a risky fix:

```bash
cd "$(scripts/create_worktree.sh <branch-name>)"
```

This creates `worktrees/<branch-name>` from current `HEAD` using a new branch and prints the new worktree path.

## Response Contract

Use this structure in user-facing output:

1. `Verdict`: `CONFIRMED`, `REFUTED`, or `PARTIAL`
2. `Severity`: your rating plus whether the report's severity was accurate, overstated, or understated
3. `What I investigated`: exact files, code paths, assumptions, and behaviors checked
4. `Proof`: the regression test or exploit harness used to confirm or refute the issue
5. `Why`: concise reasoning tied to observed code behavior and attacker preconditions
6. `Action taken`:
- If fixed: list changed files, checks run, commit SHA/message, and push result when applicable
- If not fixed: explicitly state that no code changes were made

## Guardrails

- Never accept a security report on narrative plausibility alone.
- Never trust severity labels without independent impact analysis.
- Prefer minimal, behavior-preserving fixes over broad hardening refactors.
- Preserve the automated proof in-tree whenever feasible so the issue cannot silently regress.
- If confidence is low, extend the investigation before changing code.
- Follow the user's signing policy for commits and tags.

### scripts/
- `scripts/create_worktree.sh`: Create a feature worktree at `worktrees/<branch-name>` and print its path.
