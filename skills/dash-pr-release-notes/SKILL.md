---
name: dash-pr-release-notes
description: Add or update release notes for Dash Core pull requests that use committed PR-specific note files like `/doc/release-notes-7052.md`. Use when a Dash PR needs proper release notes, when notes were mistakenly put in the GitHub PR body, or when Codex must convert a code change into the repo's snippet format.
---

# Dash PR Release Notes

Add release notes as committed repo content, not as prose embedded in the GitHub PR body.

## Workflow

1. Confirm the repo uses the Dash PR-specific release-note convention.
   Check `doc/developer-notes.md` if needed. The expected location is
   `doc/release-notes-<PR number>.md`.
2. Determine the PR number from the user request, PR URL, current branch, or
   GitHub metadata.
3. Read one or two local examples before writing.
   Start with small PR-note examples such as `doc/release-notes-7181.md` and
   `doc/release-notes-25957.md`. Read larger release notes only if the correct
   section heading is unclear.
4. Choose the narrowest accurate release-notes section heading.
   Prefer headings already used in Dash release notes, such as `Wallet`,
   `Updated RPCs`, `New RPCs`, `GUI changes`, `Build System`, `Bug Fixes`, or
   `Miscellaneous`.
5. Write a short snippet in release-notes file style.
   Use a heading and underline, then one or more bullets. End each bullet with
   `(#<PR number>)`.

## Required Format

Use this shape in `doc/release-notes-<PR number>.md`:

```md
Wallet
------

- User-facing summary. (#7052)
```

## Writing Rules

- Write for release notes, not for code review.
- Describe the user-visible or operator-visible effect first.
- Mention gating, compatibility, or preserved old behavior when it materially
  changes how the feature should be understood.
- Keep implementation detail minimal unless it explains user impact.
- Prefer one bullet unless the PR has clearly separate visible changes.
- Wrap long bullets cleanly over multiple lines.
- Do not add `## Release Notes` or any full-release-document scaffolding to the
  PR-specific file.

## PR Body Rule

Keep release notes out of the GitHub PR body unless the user explicitly asks
for them there too. If release notes were added to the PR body by mistake,
remove that block after committing `doc/release-notes-<PR number>.md`.

## Validation

- Verify the file path matches the PR number exactly.
- Verify the heading style matches existing examples.
- Verify the bullet ends with the PR number in parentheses.
- If you changed repo content, commit and push according to the repo workflow
  unless the user asked otherwise.
