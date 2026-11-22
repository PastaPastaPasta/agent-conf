---
name: pr-review
description: Run a thorough, CodeRabbit-style PR review for one pull request by number, including file-level risk analysis, line-level findings, CI/check health, and review-thread context. Use on commands like `/pr-review 123`.
---

# PR Review

A focused review automation for one GitHub pull request.

## What this skill does

This skill produces a thorough PR packet with:
- PR metadata and ownership context
- commit/CI/check health
- diff-level evidence (`+/-` style snippets)
- line-level risk findings with severity (`high`, `medium`, `low`)
- early risk signals and a final review signal (`APPROVED`, `APPROVED WITH SUGGESTIONS`, `REQUIRES CHANGES`)
- review comments and review summaries

## Invocation

Primary pattern:

```bash
python3 ~/.codex/skills/pr-review/scripts/review_pr.py <PR_NUMBER>
```

(Cursor: `~/.cursor/skills/...`.)

Optional flags:

- `--repo owner/repo` (when running outside the target repo)
- `--local-checkout` (attempt local checkout for manual follow-up)
- `--max-comments N`
- `--json-only` (skip recommendations/checklist section)

## Review workflow

1. Resolve repository context.
2. Pull PR metadata, files, inline comments, issue comments, and check runs.
3. Run heuristic diff analysis on added lines and emit severity-ranked findings.
4. Rank risk signals first, then map unresolved discussion points.
5. Emit final recommendation signal.

## Severity rubric

- `high`: definite risk patterns (dynamic execution, deserialization/exec-style calls, major merge risk).
- `medium`: likely risk patterns (placeholder comments, debug output, broad error handling, possible credentials).
- `low`: weaker risk patterns that still need reviewer attention.

## Output contract

1. PR metadata
2. File risk map
3. Detailed findings (file + line + rationale)
4. Files/diff snippets
5. Discussion summary
6. CI/check state and blockers
7. Early-risk signals
8. Suggested review checkpoints + review outcome

## Guardrails

- Requires authenticated GitHub CLI (`gh auth login`).
- Do not infer conclusions beyond collected evidence.
- Treat heuristic findings as review prompts, not certainties.
- If checks are failing or merge state is blocked/dirty, escalate to `REQUIRES CHANGES` unless user scope explicitly permits.
