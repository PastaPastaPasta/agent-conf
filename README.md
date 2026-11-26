# agent-conf

Shared agent setup kept in sync across machines that run coding agents (T3 Code, Claude Code, Codex, Cursor, Gemini CLI, Antigravity, OpenCode; Muse reads Claude Code's files itself).

Private host configurations, private infrastructure skills, and Claude Code memory live in separate optional private repositories so this repository stays cleanly shareable.

## What it manages

| Source | On each machine |
|---|---|
| `skills/<name>/` + `skills.json` | Symlinked into `~/.claude/skills`, `~/.codex/skills`, `~/.cursor/skills`, `~/.gemini/skills` (Gemini CLI), `~/.gemini/config/skills` (Antigravity) and `~/.config/opencode/skills` (OpenCode, which auto-discovers that folder) per each skill's `targets`, on machines where that harness's folder exists. Muse discovers `~/.claude/skills` and `~/.codex/skills` itself. `hosts` limits a skill to specific hosts; a host's `skip_skills` drops it there. A skill with `git` lives in its own repo, cloned to `path` and fast-forwarded. Skills removed from the manifest are unlinked. |
| `instructions/CLAUDE.md`, `instructions/AGENTS.md`, `instructions/GEMINI.md`, `instructions/CURSOR.md`, `instructions/OPENCODE.md` | Rendered to `~/.claude/CLAUDE.md`, `~/.codex/AGENTS.md`, `~/.gemini/GEMINI.md`, `~/.cursor/rules/global-workflow.mdc` and `~/.config/opencode/AGENTS.md`, with the host's `notes` prepended, `drop_sections` removed and `replace` rules applied. YAML frontmatter (Cursor) stays first. |
| `opencode/{agents,commands}/`, `hosts/<host>/opencode/…` | Symlinked into `~/.config/opencode/…`; host folders add machine-only files. The repo's agents intentionally carry no model assignments (machine-specific); per-machine model overrides go in the hand-managed `~/.config/opencode/opencode.json`. |
| `claude/{agents,commands,scripts}/`, `hosts/<host>/claude/…` | Symlinked into `~/.claude/…`; host folders add machine-only files. |
| Optional private overlay repo (`--overlay-repo`) | Merged on top of `hosts.json`, `skills.json`, `skills/`, `hosts/`, `claude/`, and `instructions/`. Keeps private host configs and private infrastructure skills out of this public repo. |
| Optional private memory repo (`--memory-repo` or `memory_repo` in `hosts.json`) | Three-way merges `memory/home`, `memory/workspace`, and `memory/workspace-<repo>` both ways with `~/.claude/projects/<key>/memory`. Omitted = memory sync skipped cleanly. |

Not managed: `settings.json`, credentials, MCP config, hooks registration, Codex `config.toml` and its `.system` skills, Cursor rules other than `global-workflow.mdc`, and memory for harnesses other than Claude Code. OpenCode's hand-managed `~/.config/opencode/opencode.json` (providers, keys and model assignments), `plugins/` and their dependencies stay in place per machine.

## Where things live on a machine

- `~/workspace/agent-conf`: ordinary editing clone. Edit here (or in a worktree), run tests, commit and push to `main`. Sync fast-forwards it (plus `~/workspace/agent-conf-private` and `~/workspace/agent-memory`, if present) when clean on `main`.
- `~/.local/share/agent-config/live`: owned by sync and reset to `origin/main` every run. Links point here.
- `~/.local/share/agent-config/overlay`: owned by sync; clone of the private overlay repo (when configured).
- `~/.local/share/agent-config/memory`: owned by sync; clone of the separate memory repo (when configured).
- `~/.local/share/agent-config/memory-base`: common ancestor for three-way memory merges.
- `~/.local/share/agent-config/backup/<time>/`: everything sync replaced or removed in the home folder.
- `~/.local/share/agent-config/run-sync`: scheduler bootstrap copied outside the repo so a bad commit can't break recovery. Rerun `setup` after changing `scheduler/`.

## Quick start

```sh
git clone https://github.com/PastaPastaPasta/agent-conf.git ~/workspace/agent-conf
~/workspace/agent-conf/bin/agent-config setup --host default
```

With a private overlay and/or private memory repo:

```sh
~/workspace/agent-conf/bin/agent-config setup \
  --host <name> \
  --overlay-repo <url|owner/repo|none> \
  --memory-repo <url|owner/repo|none>
```

`owner/repo` shorthands inherit SSH vs HTTPS transport from `agent-conf`'s `origin` remote. `setup` records `~/.config/agent-config/{host,overlay-repo,memory-repo}`, installs the 15-minute schedule (launchd on macOS, systemd user timer on Linux), and runs a first sync.

## A sync (every 15 minutes; `bin/agent-config sync` to run one now)

1. Bring `live` (and `overlay`, if configured) to `origin/main`. Accidental edits inside sync-owned copies are saved to `live-edits/*.patch` and reported once.
2. If a memory repo is configured (`~/.config/agent-config/memory-repo`, else `memory_repo` in merged `hosts.json`), merge Claude memory three-way per note against `memory-base` and push. Conflicts park the losing copy in `memory-conflicts/`, mass deletions (>50%) are refused, secret-shaped notes are blocked, and rewritten history pauses memory sync.
3. Clone or fast-forward external skill repos (left alone while they have tracked changes).
4. Link skills, agents, commands, scripts; render instructions. Broken `skills.json` or `hosts.json` stops this step so nothing gets uninstalled.
5. Fast-forward clean editing clones (`~/workspace/agent-conf`, `~/workspace/agent-conf-private`, `~/workspace/agent-memory`).

`bin/agent-config status` prints the last result and exits 1 if there are problems or no clean sync in 3 hours.

## Skills adapted from tstack

`full-send`, `full-stop`, `sol-loop`, `council`, `file-pr`, `leaving-pr-comments`, `modernize` and `takeover` started as copies of [t3dotgg/tstack](https://github.com/t3dotgg/tstack) at `92e38e2` (MIT, `third_party/tstack/LICENSE`) and were adapted to this setup.

## Tests

```sh
python3 -I tests/test_agent_config.py
```
