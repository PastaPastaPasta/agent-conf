---
name: rank-dash-pr-readiness
description: Build a semantic, evidence-backed HTML report ranking every open dashpay/dash (Dash Core) pull request from closest to merge to furthest away. Use when Codex needs to assess the Dash Core review queue, identify ready-to-merge PRs, recommend what maintainers should review next, or refresh a merge-readiness dashboard using approvals, review conversations, CI, conflicts, rebases, change risk, and recent activity without reducing the result to a deterministic score.
---

# Rank Dash PR Readiness

Produce a point-in-time maintainer brief, not a mechanical leaderboard. Gather facts reproducibly, understand each PR's actual review conversation, make a comparative semantic judgment, and render a self-contained HTML page.

## Requirements

- Cover every open PR in `dashpay/dash`, including drafts, unless the user explicitly narrows scope.
- Rank by distance to merge. Do not compute, expose, or mentally substitute a weighted score.
- Treat two current, substantive human approvals plus healthy CI as strong evidence of merge readiness, then check for contrary evidence.
- Treat positive CodeRabbit, Codex, and ThePastaClaw assessments as meaningful corroboration, not human approvals and never veto-proof.
- Interpret unresolved threads. A technically unresolved thread may be answered, superseded, mistaken, or explicitly accepted; a resolved thread may still expose broader risk.
- Distinguish “closest to merge” from “best use of the next reviewer.” Surface both.
- State uncertainty. Never invent required-check status, reviewer intent, approval currency, or whether a failing check is unrelated.
- Make the report traceable: link blockers and important review evidence back to GitHub.

Read [references/judgment-guide.md](references/judgment-guide.md) before assessing PRs. Read [references/analysis-schema.md](references/analysis-schema.md) before writing the analysis JSON.

## Workflow

### 1. Collect a complete snapshot

Require authenticated `gh` access, then run:

```bash
python3 scripts/collect_pr_evidence.py \
  --repo dashpay/dash \
  --output /absolute/path/dash-pr-evidence.json
```

Use an absolute output path outside the skill directory. The collector retrieves PR metadata, body, commits, reviews, issue comments, review threads, and current check rollups. It fails on incomplete collection by default. Do not proceed from a partial snapshot merely to produce a report.

Record the collection timestamp in the final handoff. PR state can change while the report is being produced.

### 2. Triage facts, then read every PR

Use `jq` or a small analysis program to make compact factual views, but inspect every PR's body, reviews, unresolved threads, recent comments, current checks, update timing, and change size. Do not classify a PR from the list-level metadata alone.

For each PR:

1. Establish its purpose, scope, risk, and whether it is a backport, draft, stacked PR, or dependency.
2. Reconstruct the review timeline. Determine what feedback remains substantively open and whether later commits invalidate earlier approvals.
3. Interpret CI failures by name and timing. Separate genuine patch failures, infrastructure/flakes, expected pending work, cancellation, and rebase-only failures when evidence supports that distinction.
4. Inspect the patch with `gh pr diff -R dashpay/dash <number>` when risk, reviewer disagreement, vague feedback, stale approvals, or the claimed fix cannot be understood from conversation alone. For large PRs, inspect the file list and decisive hunks rather than flooding context.
5. Write a short semantic case: why it occupies this position, what evidence could move it, and the single best next action.

Batching is allowed for context management, but never infer uninspected PRs from neighboring titles or status fields.

### 3. Rank comparatively

Assign qualitative stages from the judgment guide, then compare PRs within and across stages. Ordering is a judgment about remaining work and uncertainty, not arithmetic.

Before finalizing, challenge the boundary cases:

- Could a “ready” PR still have a substantive objection, stale approval, hidden dependency, or required rebase?
- Is an unresolved bot thread actually conceded or superseded?
- Is a red check actionable, flaky, obsolete, or merely still running?
- Does a tiny unreviewed change belong above a deeply reviewed high-risk change?
- Does the report explain why adjacent PRs are ordered as they are?

Use precise language such as “appears ready,” “awaiting one current human ACK,” or “blocked on author changes.” Avoid pretending GitHub evidence proves maintainers will merge.

### 4. Write structured analysis

Create analysis JSON matching [references/analysis-schema.md](references/analysis-schema.md). Include every evidence PR exactly once and give unique consecutive ranks. Keep factual counts out of prose when the renderer already displays them; use prose for meaning.

Mark `review_priority` independently:

- `merge-now`: maintainer merge decision is the next useful action.
- `review-now`: a focused human review/ACK is likely to unlock the PR.
- `author-action`: code, responses, rebase, or clarification is needed first.
- `wait`: CI, dependency, or external event is the immediate gate.
- `low`: draft, stale, exploratory, or otherwise poor use of review time now.

### 5. Render and verify

Run:

```bash
python3 scripts/render_report.py \
  --evidence /absolute/path/dash-pr-evidence.json \
  --analysis /absolute/path/dash-pr-analysis.json \
  --output /absolute/path/dash-pr-readiness.html
```

The renderer validates coverage and ordering, escapes GitHub-sourced text, and creates a dependency-free searchable/filterable HTML report. Open the page in the shared preview/browser, inspect the top, middle, and bottom of the ranking, test search and filters, and correct unclear or broken output before delivery.

## Quality bar

Reject the report and revisit the analysis if any of these are true:

- A numeric formula or checklist determines rank.
- Any open PR is absent or duplicated.
- “Unresolved” is treated as synonymous with “unaddressed.”
- Bot approvals are counted as human approvals.
- A stale human approval is presented as current without qualification.
- CI is summarized as red/green without interpreting the relevant failures.
- The next-review recommendation merely repeats the top-ranked PRs.
- Assessments are interchangeable boilerplate rather than PR-specific reasoning.
- The HTML does not show its snapshot time, evidence, confidence, and next action.

