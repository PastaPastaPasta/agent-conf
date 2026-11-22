# Analysis JSON schema

Write UTF-8 JSON with this shape. Fields marked “optional” may be omitted; all others are required.

```json
{
  "repository": "dashpay/dash",
  "evidence_generated_at": "2026-08-06T20:00:00Z",
  "analysis_generated_at": "2026-08-06T20:20:00Z",
  "methodology_note": "One short statement explaining that ordering is semantic and point-in-time.",
  "executive_summary": "A concise maintainer-level reading of the queue.",
  "pull_requests": [
    {
      "number": 1234,
      "rank": 1,
      "stage": "ready-to-merge",
      "confidence": "high",
      "review_priority": "merge-now",
      "assessment": "PR-specific explanation of where this sits in the process.",
      "why_here": [
        "Comparative reason supported by current evidence",
        "Another material reason"
      ],
      "next_action": "The single best concrete action and intended actor.",
      "human_approvals": [
        {
          "login": "reviewer",
          "currency": "current",
          "scope": "full",
          "summary": "ACK covers the current substantive diff.",
          "url": "https://github.com/dashpay/dash/pull/1234#pullrequestreview-..."
        }
      ],
      "automation_signals": [
        {
          "source": "CodeRabbit",
          "disposition": "positive",
          "summary": "No actionable findings after the latest revision.",
          "url": "https://github.com/dashpay/dash/pull/1234#issuecomment-..."
        }
      ],
      "blockers": [
        {
          "kind": "ci",
          "severity": "blocking",
          "summary": "Current functional test fails for a patch-related reason.",
          "url": "https://github.com/dashpay/dash/actions/runs/..."
        }
      ],
      "caveats": [
        "Optional uncertainty or non-blocking concern"
      ]
    }
  ]
}
```

## Allowed values

- `stage`: `ready-to-merge`, `final-review`, `review-active`, `needs-author`, `blocked`, `draft-or-stale`
- `confidence`: `high`, `medium`, `low`
- `review_priority`: `merge-now`, `review-now`, `author-action`, `wait`, `low`
- `human_approvals[].currency`: `current`, `probably-current`, `stale`, `unclear`
- `human_approvals[].scope`: `full`, `test-only`, `concept-only`, `partial`, `unclear`
- `automation_signals[].disposition`: `positive`, `negative`, `mixed`, `superseded`
- `blockers[].severity`: `blocking`, `likely-blocking`, `caveat`

`url` is optional in nested evidence objects. Use only an actual supporting GitHub URL; never fabricate an anchor.

## Integrity rules

- Include every PR number from the evidence snapshot exactly once.
- Use unique consecutive integer ranks beginning at 1. Array order should match rank.
- Do not put automated reviewers in `human_approvals`.
- Include stale/partial approvals only when their limits help explain the ranking.
- Keep `blockers` empty when no blocker is known. Do not manufacture a blocker to justify ordering.
- Make `assessment`, `why_here`, and `next_action` specific enough that swapping them onto another PR would sound wrong.
- Use `caveats` for uncertainty; use `blockers` for evidence that actually impedes merge.
