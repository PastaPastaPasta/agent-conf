---
name: babysit
description: Monitor one or more GitHub PRs until they merge — wait via watch_pull_request, triage bot and reviewer feedback, fix or rerun CI failures, keep branches current, and check the merge gate. Use when asked to watch, monitor, babysit, or shepherd a PR, keep an eye on CI, or handle PR review comments.
---

# PR Babysitting

Keep PRs healthy with minimal token spend until they merge or the user stops
you. You are a caretaker, not a rewriter: react to news, fix what's real, push
back on what isn't, and stay quiet in between.

## Waiting: `watch_pull_request`

T3 Code's `watch_pull_request` is the only waiter. It wakes the thread when a
check fails, the required checks pass (and once more when optional checks
settle), a comment or review arrives, no checks report for 15 minutes, or the
branch conflicts; it ends the watch on merge or close. **Never write your own
watcher**: no `sleep` or `gh pr checks` loops, Monitor scripts, ScheduleWakeup,
cron or launchd jobs, and no `pr_wait.py wait` loop.

1. **Start:** handle what already exists first, because the watch reports only
   later activity. Run `scripts/pr_wait.py once <PR>` (next to this file) for
   an unacked digest of comments, reviews and CI, handle it, and
   `pr_wait.py ack --ack <ack_token> <PR>` so later reads don't repeat it. Then
   call `watch_pull_request` and end the turn.
2. **On a wake:** the message lists what changed. Handle it, then end the turn.
   The watch stays on; do not call `watch_pull_request` again. If nothing needs
   action, end the turn without a message. Never post or say "still waiting".
3. **A wake is news, not a merge decision.** Before calling a PR ready or
   merging, run the merge check below.
4. **Keep watching through "ready".** A ready PR still gets ACKs, late reviews
   and base changes; babysitting lasts until merge or close. Unwatch only when
   you stop for good: you need pasta's input, pasta opted out, or a skill hands
   back at ready (`full-stop`). A watched thread stays in Working and out of
   pasta's inbox, so call `unwatch_pull_request` before that handback.
5. **"Stopped watching, could not read it"** means 8 reads in a row failed for
   reasons other than rate limits (auth, 404, network); rate-limited reads just
   pause the watch. Check the PR yourself, run `pr_wait.py once` to catch the
   gap, then watch again. Never re-watch in a tight loop.
6. **"Stopped watching after 10 comment-only updates"** means bots are
   talking in a loop. Find out why before you watch again.

Two checks at the start:

- **dashpay/platform PRs from pasta's fork:** if `gh pr view <N> --json headRepositoryOwner`
  is `PastaPastaPasta`, its Rust/Swift CI never runs, so a green check means
  nothing. Don't babysit it. Replace it from a branch on dashpay/platform
  (`file-pr`). Contributors' fork PRs are theirs; leave them as they are.
- **Drafts:** thepastaclaw posts a deferral comment
  (`<!-- thepastaclaw-review-deferred v1 -->`) and won't review the draft until
  asked. When it appears, edit that comment to tick
  `- [x] **Request normal review**` with
  `gh api -X PATCH repos/<R>/issues/comments/<id> -f body=…`. Never tick
  priority review unless asked.

Only the thread that owns the PR watches it. Delegated children never call
`watch_pull_request`; give them fix work and let the parent watch.

### What the T3 watch misses

- **pasta's own comments.** It skips every comment from the logged-in GitHub
  user, so a comment pasta types on the PR does not wake you. Read human
  comments whenever you look at the PR anyway, and ask pasta to say it in the
  thread when it matters.
- **Cancelled checks are reported as failed.** Cancelled is usually a
  superseded run or a deliberate trim (`~/.claude/ci-trim`), not a failure.
- **Gate edits are not settled.** thepastaclaw edits one gate comment in place
  (`<!-- thepastaclaw-gate v1 -->`); a wake can land on an in-progress edit.
  Trust the gate only when its line names the current head commit and says the
  review is complete.
- **Pushes by someone else** don't wake you on their own; you hear about the
  new head when its checks finish.
- **Self-initiated merges or closes don't wake you.** T3 wakes once on an
  external merge or close, not on one you ran via CLI. If you merge, queue a
  merge, or enable auto-merge yourself, write your report first or confirm the
  merge in the same turn.
- **The thread settling or being a subagent** ends the watch silently.
- **BEHIND, unresolved threads, and base changes** are not reported. The merge
  check covers them.

## Scope

Watch exactly the PRs the user named, or the ones you opened in this task line.
Never adopt other PRs because their state files exist or their watches died;
list them for the user instead. If another thread already watches a PR, don't
add a second.

## Handling events

- **Bot comments.** Bots are often wrong. **Investigate before
  implementing**: read the code, trace the path, check whether it's already
  handled. Then decide:
  - **Valid:** fix it, as narrowly as the finding.
  - **False positive:** leave the code alone; reply with a one- or two-sentence
    reason (`leaving-pr-comments`) and resolve the thread.
  - **Partial:** the observation is real but the suggested fix is wrong;
    implement the right fix and say so.

  CodeRabbit is advisory: treat its findings like any other, but never wait or
  hold a merge for it.
- **Keep the PR at its size.** The description and commits define the scope.
  Review loops grow a PR one cheap-looking fix at a time. Fix real bugs in the
  intended case. Decline the rest with a written reason and list them as
  follow-ups: refactors, style rewrites, tests for untouched code, guards for
  edge cases that don't matter, extra compatibility, small perf costs. Prefer the
  fix that deletes or narrows code.
- **Comments from a human, including pasta:** surface them rather than acting
  alone, unless the fix is trivial and unambiguous.
- **Failed checks:** look cheaply first: `gh run view <run-id> --log-failed 2>/dev/null | tail -80`.
  - **Caused by the PR:** fix, commit, push.
  - **Clear flake** (unrelated to the diff, infra, runner death): rerun that job
    once with `gh run rerun <run-id> --failed`. A second identical failure is
    evidence, not noise: flag it.
  - **Cancelled:** find out why before rerunning anything.
  - **`action_required`:** a fork PR's workflows need maintainer approval.
    Report it.
  - **Unclear:** check whether the test touches the diff and whether it fails on
    base; if still ambiguous, describe it to the user.
  - Never push empty commits to retrigger CI, and never rerun every job when one
    will do.
- **No checks reported:** workflows didn't trigger or need approval. Report it;
  it is not green.
- **Conflict:** rebase only if the PR is yours to maintain (`rebase-branch`);
  otherwise report it.
- **Someone else pushed:** fetch and recheck queued work against the new head.
- **An overlapping PR makes this one obsolete:** stop, report it, and ask
  before closing unless closing was authorized.

Only act on checks and comments newer than the latest push.

## Merge check

Run this before calling a PR ready, and again right before merging:

```bash
gh pr view <N> --repo <R> --json state,isDraft,headRefOid,baseRefName,mergeStateStatus,reviewDecision,latestReviews
gh pr checks <N> --repo <R> --required      # all checks if the repo has no required ones
gh api graphql -f o=<owner> -f r=<repo> -F n=<N> -f query='
  query($o:String!,$r:String!,$n:Int!){repository(owner:$o,name:$r){pullRequest(number:$n){
    reviewThreads(first:100){nodes{isResolved path comments(first:1){nodes{author{login} url}}}}}}}' \
  --jq '[.data.repository.pullRequest.reviewThreads.nodes[] | select(.isResolved | not)]'
```

Ready means all of:

- `mergeStateStatus` is `CLEAN`, on the head you proved. `UNSTABLE` is
  acceptable only when every check that isn't green is non-required and
  advisory (CodeRabbit, an optional job you've looked at). `BEHIND`, `DIRTY`,
  `BLOCKED` and `UNKNOWN` are not ready.
- Required checks are green on that head (`pending: 0`, `failed: 0`).
- No unresolved review thread, and no entry in `latestReviews` is
  `CHANGES_REQUESTED` (`reviewDecision` is null when reviews aren't required).
- The thepastaclaw gate (where the repo has one) has finished on this head with
  no blocking findings left unanswered.
- If the PR changes anything a user sees, its body has the UI proof that
  `file-pr` requires (a `## UI proof` section) and still shows this head's UI.
  Recapture if a later commit changed what users see.
- Base commits that landed after the last green run don't touch this PR's
  files: `git fetch`, then compare `git diff --name-only $(git merge-base <head> origin/<base>) origin/<base>`
  with `gh pr diff <N> --name-only`. If they overlap, rebase, push, and wait for
  green again.

When the GraphQL limit is spent (`gh api rate_limit --jq .resources.graphql`),
REST still works: `gh api repos/<o>/<r>/pulls/<n>` for the PR and
`gh api repos/<o>/<r>/commits/<sha>/check-runs` for checks.

## Merging (only when the user asked, or `full-send` allows it)

Merge with `gh pr merge <N> --match-head-commit <sha>` so a late push can't slip
in, using the repo's merge method; pass `--delete-branch` only if asked. Never
`--admin`. When several green PRs touch related code, merge one at a time and
let base CI confirm before the next.

**Pin before merging if you have more to do.** Unless this thread is pinned,
it settles as soon as a linked PR merges, and a settled thread never wakes
again. If you need to keep working after the merge (more PRs in a series, a
tag, a deploy, a follow-up fix), pin the thread first with `t3_thread_organize`
(`action: "pin"`), then merge. Otherwise merge, and this thread ends. When the
remaining work is done, `unpin` and `settle` it.

## `pr_wait.py`

`scripts/pr_wait.py` stays for one-shot reads, not waiting:

```
pr_wait.py once PR...                 # everything not yet acked, as JSON
pr_wait.py ack --ack TOKEN PR...      # ack a batch you handled
pr_wait.py gc [--yes]                 # list (delete) state for merged/closed PRs
```

Use `once` at the start, after a watch gap, and for multi-PR heartbeat sweeps,
and ack each batch you handle. It settles thepastaclaw gate edits and skips our
own replies by their attribution footer. If its output has
`state_dir_fallback`, a sandbox is hiding the shared state dir; rerun with the
sandbox disabled. If it lacks something, fix it and its tests
(`scripts/test_pr_wait.py`).

## Commits and signing

Commits sign automatically with the dedicated agent SSH key; never pass
`--no-gpg-sign` or override signing config. If signing fails, stop and tell
pasta rather than committing unsigned.

## Reporting

When you act, give a compact digest: findings triaged (valid or dismissed, and
why), fixes pushed, CI state, anything queued. When blocked on something only
pasta can resolve (contentious human feedback, a repeated CI failure, a scope
call), unwatch, then say exactly what you need, with the question tool if the
user isn't watching. After a batch of PRs finishes, run `pr_wait.py gc`, then
`gc --yes`.
