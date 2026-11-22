# Semantic judgment guide

Use this guide to reason consistently without turning the report into a score. Evidence changes meaning in context; there is no fixed point value, threshold, or tie-break formula.

## Core question

Ask: **What substantive work, validation, coordination, and uncertainty remain before a responsible Dash Core maintainer could merge this PR?**

Rank the answer comparatively across the full queue. A PR with fewer visible blockers can still rank lower when its risk is poorly understood, approvals are stale, or its relationship to other work is unclear.

## Evidence and interpretation

### Human review

- Count a human approval only when GitHub identifies a human reviewer and the review is substantively an approval/ACK.
- Treat two or more current substantive human approvals as strong readiness evidence, especially when they cover the latest meaningful code.
- Check whether commits landed after an approval. Later changes do not automatically erase it, but assess whether they are mechanical, requested and verified, or materially outside the reviewed state.
- Read approval bodies. `ACK`, `utACK`, `re-ACK`, and scoped approvals carry different implications; explain material scope limits.
- A requested-changes review remains important until later discussion or code clearly resolves it, even if GitHub's aggregate decision is ambiguous.
- Review requests are not negative by themselves. They can indicate the missing final reviewer.

### Automated and agent review

Treat CodeRabbit, Codex, and ThePastaClaw as distinct corroborating reviewers. Their positive conclusions increase confidence that a PR is mature; their findings can expose real blockers. Do not count them toward the two-human-approval signal.

Read the conversation, not merely thread state. For example, an unresolved CodeRabbit thread followed by CodeRabbit explicitly conceding the concern is not an unaddressed blocker. Conversely, an author reply that only disagrees without resolving the technical concern may remain a blocker.

Recognize automation by actor identity and by unmistakable signed/body text; identities can change. Separate GitHub Actions boilerplate from semantic agent review.

### CI and merge state

- Healthy current CI strongly supports readiness. Pending required-looking suites usually mean “wait,” not “failed.”
- Interpret each current failure. A patch-caused test failure is a blocker; a documented infrastructure failure or credible flake may be a caveat, but never wave it away without evidence.
- Canceled, skipped, neutral, and superseded reruns are not ordinary failures. Inspect timestamps and duplicate check names.
- `BEHIND`, merge-conflict predictions, and fast-forward checks can mean a rebase is required. Confirm using current merge state and relevant check/comment evidence.
- GitHub's `mergeStateStatus` is a clue, not a full explanation. Branch protection can say `BLOCKED` merely because approvals are missing.
- Empty CI on a new PR means “not yet validated,” not green.

### Conversation and unresolved work

For every unresolved thread, identify its semantic state:

- **Open blocker:** a correctness, security, consensus, test, or scope problem still stands.
- **Open question:** needs clarification before confident review.
- **Addressed but unresolved:** code/reply appears sufficient; thread bookkeeping remains.
- **Conceded/superseded:** reviewer withdrew it or later changes made it obsolete.
- **Nit/deferred:** acknowledged non-blocking cleanup or explicit follow-up.

General comments can contain blockers that are not review threads. Check recent maintainer comments, dependency references, test reports, and requests to rebase.

### Change risk and maturity

- Evaluate risk by subsystem and behavior, not lines changed alone. Consensus, LLMQ/BLS, ChainLocks, InstantSend, special transactions, EvoDB/Platform, networking serialization, wallet security, and release/build paths require stronger confidence.
- A clean upstream backport can be mature when upstream provenance and Dash adaptations are well reviewed; a large conflict-heavy backport may require detailed drift review.
- A tiny PR with no review is easy to review, not necessarily close to merge.
- Draft status, explicit work-in-progress language, missing prerequisites, stacked dependencies, and dormant author activity all increase remaining coordination.
- Fresh activity can mean momentum or churn. Determine which.

## Suggested stages

Use these as descriptive buckets, then order semantically within them:

1. `ready-to-merge` — evidence indicates only a maintainer merge decision remains.
2. `final-review` — mature and validated; one focused ACK, re-ACK, or final check is the likely last gate.
3. `review-active` — useful review is underway or the PR is reviewable, but meaningful review work remains.
4. `needs-author` — actionable code, response, clarification, or rebase work should precede more review.
5. `blocked` — dependency, conflict, policy, design decision, or persistent validation failure prevents progress.
6. `draft-or-stale` — explicitly unfinished, dormant without a credible path, superseded-looking, or not presently worth scarce reviewer attention.

Do not assume every PR in an earlier-numbered stage outranks every later-numbered stage without examining nuance. If you depart from the usual ordering, explain why.

## “What to review next” lens

Favor PRs where one bounded human action is likely to unlock progress:

- CI is healthy or credibly understood.
- The author has addressed prior feedback.
- The remaining review scope is clear.
- Another approval/re-ACK is genuinely the missing gate.
- The change is important enough to justify reviewer time.

Do not recommend spending review time on PRs awaiting author code, a rebase, known failing tests, or an external dependency. A ready-to-merge PR belongs in `merge-now`, not automatically `review-now`.

## Confidence

- `high`: evidence is current, coherent, and specific.
- `medium`: the likely state is clear but approval currency, CI interpretation, or reviewer intent has a material ambiguity.
- `low`: evidence is incomplete/contradictory or decisive technical context could not be established.

Low confidence is not automatically low readiness. Explain what would resolve the uncertainty.

