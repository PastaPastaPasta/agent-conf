---
name: full-send
description: Take a change end-to-end to a merged PR unattended (prove, review, file, babysit, and merge). Use when the user says 'full send'.
---

# Full Send

If the user said "full send", they are not watching this thread and want the
work done end to end. Your updates and final message go unread until long
after you stop. You own the work from its current state to a merged PR.

If the user did not clearly ask for "full send", do not assume this autonomy.
If they did, everything below applies.

## What the user grants

- Merge the PR once the merge gate passes, **subject to "Where merging is
  allowed"**.
- Force-push this task's own PR branch with `--force-with-lease` after a rebase
  (follow `rebase-branch`, including its HEAD and tree checks before the push).
- Use the test methods Proof needs without asking first (see "Testing").

### Where merging is allowed

- **Repos outside the `dashpay` org** (`PastaPastaPasta/*`, `thepastaclaw/*`,
  personal projects): merge when the gate passes.
- **`dashpay/*`**: these merge on other maintainers' ACKs. Act as `full-stop`
  (stop with the PR ready, never merge, never enable auto-merge) unless the
  user's request names that repo and says to merge there.
- Never merge into a production branch the repo keeps apart from its working
  branch (yappr `master`); the PR targets the working branch (`staging`).

## Testing

A "full send" request is permission for the test methods Proof needs. It
replaces project rules that say to ask first or to leave testing to the user,
for this task only. Rules about *how* to test still apply: use the commands,
fixtures and checks the repo names.

Never put GUI on pasta's laptop screen (no `open`, local Simulator windows,
XCUITest UI, or windows that steal focus). For iOS Simulator and Android
Emulator proof, use T3 Code's device tools (`device_list` → `device_open` →
`agent-device` + `device_screenshot`, preferring a remote device host like the
Mac Studio when available) — never drive simulators over raw SSH or `simctl`
unless explicitly asked. For web/desktop GUI proof, use T3's `preview_*` tools,
headless browsers, or Xvfb. `run-ios-simulator` and `capture-visual-evidence`
cover the details.

This permission covers testing only. It does not cover the items under
"Asking the user", and it does not bypass a harness approval prompt.

## Steps

1. **Finish the change.** The smallest change that meets the goal. Fix the
   case that happened, not every case that could. Branch first if you are on
   the base branch. Use the repo's real working branch as the base (`staging`
   for yappr, the current `v*-dev` for Platform, `develop` for Dash Core), not
   just GitHub's default.
2. **Prove it.** Proof for every change in the diff. See "Proof".
3. **Review it.** Follow the Quality Gates in your global instructions: `code-review-validator`
   for non-trivial changes, plus `code-simplifier` after significant new code.
   Use `sol-loop` only if the user asked for it, and `council` if the user
   asked or `model-choice` requires it (consensus, security or protocol design).
4. **File the PR** with `file-pr`. Rebase onto the latest base first. Add one
   short line to the description saying how you proved the change. For
   dashpay/platform, push to dashpay/platform, never a fork. If an existing
   platform PR's head is on PastaPastaPasta/platform, replace that PR rather
   than babysitting it.
5. **Babysit it** with `babysit`. Fix real findings and CI failures. Get proof
   for each fix before pushing it.
6. **Merge** when the merge gate passes and merging is allowed here. If any
   work remains after this merge (another PR in the series, a tag, a deploy),
   pin the thread first: an unpinned thread settles on merge and never wakes
   (see `babysit`, "Merging").
7. **Report** in the final message: PR link, merge commit (or why it stopped
   at ready), proof, and every decision you made for the user.

Stay active from step 1 to step 7. Ending the turn while checks or bots are
pending stops the work unless a watcher wakes you: call `watch_pull_request`
(the `babysit` way) before ending any waiting turn. Call
`unwatch_pull_request` before you stop short of a merge. T3 wakes once on an
external merge or close, not on one you ran via CLI, so when you merge, queue a
merge, or enable auto-merge yourself, write the report first or confirm the
merge in the same turn.

## Proof

Proof is evidence you observed in this session: command output, a
reproduction, a screenshot. Use the most direct kind the change allows:

- Reproduce the original failure, apply the fix, watch the same reproduction
  pass.
- Run what the repo's CI runs for the touched area (build, lint, tests). For
  Dash Core and Platform, follow the build rules in your global instructions,
  if any, and the repo's own AGENTS.md or CLAUDE.md.
- Add one focused test that fails without the fix, when the behavior has no
  test and the repo has a test setup.
- For UI and runtime behavior, run it and look. Green mocked tests do not prove
  the user experience works. A PR that changes anything a user sees needs
  the UI proof that `file-pr` requires.

If you cannot find a way to prove a change, you do not have full confidence.
Ask the user.

## Merge gate

All of these on the latest head:

- Your proof covers every change in the diff.
- `babysit`'s merge check passes: GitHub reports `mergeStateStatus: CLEAN`,
  required checks are green, nothing is BEHIND or conflicting.
- Review bots have finished on this head (thepastaclaw/reviewsys gate verdict,
  Codex, CodeRabbit), and every finding is fixed or answered with a written
  reason.
- No human review still requests changes, and no human comment is unanswered.

Merge with the method the repo uses (look at recent merged PRs), with
`gh pr merge <N> --match-head-commit <sha>`. If the repo uses a merge queue or
auto-merge, see the note under Steps. Never use `--admin` or any
other branch-protection bypass. On repos where merging is allowed, an automated
"needs human review" note does not block you when your proof is strong.

## Asking the user

A question in a normal message goes unseen and the thread looks finished. Ask
with your harness's question tool (`AskUserQuestion`, `request_user_input`,
`ask_question`, etc.) so the thread shows it is waiting, and call
`unwatch_pull_request` first. Put all context in the question: PR link, what
blocks you, and the options with your recommendation first.

Exception: on threads started by a Grok Bot (e.g., `Report to: Grok Bot …` or
`— from Grok Bot …`), do **not** call the question tool — call
`unwatch_pull_request` first, notify the spawning bot with
`t3-notify send "<concise question/blocker>"`, write the full context in your
normal reply, and end the turn without settling so the bot can respond.

Ask only when you cannot go on alone:

- You cannot prove the change.
- The merge gate cannot pass and you cannot fix that yourself.
- The next step is outside the grant: deleting data, touching production or
  deployed services, changing things outside the repo, closing a PR, or
  force-pushing any branch but this task's own.
- Commit signing fails (stop and tell the user).
- The goal is ambiguous in a way that changes the result.
- Another PR makes this one obsolete.

Decide everything else with sensible defaults and list those decisions in the
report.

If no question tool exists or it returns no answer, take the safe path: leave
the PR open and unmerged, and start the final message with the question.
