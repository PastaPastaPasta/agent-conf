---
name: rebase-branch
description: Rebase a branch or PR onto a newer base (develop, main, staging, another PR) — resolve conflicts from the actual blobs, prove nothing was lost with range-diff, and force-push to the ref the PR really reads. Use whenever asked to rebase, restack, update, or "bring a PR up to date with" a base branch, including "rebase this PR and force push". Also applies to squashing or amending published commits, since the force-push traps are the same.
---

# Rebasing a branch

A rebase is done when two things are true: **`git range-diff` shows every commit preserved or explainably changed**, and **the force-push landed on the ref the PR actually reads**. Anything less is an unfinished rebase, no matter how clean `git log` looks and no matter whether it built.

The three sections below are the ones that go wrong in practice, drawn from real transcripts.

---

## 1. Capture ground truth before you start

After the rebase these values are unrecoverable without reflog archaeology, and without them you cannot verify anything.

```bash
gh pr view <N> --json number,url,state,headRefName,baseRefName,headRepositoryOwner,headRepository
git worktree list && git remote -v
```

Then, in the worktree holding the branch:

```bash
git status --short          # MUST be empty — see below
BASE=<base-remote>/<base-branch>   # e.g. upstream/develop; see below
git fetch <base-remote> <base-branch>
git fetch <pr-remote> <branch>

PRE=$(git rev-parse HEAD)                # tip before the rebase
OLDBASE=$(git merge-base HEAD "$BASE")   # base the commits were written against
git log --oneline "$OLDBASE"..HEAD                 # commits you must still have afterwards
```

Write `PRE`, `OLDBASE`, and that commit list down. `ORIG_HEAD` is not a substitute — later git operations overwrite it. For more than ~2 commits, or any published branch, also drop a backup ref that survives everything:

```bash
git branch "backup/prerebase-$(git rev-parse --short "$PRE")" "$PRE"
```

**Refuse to rebase a dirty tree.** If `git status --short` is non-empty, land or stash the work deliberately and say so. `--autostash` mixes uncommitted changes into conflict resolution and makes range-diff verification meaningless — don't reach for it to get past a dirty tree.

**Confirm the base you were actually asked for.** The base branch is the PR's `baseRefName` unless the user named another, and the base remote is the one whose URL is the PR's base repository (`git remote -v`; remote names differ between machines and repos). For Dash Core that is usually `upstream/develop`. When the base is another PR, use that PR's head remote and branch. "Latest" means *after a fresh fetch*: not the stale tracking ref you already had, and not a fork's mirror of the branch, which may lag. Quote `git log -1 --format='%h %s' "$BASE"` in your report.

Then:

```bash
git rebase "$BASE"
```

(`git status` reporting "interactive rebase in progress" during a plain rebase is normal — modern git implements every rebase on the merge backend and labels it that way. It does not mean you ran `-i`.)

---

## 2. Resolve conflicts from the actual blobs, not from memory

### Find out what you are resolving

```bash
git diff --name-only --diff-filter=U          # which files conflict
git log -1 --format='%h %s' REBASE_HEAD       # which commit is being replayed right now
git show REBASE_HEAD -- <file>                # what that commit was trying to do
```

`REBASE_HEAD` is the commit currently being applied. Its diff is the *intent* you must preserve. Read it before editing anything.

### Get all three sides

Plain `git diff` during a conflict prints a combined `diff --cc`, which is easy to misread. Use the index stages:

```bash
git show :1:<file>    # merge base
git show :2:<file>    # "ours" = the new base you are rebasing onto
git show :3:<file>    # "theirs" = the commit being replayed
```

During a **rebase** ours/theirs are swapped relative to a merge: *ours* is upstream, *theirs* is your commit. Getting this backwards is how upstream work gets silently reverted.

### The resolution rule

The correct resolution is **the replayed commit's intent, re-applied to the new base** — not "take ours", not "take theirs", and never a block of code retyped from memory.

For each hunk ask:

- What did `REBASE_HEAD` change here, and why? Read its full diff, and the PR description if the intent isn't local.
- What did the new base change here independently?
- Does the commit's change still make sense against the new base, or did upstream already do it / make it unnecessary?

Then edit the file in place with a real file-editing tool (`apply_patch`, `Edit`, or a targeted `sed`).

**Do not resolve conflicts with a script that string-matches `<<<<<<< HEAD` / `>>>>>>> <sha>` and splices in hand-typed replacement text.** Observed failure (Codex, gemini-3.6-flash-high, 2026-08-20, dashpay/dash#7570): a `python3 -c` one-liner searched for the exact marker strings and substituted a constructor initializer list the model had typed out itself. It happened to be right that time, but the technique has no safety net — the script prints "not found" and exits 0 if the marker text differs by one character, it can't be reviewed as a diff, and every character of the replacement is a fresh chance to introduce code that was in neither side. If you must script it, splice from the `:2:`/`:3:` blobs, never from prose you generated.

### Watch out for rerere

Some checkouts (the laptop's dash clone, for one) have `rerere.autoupdate = true` and a populated `.git/rr-cache`; check with `git config rerere.autoupdate`. When you see:

```
Recorded resolution for 'src/node/miner.cpp'.
Recorded preimage for 'src/node/miner.cpp'
```

git may have **auto-staged a previously-recorded resolution** without showing it to you. A stale rerere hit is a silent wrong answer. Inspect what actually got staged:

```bash
git diff --cached -- <file>
```

### Verify, stage explicitly, continue

```bash
# No markers survived anywhere — not just in the hunk you looked at
git grep -nE '^(<<<<<<<|=======|>>>>>>>)' -- <files>
git diff --check

git add <explicit/paths>      # never `git add -A`, `.`, or a broad `-u`
git rebase --continue
```

If a commit becomes genuinely empty because upstream already landed it, `git rebase --skip` is correct — but say so in your report. Never `--skip` to make an error message go away.

---

## 3. Prove the work survived — `range-diff`

This is the step most often skipped and the only one that actually answers "did the rebase come out right?". A clean `git log` and a green build prove nothing: a hunk dropped during conflict resolution usually still compiles.

```bash
git range-diff "$OLDBASE".."$PRE" "$BASE"..HEAD
```

Read the summary column for every commit:

- `=` — identical patch. Nothing to check.
- `!` — the patch changed. **Read the diff-of-diffs and explain each one.** Expected: context-line shifts and the hunks you deliberately resolved. Unexpected: whole hunks disappearing, `-` lines you never meant to remove, changes in files you never touched.
- `<` / `>` — a commit was dropped or added. Unless you intentionally `--skip`ped, that's a bug.

Then confirm the branch shape is unchanged:

```bash
git log --oneline "$BASE"..HEAD    # same count, order, and subjects as section 1
```

If range-diff shows something you can't explain, `git reset --hard "$PRE"` (or the backup ref) and redo the resolution. Do not push and hope review catches it.

**Then build and test** what the change touches — the relevant unit suite, functional test, and lints. A conflict resolved in a constructor initializer list, a header, or a serialization path deserves a real build, not a one-file compile. If a lint is skipped for a missing tool (`Skipping Python linting since flake8 is not installed`), that is **not a pass** — report it as skipped.

---

## 4. Force-push to the ref the PR actually reads

`<pr-remote>` is the remote whose URL is the PR's `headRepository` (`git remote -v`), not whichever remote is called `origin`. If that repository is dashpay/dash, stop and ask before pushing.

**dashpay/platform exception:** if the PR's head is on PastaPastaPasta/platform (`gh pr view <N> --json headRepositoryOwner`), don't push there. Fork PRs skip platform's Rust/Swift CI. Push the branch to dashpay/platform and replace the PR instead (see `file-pr`).

### Refresh the lease target first

`--force-with-lease` with no explicit value compares against your local `refs/remotes/<remote>/<branch>`. A stale tracking ref gets the push rejected with `stale info` even when nothing is wrong on the server:

```bash
git fetch <pr-remote> <branch>       # refresh the lease target
git push --force-with-lease <pr-remote> <branch>
```

Or state the expectation explicitly, which is stronger and doesn't depend on tracking-ref freshness:

```bash
git push --force-with-lease=<branch>:<sha-you-expect-to-replace> <pr-remote> <branch>
```

Never fall back to bare `-f` / `--force` because `--force-with-lease` was rejected. A rejection means your picture of the remote is wrong — find out why.

An SSH push that fails with `agent refused operation` is different: the Secretive key needs pasta's approval. Push the same lease over HTTPS instead: `git -c credential.helper='!gh auth git-credential' push --force-with-lease=<branch>:<sha> https://github.com/<owner>/<repo>.git <branch>`.

### The multi-URL `origin` trap

A remote can have more than one push URL; check `git remote -v` before pushing. The laptop's dash clone, for example, has **two push URLs** on `origin`:

```
origin          git@github.com:PastaPastaPasta/dash.git    (fetch)
origin          git@gitlab.com:PastaPastaPasta/dash-ci.git (push)
origin          git@github.com:PastaPastaPasta/dash.git    (push)
origin-github   git@github.com:PastaPastaPasta/dash.git    (fetch/push)
```

A single `git push origin` fans out to both and can **partially succeed** — GitLab CI updated, GitHub rejected — while exiting non-zero:

```
To gitlab.com:PastaPastaPasta/dash-ci.git
 + 005c618bb5ea...4886b9f7ef6d  (forced update)
To github.com:PastaPastaPasta/dash.git
 ! [rejected]   (stale info)
error: failed to push some refs
```

That leaves the mirrors divergent. So:

- When the push remote has several URLs, push the PR head to a single-URL remote for the repo that backs the PR (`origin-github` in the example), then push the multi-URL remote to keep the mirror in sync.
- Read **every line** of push output, not just the exit code. A zero exit doesn't mean every URL updated; a non-zero exit doesn't mean nothing changed.
- Confirm rather than assume:

```bash
gh pr view <N> --json headRefOid -q .headRefOid
git rev-parse HEAD          # must match
```

---

## 5. Report what actually happened

- the base you rebased onto, by hash and subject;
- commits before → after (counts and subjects), plus the range-diff verdict per commit;
- every conflict: file, which commit was being replayed, what you kept and why;
- anything skipped, dropped, or auto-resolved by rerere;
- tests and lints actually run — and any skipped for a missing tool;
- which remote and ref you pushed, including any push that partially failed on the way.

Do not compress a trial-and-error push sequence into "force-pushed with `--force-with-lease`". If the first attempt half-landed on a mirror, say so.

---

## Quick reference

```bash
# setup
gh pr view <N> --json headRefName,headRepositoryOwner,baseRefName,url
git status --short                                   # must be empty
BASE=<base-remote>/<base-branch>                     # from baseRefName and git remote -v
git fetch <base-remote> <base-branch> && git fetch <pr-remote> <branch>
PRE=$(git rev-parse HEAD); OLDBASE=$(git merge-base HEAD "$BASE")
git log --oneline "$OLDBASE"..HEAD
git branch "backup/prerebase-$(git rev-parse --short "$PRE")" "$PRE"
git rebase "$BASE"

# per conflict
git diff --name-only --diff-filter=U
git log -1 --format='%h %s' REBASE_HEAD && git show REBASE_HEAD -- <file>
git show :2:<file>   # ours = new base
git show :3:<file>   # theirs = commit being replayed
# ...edit the file with a real editing tool...
git grep -nE '^(<<<<<<<|=======|>>>>>>>)' -- <files> && git diff --check
git diff --cached -- <file>                          # catch stale rerere auto-staging
git add <explicit paths>
git rebase --continue

# verify
git range-diff "$OLDBASE".."$PRE" "$BASE"..HEAD
git log --oneline "$BASE"..HEAD
# ...build + targeted tests...

# push
git fetch <pr-remote> <branch>
git push --force-with-lease <pr-remote> <branch>           # the PR's headRepository
# if another remote mirrors the branch (multi-URL origin), push it too
gh pr view <N> --json headRefOid -q .headRefOid       # must equal git rev-parse HEAD

# recover
git rebase --abort
git reset --hard "$PRE"       # or the backup ref
git reflog
```

## Never

- Resolve conflicts by regex-splicing conflict markers with hand-typed code.
- `git add -A` / `git add .` mid-rebase.
- Rebase a dirty tree, or paper over one with `--autostash`.
- Declare the rebase good on `git log` plus a green build, without `git range-diff`.
- `git push -f` after `--force-with-lease` was rejected.
- Report success from a push that exited non-zero or partially failed.
