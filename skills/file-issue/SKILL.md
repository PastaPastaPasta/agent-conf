---
name: file-issue
description: File or edit a GitHub issue body safely. Use whenever you file, open, create or update an issue, whether the user asked or you are opening a follow-up yourself.
---

# File Issue

Twice a PR was posted with another PR's description, because a generic body
file (`$TMPDIR/pr-body.md`) was shared across sessions. `$TMPDIR` also differs
inside and outside the sandbox. Issues have the same trap.

- Search for an existing issue first (`gh issue list --search <terms> --state all`).
- Write the body to a unique absolute path naming the repo and topic; give
  parallel subagents separate paths. Pass it with `--body-file`.
- After creating or editing, read the body back (`gh issue view <N> --json body`)
  and fix any mismatch before doing anything else.
- Lead with the problem: what happens, what was expected, how to reproduce.
- No internal review notes (council, scores, review rounds, model names), no
  `@mentions`, and no names of our machines or local paths; see `file-pr`.
- No attribution footer in the body. Comments on the issue follow
  `leaving-pr-comments`.
