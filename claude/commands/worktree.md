---
description: Create a git worktree for a feature branch and cd into it
allowed-tools: Bash(git:*), Bash(cd:*), Bash(ls:*), Bash(pwd:*)
argument-hint: <branch-name>
---

Create a git worktree for the branch `$ARGUMENTS` and change into it.

Steps:
1. Create a new worktree in a subdirectory named `worktrees/$ARGUMENTS`
2. Create a new branch named `$ARGUMENTS` based on the current branch
3. Change directory into the new worktree
4. Report the new working directory

Example: If in `/workspace/platform` and running `/worktree fix-revision-updates`, create worktree at `/workspace/platform/worktrees/fix-revision-updates` with branch `fix-revision-updates`.
