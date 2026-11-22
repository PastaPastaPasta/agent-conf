---
name: flake-to-fix
description: Use when you observe a flaky test or intermittent CI failure in dashpay/dash, even one unrelated to your change and even mid-task (babysitting a PR, running tests). Don't ignore, rerun or merely note it; hand it to an Opus 5.5 high-effort agent that takes it to a root-cause fix (dedupe check, failure history, introducing commit, local repro under stress/sanitizers, fix, validation and review, milestoned PR from the PastaPastaPasta/dash fork).
---

# Flake to fix

A flake in dashpay/dash is a real bug, in the test or in the code, that happens to show up only some of the time. Don't ignore it, rerun it or just note it. Fix it at the root.

This skill runs on Opus 5.5 (`claude-opus-5-5`) at high effort, preferably in its own T3 thread. If you are any other model or effort, or you're in the middle of other work (babysitting a PR, running tests), don't run it yourself: hand it off with the test name, the failing job's URL and log excerpt, the commit it ran on, and the runner/build config, then go back to your task. Search T3 threads for the test name before launching, so you don't start a second agent on the same flake. After the handoff you may rerun the job to unblock your own PR.

Run as a subagent, stop at the filed PR and return its URL; only the owning thread babysits it.

## 0. Check for duplicate work first

Before anything else, make sure nobody is already on it:

- **T3 threads:** `t3_thread_search` (and `t3_thread_list`) for the test name and the error text. If another thread owns the flake, send it your failure as new evidence and stop.
- **GitHub:** search dashpay/dash issues and PRs, open and recently closed, for the test name and the distinctive error:
  ```bash
  gh search issues --repo dashpay/dash "<test_name>" --include-prs --limit 50
  ```
- **Local:** `git -C ~/workspace/dash worktree list` and `ls ~/.t3/worktrees` for a branch already named after it.

If an open PR already fixes it, add your evidence there (`leaving-pr-comments`) or tell the user, and stop. A merged fix that didn't hold means the flake has a second cause; carry on, and link the earlier fix.

## 1. History

Work out how often it fails, since when, and in what conditions:

- Earlier failures on `develop` and on PRs: `gh run list --repo dashpay/dash --branch develop --workflow <wf> --status failure --limit 100 --json databaseId,headSha,createdAt,url`, then `gh run view <id> --log-failed` and grep for the test. Look at PR runs too; they are most of the volume.
- Existing issues, PRs and review comments that mention it, and any upstream Bitcoin Core issue or fix for the same test (`gh search issues --repo bitcoin/bitcoin "<test_name>"`). If upstream fixed it, backport that fix (`backport` skill) instead of writing a new one.
- What the failures share: the job (TSan, ASan/UBSan, multiprocess, arm, no-wallet…), the failing assertion or timeout, the line, the log lines just before it. Collect at least three failing logs if they exist.

## 2. Trace the intro

Find the commit or PR that made it start failing:

- The first failure date in the history bounds it. `git log --since/--until` on the test file and the code it exercises in that window usually names a handful of candidates.
- `git log -S`/`-G` for the assertion, timeout or log line that fails; `git blame` the lines involved.
- If you can reproduce it (step 3), `git bisect run` with the repro script settles it. A flaky predicate needs enough iterations per step that a pass really means "fixed" (step 3's number), and treat "skip" honestly.

Record the introducing commit/PR. The fix often belongs where that change left an invariant broken, and its author or reviewers are the right people to tag.

## 3. Reproduce locally

You need a reliable local repro before you fix anything; it is also the proof the fix works. Build in your own worktree (`~/.t3/worktrees` or `/work/scratch/<task>`), never in `/tmp`. Run functional tests through `dash-functional-tests`. Escalate until it fails:

1. Run the test alone in a loop (`for i in $(seq 200)`, or `test_runner.py --jobs N` with the test listed N times) and count failures.
2. Add load: run many copies in parallel (`-j` well above the core count; for long stress runs pass `--tmpdirprefix=/work/scratch/<task>` so hundreds of datadirs don't fill the shared `/dev/shm` quota, and delete it afterwards), alongside `stress-ng --cpu 0` or another busy build. agentbox is often at load 50–190 anyway, which helps here. Try `--timeout-factor` both lower and higher to see whether it's a deadline.
3. Use the build CI failed on: TSan, ASan/UBSan (`-DSANITIZERS=thread` or `address,undefined`), debug, the same depends and compiler. Copy the job's flags from `ci/test/00_setup_env_<job>.sh` (for example `00_setup_env_native_tsan.sh`).
4. Reuse CI's seed: functional tests print theirs; pass it back with `--randomseed=`. For unit tests: `test_dash --run_test=<suite>/<case>` from the build dir in a loop, with `RANDOM_CTX_SEED` set to the seed from the CI log if it printed one.
5. Narrow it: add temporary logging or `-debug=` categories, insert a sleep at the suspected race point to force the bad interleaving, attach `gdb -p` to a hung process.

State the repro rate, e.g. "fails 7 of 300 at -j64 under TSan". If after real effort you can't reproduce it, say what you tried and argue the cause from the logs and code; don't guess a fix.

## 4. Fix the root cause

Explain the mechanism in one paragraph: what interleaving or condition produces the failure, and why it shows up only sometimes. Then fix that.

- Not acceptable as the fix: adding or raising sleeps, bumping timeouts, retry loops, `@skip`, marking the test flaky, or loosening an assertion until it passes. These hide the bug; a real race in dashd stays in dashd.
- A longer timeout is right only when you've shown the work genuinely takes that long and nothing is stuck. Say so with numbers.
- In tests, wait for the actual condition (`wait_until` on the state, `sync_blocks`/`sync_mempools`, waiting for the specific log line or RPC result) instead of time. In product code, fix the lock, ordering or lifecycle bug.
- If the test is right and dashd is wrong, the fix goes in dashd, and that is a bug fix with user impact; say so in the PR.
- Keep the diff to the fix. Follow `dash-core-development` conventions.

## 5. Validate and review

- Rerun the step 3 repro on the fixed build, at least as many iterations as it took to fail several times before, and report "0 of N" against the before rate. Run it on the same sanitizer build.
- Run the test's neighbours and anything touching the same code, plus the relevant lints.
- Get a strong-model review of the diff from another model family (Astra high by default; `model-choice` and `limits` pick the reviewer), giving it the mechanism, the repro, the before/after numbers and the diff. Fix what's valid, then run `code-review-validator` if the change is non-trivial.

## 6. PR and babysit

- Commit with a conventional message and push to the PastaPastaPasta/dash fork; never push to dashpay/dash. File with `file-pr` (`--head PastaPastaPasta:<branch>`).
- Set a milestone: the open milestone `develop` is heading for (`gh api repos/dashpay/dash/milestones --jq '.[] | [.number,.title,.due_on] | @tsv'`), or the release branch's milestone if the flake is on a `v*.x` branch. Pass `--milestone` to `gh pr create` or set it right after. If it's unclear which applies, pick the nearest upcoming one and say so. If `gh` lacks the rights to set it, put the intended milestone in the PR body and tell pasta.
- The PR body leads with the failure (test, job, frequency, links to failing runs), then the mechanism, the introducing commit/PR, the fix, and the before/after repro numbers. Link the issue if there is one (`Fixes #…`).
- Then `babysit` it as usual.
