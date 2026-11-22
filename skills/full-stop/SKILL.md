---
name: full-stop
description: Trigger this if the user says 'full stop', even as a closing "Full stop." that reads like emphasis. Same as full-send, but stops with the PR ready for the user to merge.
---

# Full Stop

Do the same work as `full-send`, but stop with the PR ready for the user to
merge. Never merge it.

Read [full-send](../full-send/SKILL.md) and follow its workflow, testing
permission, proof rules, review and babysitting steps. An explicit "full stop"
request authorizes that work without a separate "full send". Its merge
permission does not apply. The overrides below take precedence.

## No merging

You may commit, push, rebase, fix conflicts, and use `--force-with-lease` on
this task's branch. Never merge, enable auto-merge, enter a merge queue, push to
the base branch, bypass branch protection, or delegate any of those.

Before work begins, disable existing auto-merge and remove the PR from any merge
queue; check again before each push. Report these changes. If you cannot
prevent an automatic merge, report the blocker before going on.

## Stop at the gate

Use full-send's merge gate as the readiness check. Replace its merge and final
report steps with a handoff. Proof and review must cover the final diff;
recheck behavior changes and real conflict fixes before handoff.

Fetch the base branch and check the live PR's head, base, checks, reviews, and
mergeability. Confirm it is open, not a draft, and not set to merge without the
user. If someone else merged it, report that instead.

- **Ready to merge:** the gate passes. Leave the PR open and unmerged.
- **Waiting for required approval:** only human approval or ACKs remain.
  Confirm that is the actual blocker.
- **Blocked:** say what prevents readiness, what you tried, and what is needed.
  Follow full-send's rules for asking the user.

Call `unwatch_pull_request` before the handoff or a question. Report the PR
link, final head, verdict, proof, reviewer outcome, and remaining risks. State
that the PR is still open and unmerged.
