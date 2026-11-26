---
name: dash-quick-merges
description: Find and rank recently opened dashpay/dash PRs to surface small, high-confidence, merge-ready changes. Use when asked to find quick merges, low-hanging fruit, or small bugfix/test PRs in Dash Core.
---

# Dash Quick Merges

Triage and rank recently opened Dash Core pull requests to surface small, low-risk, clearly correct changes ready for immediate review and merge.

## Core Rules

1. **Always Link PRs**: Every PR mention must be a clickable markdown link formatted as `[#<num>](https://github.com/dashpay/dash/pull/<num>)` (or `[<title>](https://github.com/dashpay/dash/pull/<num>)`). Never output bare PR numbers like `#7610` without links.
2. **Sort by Readiness and Size**: Group PRs into clear semantic categories (Ready Tonight / Top Merge Candidates, Fast Follow-ups, Blocked/Drafts, and Large Changes), ordered from smallest change footprint to largest within each group.
3. **Distinguish CI Failures**: Separate genuine code/test failures from known infrastructure quirks or advisory jobs (such as `predict_conflicts` or base cache misses like `linux64_asan-build`).
4. **Distinguish Human ACKs from Bots**: Treat human maintainer approvals (`UdjinM6`, `knst`, `PastaPastaPasta`, `odimm`, etc.) as authoritative, and automated bot reviews (`@thepastaclaw`, `@coderabbitai`) as corroborating evidence.
5. **Traceable Code References**: Include standalone workspace file paths with line references (e.g. `test/functional/feature_protx_version.py:258`) for the top candidates so maintainers can immediately inspect the code.

## Workflow

### 1. Run the Triage Script

Use the bundled triage script (`scripts/triage_recent_prs.py`, next to this file) to fetch open PRs created within the target window (default 30 days):

```bash
python3 scripts/triage_recent_prs.py --days 30
```

To fetch raw structured data for custom filtering or deeper inspection:

```bash
python3 scripts/triage_recent_prs.py --days 30 --json
```

### 2. Inspect Top Candidates

For PRs in the "Top Merge Candidates" and "Fast Follow-up" groups, inspect the diffs to confirm correctness and safety:

```bash
gh pr diff <number> -R dashpay/dash
```

Verify:
- **Scope**: Is the change tightly scoped without accidental refactoring or drive-by formatting?
- **Root Cause**: Does the fix address the root cause rather than masking symptoms?
- **Consensus & Subsystems**: If touching Dash-specific areas (EvoDB, LLMQs, InstantSend, CoinJoin, Masternodes), ensure invariants are strictly preserved.
- **Flake Fixes**: If fixing a test flake, does it wait on explicit states/events rather than adding arbitrary sleeps?

### 3. Present Results

Format output cleanly using standard sections:
- `**Top Merge Candidates**`: Smallest, 100% passing CI or approved, zero blockers, safe to merge immediately.
- `**Fast Follow-up Candidates**`: Small to medium size, clear logic, needing a quick review or rerunning an isolated CI cache job.
- `**Summary of Recent PRs**`: One-line summaries grouping all evaluated PRs with clickable links and line counts.

