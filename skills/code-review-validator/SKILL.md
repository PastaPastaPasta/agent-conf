---
name: code-review-validator
description: Run an unbiased code review on completed implementations before final handoff. Use when non-trivial code changes are done and Codex should verify correctness, regressions, architecture fit, and security or reliability risks.
---

# Code Review Validator

Review code changes with a quality-gate mindset and report findings in severity order.

## Inputs

Collect:
- Intended outcome of the implementation
- Scope to review (files, branch, or commit range)
- Known constraints (performance targets, compatibility, deadlines)

## Workflow

1. Confirm what changed.
Inspect real diffs (`git status --short`, `git diff`, or commit range) instead of reviewing only final file snapshots.

2. Review in four passes.
- Correctness and completeness: does the change solve the stated task without functional gaps?
- Quality and maintainability: readability, duplication, naming, testability, and complexity growth.
- Architecture and design: fit with existing patterns, coupling/cohesion, long-term maintainability.
- Security and reliability: input handling, auth boundaries, error paths, race conditions, data integrity.

3. Prioritize findings.
List high-severity issues first. Include exact file references and concrete remediation guidance.

4. Identify gaps and uncertainty.
Call out missing tests, unverified assumptions, and areas not reviewed.

5. Conclude with a clear status.
Use:
- `APPROVED`
- `APPROVED WITH SUGGESTIONS`
- `REQUIRES CHANGES`

## Output Contract

1. `Findings` (ordered by severity, each with file path/line)
2. `Open questions or assumptions`
3. `Approval status`
4. `Brief summary` (optional and short)

## Guardrails

- Base claims on observed code behavior, not style preference.
- Prefer actionable fixes over abstract criticism.
- Do not hide critical risks behind long summaries.
- If evidence is insufficient, state uncertainty explicitly.
