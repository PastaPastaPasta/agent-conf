---
name: agent-conf
description: Manage shared agent skills, global instructions (CLAUDE.md, AGENTS.md, GEMINI.md, Cursor, OpenCode), harness support files, private overlays, memory sync, and agent-config sync status. Use whenever creating, editing, auditing, or troubleshooting skills, global agent instructions, harness configs, synced memory setup, or agent-config status problems.
---

# Agent Config Sync (`agent-conf`)

Shared skills, global instructions, and Claude/OpenCode agents, commands, plugins, and scripts are synced from `PastaPastaPasta/agent-conf` (`~/workspace/agent-conf`). Private host configs, host notes, and private infrastructure skills come from the optional private overlay (`~/workspace/agent-conf-private`), and Claude memory syncs separately through `~/workspace/agent-memory`.

## Never edit synced copies in place

These paths are generated or symlinked from sync-owned copies (`~/.local/share/agent-config/{live,overlay}`) that reset every 15 minutes — edits made directly there are overwritten:

- Skills: `~/.claude/skills`, `~/.codex/skills`, `~/.cursor/skills`, `~/.gemini/skills`, `~/.gemini/config/skills`, `~/.config/opencode/skills`
- Instructions: `~/.claude/CLAUDE.md`, `~/.codex/AGENTS.md`, `~/.gemini/GEMINI.md`, `~/.cursor/rules/global-workflow.mdc`, `~/.config/opencode/AGENTS.md`
- Support files: synced entries under `~/.claude/{agents,commands,scripts}` and `~/.config/opencode/{agents,commands,plugins}`

## How to make a change

1. **Choose the right repo:**
   - **Public (`~/workspace/agent-conf`):** portable skills, global instructions, shared agents/commands/plugins/scripts. Never commit private hostnames, tailnet URLs, LAN IPs, or secrets (enforced by tests and pre-push hooks).
   - **Private overlay (`~/workspace/agent-conf-private`):** host-specific configs (`hosts.json`, `hosts/<host>/notes.md`), private infrastructure skills, and host-scoped overrides.
   - **External git-backed skills:** skills with `"git"` in `skills.json` (e.g. `agentic-qa`, `dash-backport-review-skill`) live in their own repo at `path`.
2. **Adding a skill:** create `skills/<name>/SKILL.md` with clear, harness-agnostic `"<what>. Use when <triggers>."` frontmatter, and add `"<name>": {}` to `skills.json` (omit `targets` so every installed harness receives it). Keep paths portable (`~/…` or relative `scripts/…`).
3. **Run tests before pushing:**
   ```bash
   cd ~/workspace/agent-conf
   python3 -I tests/test_agent_config.py
   python3 -I tests/test_git_guard.py
   python3 -I tests/test_pre_push.py
   python3 -I tests/test_rm_safety_allow.py
   ```
4. **Commit, push to `main`, and sync immediately:**
   ```bash
   ~/workspace/agent-conf/bin/agent-config sync
   ~/workspace/agent-conf/bin/agent-config status
   ```

## Guardrails

- Never put secrets in memory, overlay, or skills.
- If `agent-config status` reports problems (stale sync, manifest error, memory conflict, broken symlink), tell the user instead of working around them.
- In `instructions/*.md`, preserve the `(injected via \`GIT_CONFIG_*\` env vars in ...)` phrase in the signing bullet so `hosts.json` `replace` rules continue rewriting it on non-laptop hosts.
