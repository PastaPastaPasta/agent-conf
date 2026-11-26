# OpenCode Global Workflow

OpenCode is the only experimental agent environment on this machine. Custom
provider routing, model aliases and related experiments live in
`~/.config/opencode/` (hand-managed: `opencode.json`, `plugins/` and the
plugin dependencies). Everything portable — the skills, the agents and commands,
and this file — comes from `~/workspace/agent-conf` and is synced like every
other harness.

## Native-agent boundary

- Treat `~/.codex`, `~/.claude`, `~/.claude.json`, `~/.claudex`,
  `~/.local/bin/claudex`, and `~/.config/dcg-claudex` as read-only.
- Never route Claude Code through a non-Anthropic endpoint or alter its model
  aliases, authentication, or provider environment.
- Never add a proxy or custom model provider to Codex. Its native configuration
  is shared with the Codex GUI app and must remain compatible with it.
- Reading portable skills and memory notes from those locations is allowed.
- If the user explicitly asks to change a protected native-agent path, explain
  this boundary and require them to confirm that exact exception first.

## Memory

pasta's agents share a persistent memory: Markdown notes under
`~/.claude/projects/<key>/memory/`, kept in sync across machines by
agent-config. The `agent-memory` plugin adds the `MEMORY.md` indexes for the
current project, for `~/workspace` (shared across projects) and for `~` to every
session. Read a linked note by its absolute path when its hook is relevant, and
verify what it says against live state before acting on it. The folders are
read-only here; report durable new facts in your final reply instead.

## Git workflow

- Commits are signed with the dedicated agent SSH key injected by the OpenCode
  workflow guard (`~/.config/opencode/plugins/workflow-guard.ts`). Never disable
  signing or override the signing configuration. If a commit ever fails to sign,
  stop and tell the user rather than committing unsigned.
- Prefer conventional commit messages.
- Never use `git add -A`, `git add --all`, `git add .`, or `git commit -a`; stage
  only the explicit, intended paths.
- Commit user-requested code changes by default unless explicitly told not to.
- Push by default only when the current feature-style branch already has an
  upstream branch. Never push directly to `master`, `develop`, or `v*-dev`.
- Reuse an existing worktree for follow-up PR work when one already checks out
  the relevant branch and is not actively being used elsewhere.
- A request to rebase a pull request includes a verified `--force-with-lease`
  update of the eligible PR head branch.

## Model routing

- `build`: GPT-5.6 Sol high; `plan`: Gemini Pro Agent; `explore`: GPT-5.6 Luna
  low; `general`: Grok Composer 2.5 Fast. The `agent` section of `opencode.json`
  (hand-managed) is the source for those; the custom subagents (`reviewer`,
  `critic`, `security-auditor`, `local-explorer`) come from `opencode/agents/`
  in `~/workspace/agent-conf` and intentionally carry no model assignments
  (machine-specific); any per-machine model override goes in the hand-managed
  `opencode.json`, never in the repo.

## Validation

- Build every source, header, or build-configuration change locally.
- Run relevant fast tests and targeted linters for touched code.
- For Dash Core in a fresh worktree, reuse the existing depends output under
  `~/workspace/dash/depends` and the repository's detected host triplet.

## Quality gates

- After multi-file, complex, or architectural changes, load and run the
  `code-review-validator` skill before handoff.
- After adding significant new code, also load `code-simplifier` and apply safe
  simplifications.
- Investigate review feedback before changing code. Keep PR fixes narrow and
  classify automated feedback as valid, partial, or false positive.

## GitHub attribution

Every autonomous GitHub comment, review, reply, or discussion message (but not
PR/issue descriptions, commit messages, or code) must end with:

```
---
🤖 Posted autonomously by OpenCode on behalf of pasta.
```

## Agent config sync

- The skills under `~/.config/opencode/skills`, the agents and commands under
  `~/.config/opencode/agents` and `~/.config/opencode/commands`, and this file
  are generated or symlinked from agent-conf (`~/workspace/agent-conf`). Never
  edit them in place.
- To change one, edit `~/workspace/agent-conf` (or a worktree), run its tests,
  commit, and push to `main`. A sync (run from the live copy at
  `~/.local/share/agent-config/live`) applies the change. New skills go in
  `skills/<name>/` plus `skills.json` with an `opencode` target; keep paths
  portable (`~/…`).
- Never put secrets in memory or skills.
- If `agent-config status` reports problems, tell the user instead of working
  around them.
