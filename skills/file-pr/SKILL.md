---
name: file-pr
description: File a concise PR that leads with the problem, routed to the right repo, remote, and base branch (dashpay forks, dashpay/platform same-repo, yappr staging). Use when asked to file, open, create, or push a PR.
---

# File PR

## Before filing

- Check whether a PR for this branch already exists (`gh pr list --head <branch> --state all`).
  If one is open, update it instead of opening another.
- Review the diff locally against the real base. Its contents must match the
  goal, with nothing unrelated staged.
- Never file from a detached HEAD or from the base branch. Use a feature-style
  branch (`feat/`, `fix/`, `chore/`; Codex uses `codex/`).

## Where it goes

Check `git remote -v` and `gh repo view --json nameWithOwner,parent` rather than
assume. Then:

| Repo | Push to | `gh pr create` | Base |
| --- | --- | --- | --- |
| `dashpay/dash` | the `PastaPastaPasta/dash` fork, never `dashpay/dash` (pick by URL) unless pasta explicitly says so for this case | `--repo dashpay/dash --head PastaPastaPasta:<branch>` | `develop` |
| `dashpay/bls-signatures` | the `PastaPastaPasta/bls-signatures` fork, never `dashpay/bls-signatures` unless pasta explicitly says so | `--repo dashpay/bls-signatures --head PastaPastaPasta:<branch>` | upstream default |
| `dashpay/platform` | the remote whose URL is `github.com/dashpay/platform`, never a fork | `--repo dashpay/platform --head <branch>` | current `v*-dev` |
| all other `dashpay/*` (`dash-wallet`, `base-sdk`, `rust-dashcore`, etc.) | the remote whose URL is `github.com/dashpay/<repo>`, in-repo (never a fork — fork PRs fail or skip CI on several repos; exception: `dashpay/guix.sigs` uses the fork per `dash-guix-release`) | `--repo dashpay/<repo> --head <branch>` | repo's working branch (e.g. `develop`, `main`, or target feature branch) |
| yappr | `origin` | `--base staging` | `staging`, never `master` |
| anything else | `origin` | defaults | the repo's working branch |

If you cannot tell which upstream a fork belongs to, ask before filing.

### dashpay/platform: never from a fork

This applies whichever repo the session started in (yappr, dash-forge, evo-tool,
…). Fork PRs skip the Rust workspace, wallet and Swift jobs, so they look green
with nothing tested.

Pick the push remote by URL, not by name. Remote names differ between machines:
laptop and agentbox use `origin` = dashpay and `fork` = PastaPastaPasta, while
older checkouts use `origin` = the fork and `upstream` = dashpay.

```sh
R=$(git remote -v | awk '$3 == "(push)" && tolower($2) ~ /github\.com[:\/]dashpay\/platform(\.git)?\/?$/ { print $1; exit }')
git push -u "$R" <branch>
gh pr create --repo dashpay/platform --head <branch> --base <v*-dev> --body-file <file>
```

If `R` is empty, add the remote (`git remote add dashpay https://github.com/dashpay/platform.git`)
rather than falling back to the fork. After filing, `gh pr view <N> --json isCrossRepository`
must be `false`. A fork PR can't be retargeted: push the branch to dashpay, open
a replacement with the same body, and close the fork PR with a link to it.

`git-guard.sh` blocks pushes to PastaPastaPasta/platform and `gh pr create` /
`gh api …/pulls` with a fork head.
Its `PLATFORM_FORK_OK=1` override is only for branches meant to stay on the fork
with no PR (git pins); never use it to file a PR.

## Title

Titles usually become commit messages, so follow the repo's conventions. Look
at recent merged PRs and `git log`. dashpay/platform: allowed scopes only, `!`
only for consensus-breaking changes, lowercase subject. Prefer a title that
says why the change matters:

> ❌ perf(server): negotiate permessage-deflate on the websocket
>
> ✅ perf(server): cut websocket frame size by 70%+ with gzipping

## Description

Open with a plain explanation of the problem, based on the user's original
request, then briefly explain the fix. Do not lead with an inventory of
changes:

> ❌ Removed implicit workspace carry-over from every "new thread" entry point
> (cmd+n / cmd+shift+o, sidebar v1/v2 buttons, command palette). …
>
> ✅ My "new worktree" default was ignored when starting new threads on existing
> worktrees. Super unintuitive. Now your preferences always apply.

- Use the repo's PR template when it has one (`.github/PULL_REQUEST_TEMPLATE.md`);
  fill its sections and delete its helper text.
- Say how you tested or proved the change, in a line or two.
- No `@mentions`, and no internal tracking or audit IDs; GitHub `#123` refs are
  fine.
- No internal review notes (council, scores, review rounds, model names) in PR
  descriptions, PR comments or commit messages. Report those to the user, not
  on GitHub. The comment footer's model slug is the one exception.
- Never put the autonomous comment footer (`🤖 Posted autonomously by ...`) in
  PR descriptions; that footer is for comments/reviews only. Follow any
  repo-specific PR template disclosure section (e.g. `base-sdk`'s "Agent
  disclosure") when present.
- Check the title, body, quotes and attachments for secrets and private
  details (hostnames, tailnet IPs, home infrastructure, memory contents).
- Describe the test setup generically. Reviewers care what was tested and on
  what (network, version, sync state), not which of our machines ran it. Never
  name our boxes (strixbox, agentbox, Mac Studio, the laptop, CT/VM numbers)
  or local paths. Naming them isn't a leak, it just looks sloppy:

  > ❌ All values were read from fully synced v24.0.0-rc.4 mainnet and testnet
  > nodes on strixbox.
  >
  > ✅ All values were read from fully synced v24.0.0-rc.4 mainnet and testnet
  > nodes.

Twice a PR was posted with another PR's description, because a generic body
file (`$TMPDIR/pr-body.md`) was shared across sessions; `$TMPDIR` also differs
inside and outside the sandbox. Write the body to a unique absolute path naming
the repo and branch, give parallel subagents separate paths, and pass it with
`--body-file`. After creating or editing a PR, read the body back with
`gh pr view <N> --json body` and fix any mismatch before doing anything else.

## UI proof

If a PR changes anything a user sees (web, desktop or mobile UI, CLI output,
styles, or vendored UI assets), its body needs a `## UI proof` section that
shows the change, so a reviewer can see it without checking out the branch.

- Include before (exact base, where the screen existed) and after (PR head)
  screenshots of each changed screen or state. For interactive flows, add a
  short recording: a GIF plays inline, and a video shows up as a link. For CLI
  output, before and after output in code blocks is enough.
- Capture desktop and mobile widths when the UI is responsive, and light and
  dark when the app has both.
- Capture in a clean, isolated session with test data: a headless browser,
  Xvfb or `agent-gui`, or an emulator or simulator through the device tools.
  Run the build and capture in a boat.dev sandbox (`boat`) when the local box
  can't fit them. `capture-visual-evidence` covers provenance, fixtures,
  checking each image, and where to host it.
- Link the images at immutable URLs that render in the PR. Never use local
  paths or expiring links, and never commit captures to the product branch.
- Look at every image before posting. Captures must not show secrets, tokens,
  emails, real names, mainnet addresses or balances, or the IPs and hostnames
  of our machines and networks. If one does, recapture with test data; don't
  blur it.
- If a capture is impossible (the platform isn't available, or it needs
  hardware or credentials you don't have), use the same section to say why and
  what you verified instead. Never just leave the proof out.

## Filing

If a push over SSH fails with `agent refused operation`, the cause is the
Secretive enclave key: it needs a per-use approval only pasta can give, which
is common for background agents. Push over HTTPS with gh's token instead:
`git -c credential.helper='!gh auth git-credential' push https://github.com/<owner>/<repo>.git <local>:<branch>`.
Commit signing is unaffected.

Open a real PR, not a draft, so review bots run. If `gh pr create` fails
because the GraphQL rate limit is used up, use REST:
`gh api repos/<owner>/<repo>/pulls -f title=... -f head=... -f base=... -F body=@<file>`.

In T3, call `link_pull_request` with the PR URL. Then start `babysit` unless
the user opted out: returning the URL is not completion.

**Pin before merging if you have more to do.** Unless this thread is pinned,
it settles as soon as a linked PR merges, and a settled thread never wakes
again. If you need to keep working after the merge (more PRs in a series, a
tag, a deploy, a follow-up fix), pin the thread first with `t3_thread_organize`
(`action: "pin"`), then merge. Otherwise merge, and this thread ends. When the
remaining work is done, `unpin` and `settle` it.

Do not post a follow-up PR comment unless it serves the request. When one is
needed, use `leaving-pr-comments`.

## Report

PR URL, target repo and base, branch, head SHA, push remote, and anything you
assumed (base choice, upstream detection).
