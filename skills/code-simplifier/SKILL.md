---
name: code-simplifier
description: Identify safe simplification opportunities in newly added or recently changed code while preserving behavior. Use when a task introduces substantial new code, duplication, extra indirection, or over-engineered patterns and Codex should reduce complexity before finalizing.
---

# Code Simplifier

Review changed code for simplification opportunities that reduce maintenance cost without changing behavior.

## Inputs

Collect:
- Scope: files, subsystem, or commit range to inspect
- Constraints: behavioral guarantees, API compatibility limits, and risk tolerance
- Validation expectations: tests, lint, typecheck, build, or smoke checks

## Workflow

1. Inspect the actual change set first.
Use `git status --short` and `git diff` (or a requested commit range) before suggesting edits.

2. Find high-value simplification candidates.
Prioritize:
- Duplicated logic that can be consolidated
- Unnecessary wrappers/abstractions
- Deep branching that can be flattened with guard clauses
- Repeated data transformations that can be centralized
- Dead paths or stale compatibility branches

3. Filter by safety.
Reject changes that alter observable behavior unless the user asks for behavior changes. Keep public interfaces stable by default.

4. Apply minimal simplifications.
Prefer small, reviewable edits over broad rewrites. Keep one clear reason per change.

5. Validate before final output.
Run relevant checks for the touched surface area and report what was run and what was not.

6. Report impact.
Summarize complexity reduction, files touched, and residual risks.

## Output Contract

Use this structure:

1. `Candidates considered`: concise list of simplification opportunities found
2. `Changes applied`: exact files and what was simplified
3. `Behavioral safety`: why behavior is preserved (or what changed if requested)
4. `Validation`: checks run and outcomes
5. `Remaining opportunities`: optional follow-up items not applied

## Guardrails

- Do not refactor for style only; require measurable simplification value.
- Do not mix unrelated cleanup into the same change.
- Do not introduce new abstractions unless they remove net complexity.
- If confidence is low, stop at recommendations and ask before risky edits.
