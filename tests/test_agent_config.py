"""End-to-end tests for bin/agent-config: two fake machines (temp HOMEs) syncing through a local bare repo.
Run: python3 -I tests/test_agent_config.py"""
import fcntl, json, os, re, shutil, subprocess, sys, tempfile, time
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent
T = Path(tempfile.mkdtemp()).resolve()
GITCFG = T / "gitconfig"
GITCFG.write_text("[user]\n name = t\n email = t@t\n[commit]\n gpgsign = false\n[init]\n defaultBranch = main\n")
ENV = {k: v for k, v in os.environ.items() if not k.startswith("GIT_CONFIG")}
ENV.update(GIT_CONFIG_GLOBAL=str(GITCFG), GIT_CONFIG_NOSYSTEM="1")
fails = 0


def check(cond, msg, detail=""):
    global fails
    print(("ok   " if cond else "FAIL ") + msg + ("" if cond or not detail else f"\n{detail}"))
    fails += not cond


def sh(*cmd, cwd=None, check_rc=True):
    p = subprocess.run(cmd, cwd=cwd, env=ENV, capture_output=True, text=True)
    if check_rc and p.returncode:
        raise SystemExit(f"{cmd} failed: {p.stderr}{p.stdout}")
    return p


# --- the real repo's manifest and instruction sources stay consistent with bin/agent-config's maps --------------
ALL_HARNESSES = {"claude", "codex", "cursor", "gemini", "antigravity", "opencode"}
real_skills = json.loads((SRC / "skills.json").read_text())
check(all(set(s.get("targets", ALL_HARNESSES)) <= ALL_HARNESSES
          for s in real_skills.values()), "real skills.json targets only name supported harnesses")
restricted_skills = {name: s["targets"] for name, s in real_skills.items()
                     if set(s.get("targets", ALL_HARNESSES)) != ALL_HARNESSES}
check(not restricted_skills,
      "every real skill targets all harnesses (omit targets to inherit SKILL_DIRS)",
      f"restricted={restricted_skills}")
check(all((SRC / f"instructions/{n}.md").is_file() for n in ("CLAUDE", "AGENTS", "GEMINI", "CURSOR", "OPENCODE")),
      "every rendered instruction source exists in the real repo")
check(not (SRC / "memory").exists(), "real agent-conf repo contains no memory/ directory")
PRIVATE_PAT = re.compile(
    r"tail[a-z0-9]+\.ts\.net|69nuts\.com|192\.168\.|100\.81\.|172\.30\.|10\.30\.30\."
    r"|strix-pasta|dcgs-mac-studio|pasta-infrastructure|solar-forecast|dash-internal"
)
leaks = []
for p in sorted(SRC.rglob("*")):
    if ".git" in p.parts or not p.is_file() or p == Path(__file__).resolve():
        continue
    if p.suffix in (".pyc", ".png", ".jpg", ".gif", ".ico", ".zip"):
        continue
    if PRIVATE_PAT.search(p.read_text(errors="ignore")):
        leaks.append(str(p.relative_to(SRC)))
check(not leaks, "public agent-conf repo contains no private infrastructure markers", f"leaks={leaks}")

# --- a miniature agent-config repo pushed to bare "origin" + separate bare "memory-origin" -------------------
seed = T / "seed"
for d in ("bin", "instructions", "claude/agents", "hosts/box/claude/agents", "opencode/agents", "opencode/commands", "opencode/plugins", "skills/alpha", "skills/beta", "skills/gamma", "skills/everywhere", "skills/mac-only"):
    (seed / d).mkdir(parents=True)
shutil.copy(SRC / "bin/agent-config", seed / "bin/agent-config")
(seed / "instructions/CLAUDE.md").write_text("# Rules\n\n- signed (injected via `GIT_CONFIG_*` env vars in settings.json)\n\n"
                                             "## Delegating Computer Use to Codex\n\nmac only\n\n## Babysitting\n\nuse pr_wait\n")
(seed / "instructions/AGENTS.md").write_text("# Codex rules\n")
(seed / "instructions/GEMINI.md").write_text("# Gemini rules\n")
(seed / "instructions/CURSOR.md").write_text("---\ndescription: test rule\nalwaysApply: true\n---\n# Cursor rules\n")
(seed / "instructions/OPENCODE.md").write_text("# OpenCode rules\n")
(seed / "hosts/box/notes.md").write_text("# You are on box\n")
(seed / "claude/agents/reviewer.md").write_text("reviewer\n")
(seed / "opencode/agents/o-reviewer.md").write_text("opencode reviewer\n")
(seed / "opencode/commands/o-review.md").write_text("opencode review command\n")
(seed / "opencode/plugins/o-memory.ts").write_text("export default async () => ({})\n")
(seed / "hosts/box/claude/agents/boxonly.md").write_text("box agent\n")
for s in ("alpha", "beta", "gamma", "mac-only"):
    (seed / f"skills/{s}/SKILL.md").write_text(f"---\nname: {s}\n---\n")
ext_src = T / "ext-src"
ext_src.mkdir()
(ext_src / "SKILL.md").write_text("---\nname: ext\n---\nv1\n")
sh("git", "init", "-q", cwd=ext_src); sh("git", "add", ".", cwd=ext_src); sh("git", "commit", "-qm", "ext", cwd=ext_src)
mem_origin = T / "memory-origin.git"
sh("git", "init", "-q", "--bare", str(mem_origin))
mem_seed = T / "mem-seed"
mem_seed.mkdir()
(mem_seed / "README.md").write_text("# agent-memory\n")
sh("git", "init", "-q", cwd=mem_seed); sh("git", "add", ".", cwd=mem_seed); sh("git", "commit", "-qm", "init", cwd=mem_seed)
sh("git", "remote", "add", "origin", str(mem_origin), cwd=mem_seed); sh("git", "push", "-q", "origin", "main", cwd=mem_seed)
(seed / "skills/everywhere/SKILL.md").write_text("---\nname: everywhere\n---\nbody\n")
(seed / "skills.json").write_text(json.dumps({
    "alpha": {"targets": ["claude", "codex", "opencode"]}, "beta": {"targets": ["codex"]},
    "gamma": {"targets": ["cursor", "gemini", "antigravity"]},
    "everywhere": {},
    "mac-only": {"targets": ["claude"], "hosts": ["mac"]},
    "ext": {"git": str(ext_src), "path": "workspace/ext", "targets": ["claude"]}}, indent=1))
(seed / "hosts.json").write_text(json.dumps({
    "mac": {"memory_repo": str(mem_origin), "git_config": {"user.name": "mac-signer"}},
    "box": {"memory_repo": str(mem_origin), "notes": "hosts/box/notes.md",
            "drop_sections": ["Delegating Computer Use to Codex"],
            "replace": [[r"\(injected via `GIT_CONFIG_\*` env vars in [^)]*\)", "(set in ~/.gitconfig)"]]},
    "shared": {"notes": "hosts/box/notes.md"}}))
origin = T / "origin.git"
sh("git", "init", "-q", "--bare", str(origin))
sh("git", "init", "-q", cwd=seed); sh("git", "add", ".", cwd=seed); sh("git", "commit", "-qm", "seed", cwd=seed)
sh("git", "remote", "add", "origin", str(origin), cwd=seed); sh("git", "push", "-q", "origin", "main", cwd=seed)


def key(home, sub=""):
    return re.sub(r"[^A-Za-z0-9]", "-", str(home / "workspace" / sub).rstrip("/"))


def machine(name, host):
    home = T / name
    (home / ".claude/projects").mkdir(parents=True)
    (home / ".codex").mkdir()
    sh("git", "clone", "-q", str(origin), str(home / "workspace/agent-conf"))
    (home / ".config/agent-config").mkdir(parents=True)
    (home / ".config/agent-config/host").write_text(host)
    return home


def ac(home, *args):
    p = subprocess.run([sys.executable, str(SRC / "bin/agent-config"), *args],
                       env={**ENV, "AGENT_CONFIG_HOME": str(home)}, capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr


def mem(home, slot="dash"):
    return home / ".claude/projects" / key(home, slot) / "memory"


def origin_file_of(repo, path):
    p = sh("git", "--git-dir", str(repo), "show", f"main:{path}", check_rc=False)
    return p.stdout if p.returncode == 0 else None


def origin_file(path):
    return origin_file_of(mem_origin, path)


def push_from_work(home, msg, edit):
    work = home / "workspace/agent-conf"
    sh("git", "pull", "-q", "--ff-only", cwd=work)
    edit(work)
    sh("git", "add", "-A", cwd=work); sh("git", "commit", "-qm", msg, cwd=work); sh("git", "push", "-q", cwd=work)


def push_mem(repo, msg, edit):
    tmp = Path(tempfile.mkdtemp(dir=T))
    sh("git", "clone", "-q", str(repo), str(tmp))
    edit(tmp)
    sh("git", "add", "-A", cwd=tmp); sh("git", "commit", "-qm", msg, cwd=tmp); sh("git", "push", "-q", cwd=tmp)


# --- machine A ("mac") ------------------------------------------------------------------------------------
A = machine("A", "mac")
(A / ".config/opencode").mkdir(parents=True)
(A / ".config/opencode/opencode.json").write_text('{"model": "x/y", "plugin": ["./plugins/hand.ts"]}\n')
(A / ".claude").mkdir(parents=True, exist_ok=True)
(A / ".claude/settings.json").write_text('{"env": {"FOO": "1", "GIT_CONFIG_KEY_7": "stale"}, "model": "m"}\n')
(A / ".t3/userdata").mkdir(parents=True)
(A / ".t3/userdata/settings.json").write_text(json.dumps({"providerInstances": {
    "x": {"environment": [{"name": "KEEP", "value": "1", "sensitive": True},
                          {"name": "GIT_CONFIG_COUNT", "value": "9", "sensitive": False}]},
    "y": {"enabled": True}}}) + "\n")
(A / ".cursor").mkdir()
(A / ".gemini/config").mkdir(parents=True)
(A / ".claude/skills/alpha").mkdir(parents=True)
(A / ".claude/skills/alpha/OLD").write_text("old copy")
mem(A).mkdir(parents=True)
(mem(A) / "MEMORY.md").write_text("- [Note A](note-a.md) — from A\n- [Old](old.md) — stale\n")
for n in ("note-a", "old", "n1", "n2", "n3", "n4"):
    (mem(A) / f"{n}.md").write_text(f"{n} from A\n")
(A / ".claude/projects/-tmp-scratch/memory").mkdir(parents=True)
(A / ".claude/projects/-tmp-scratch/memory/x.md").write_text("machine-local\n")
(mem(A) / ".tmp.123.md").write_text("temp\n")

rc, out = ac(A, "sync")
live_a = A / ".local/share/agent-config/live"
check(rc == 0, "first sync on A succeeds", out)
check((A / ".claude/skills/alpha").resolve() == live_a / "skills/alpha", "skills link into the live copy")
check((A / ".codex/skills/beta").is_symlink() and not (A / ".claude/skills/beta").exists(), "targets respected")
check((A / ".claude/skills/mac-only").is_symlink(), "host-scoped skill installed on its host")
check((A / ".claude/skills/ext").resolve() == (A / "workspace/ext").resolve(), "external skill cloned and linked")
check(len(list((A / ".local/share/agent-config/backup").rglob("OLD"))) == 1, "replaced real folder backed up")
check("Generated by agent-config" in (A / ".claude/CLAUDE.md").read_text(), "instructions rendered")
check((A / ".cursor/skills/gamma").is_symlink() and (A / ".gemini/skills/gamma").is_symlink()
      and (A / ".gemini/config/skills/gamma").is_symlink() and not (A / ".claude/skills/gamma").exists(),
      "cursor/gemini/antigravity skill targets link into their own folders")
check(all((A / rel / "everywhere").resolve() == live_a / "skills/everywhere"
          for rel in (".claude/skills", ".codex/skills", ".cursor/skills",
                      ".gemini/skills", ".gemini/config/skills", ".config/opencode/skills")),
      "skill without targets links into every installed harness")
check("Gemini rules" in (A / ".gemini/GEMINI.md").read_text(), "gemini instructions rendered")
mdc = (A / ".cursor/rules/global-workflow.mdc").read_text()
check(mdc.startswith("---\n") and "alwaysApply: true" in mdc.split("---")[1]
      and "Generated by agent-config" in mdc and "Cursor rules" in mdc,
      "cursor rule rendered with frontmatter first", mdc)
check((A / ".claude/agents/reviewer.md").is_symlink() and not (A / ".claude/agents/boxonly.md").exists(), "host overlays")
check((A / ".config/opencode/skills/alpha").resolve() == live_a / "skills/alpha", "opencode skills link into the live copy")
check((A / ".config/opencode/agents/o-reviewer.md").resolve() == live_a / "opencode/agents/o-reviewer.md"
      and (A / ".config/opencode/commands/o-review.md").resolve() == live_a / "opencode/commands/o-review.md",
      "opencode agents and commands link into the live copy")
check((A / ".config/opencode/plugins/o-memory.ts").resolve() == live_a / "opencode/plugins/o-memory.ts",
      "opencode plugins link into the live copy")
want_env = {"GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "user.name", "GIT_CONFIG_VALUE_0": "mac-signer"}
check(json.loads((A / ".local/share/agent-config/git-env.json").read_text()) == want_env,
      "host git_config rendered to git-env.json for the OpenCode guard")
cl = json.loads((A / ".claude/settings.json").read_text())
check(cl["env"] == {"FOO": "1", **want_env} and cl["model"] == "m",
      "Claude settings env carries the host git env, stale GIT_CONFIG_* dropped, other settings kept", cl)
t3s = json.loads((A / ".t3/userdata/settings.json").read_text())["providerInstances"]
check([e["name"] for e in t3s["x"]["environment"]] == ["KEEP", *want_env]
      and {e["name"]: e["value"] for e in t3s["y"]["environment"]} == want_env and t3s["y"]["enabled"] is True,
      "every T3 provider instance gets the host git env and keeps its own variables", t3s)
oc_cfg = json.loads((A / ".config/opencode/opencode.json").read_text())
check(oc_cfg.get("model") == "x/y" and oc_cfg.get("plugin") == ["./plugins/hand.ts", "./plugins/o-memory.ts"],
      "opencode.json lists synced plugins and keeps hand-managed settings", oc_cfg)
check(not (A / ".config/opencode/skills/beta").exists(), "opencode skill targets respected")
check("Generated by agent-config" in (A / ".config/opencode/AGENTS.md").read_text()
      and "# OpenCode rules" in (A / ".config/opencode/AGENTS.md").read_text(),
      "opencode instructions rendered")
check(not mem(A).is_symlink() and origin_file("memory/workspace-dash/note-a.md") == "note-a from A\n",
      "memory stays a real folder and is pushed to the separate memory repo")
cfg_tree = sh("git", "--git-dir", str(origin), "ls-tree", "-r", "--name-only", "main").stdout
check("memory/" not in cfg_tree, "config repo stays free of memory/", cfg_tree)
mem_tree = sh("git", "--git-dir", str(mem_origin), "ls-tree", "-r", "--name-only", "main").stdout
check("x.md" not in mem_tree and ".tmp" not in mem_tree, "machine-local memory and temp files not synced", mem_tree)
check(sh("git", "-C", str(A / ".local/share/agent-config/memory"), "config", "user.name").stdout.strip() == "mac-signer",
      "host git_config applied to the memory repo clone")
rc, out = ac(A, "sync")
check(rc == 0 and "linked" not in out and "rendered" not in out and "listed plugins" not in out
      and "agent git env" not in out, "second sync is a no-op", out)
stale = [live_a / ".git/index.lock", live_a / ".git/HEAD.lock", A / ".local/share/agent-config/memory/.git/index.lock"]
for lock in stale:
    lock.write_text("")
    os.utime(lock, (time.time() - 3600, time.time() - 3600))
young = live_a / ".git/refs/heads/young.lock"
young.write_text("")
rc, out = ac(A, "sync")
check(rc == 0 and "removed stale" in out and not any(l.exists() for l in stale) and young.exists(),
      "sync clears stale git locks in its own clones and keeps a fresh one", out)
young.unlink()

# --- machine B ("box"): its own memory, a conflicting note, an old CLAUDE.md symlink -------------------------
B = machine("B", "box")
(B / ".cursor").mkdir()
(B / ".gemini").mkdir()  # Gemini CLI present, Antigravity (no config folder under it) absent
mem(B).mkdir(parents=True)
(mem(B) / "MEMORY.md").write_text("- [Note B](note-b.md) — from B\n- [Note A](note-a.md) — stale description\n")
(mem(B) / "note-b.md").write_text("note-b from B\n")
(mem(B) / "note-a.md").write_text("B's newer edit of note A\n")
future = time.time() + 600
os.utime(mem(B) / "note-a.md", (future, future))
(B / ".claude/CLAUDE.md").symlink_to(B / ".codex/AGENTS.md")
rc, out = ac(B, "sync")
check(not (B / ".local/share/agent-config/git-env.json").exists(), "no git env without host git_config")
check(rc == 1 and "changed on two machines" in out, "first sync on B reports its conflict as a problem", out)
check((mem(B) / "note-a.md").read_text() == "B's newer edit of note A\n" and
      origin_file("memory/workspace-dash/note-a.md") == "B's newer edit of note A\n", "newer side of a conflict wins")
st = json.loads(ac(B, "status")[1])
parked = st["memory_conflicts_last_7_days"]
check(parked and Path(parked[0]["other_copy"]).read_text() == "note-a from A\n", "other copy parked and listed in status")
state_file = B / ".local/share/agent-config/state.json"
saved_state = state_file.read_text()
st_old = json.loads(saved_state)
st_old.update(last_ok=time.time() - 4 * 3600, problems=[])
state_file.write_text(json.dumps(st_old))
rc, out = ac(B, "status")
check(rc == 1 and "no successful sync in the last 3 hours" in out, "status flags a stalled scheduler as a problem", out)
state_file.write_text(saved_state)
idx = (mem(B) / "MEMORY.md").read_text()
check("note-a.md" in idx and "note-b.md" in idx and (mem(B) / "n1.md").exists(), "memory merged into B's real folder")
check(idx.count("note-a.md") == 1 and "from A" in idx, "an entry indexed on both sides stays one entry (repo's line)", idx)
cb = B / ".claude/CLAUDE.md"
check(not cb.is_symlink() and "# You are on box" in cb.read_text() and "mac only" not in cb.read_text()
      and "(set in ~/.gitconfig)" in cb.read_text(), "old symlink replaced; box transforms applied")
check(not (B / ".claude/skills/mac-only").exists() and (B / ".claude/agents/boxonly.md").is_symlink(), "host scoping")
check(not (B / ".config/opencode").exists(), "opencode files are not written without an opencode config dir")
bmdc = (B / ".cursor/rules/global-workflow.mdc").read_text()
check(bmdc.startswith("---\n") and "# You are on box" in bmdc,
      "host notes stay behind cursor frontmatter", bmdc)
check((B / ".gemini/skills/gamma").is_symlink() and "Gemini rules" in (B / ".gemini/GEMINI.md").read_text()
      and not (B / ".gemini/config").exists(),
      "gemini linked and rendered while antigravity's absent anchor is skipped, never created")

# --- both machines edit the same note, then A pushes an instruction change: nobody gets stuck --------------------
ac(A, "sync")
(mem(A) / "n1.md").write_text("n1 edited on A\n")
(mem(B) / "n1.md").write_text("n1 edited on B\n")
ac(A, "sync")
push_from_work(A, "docs: new rule", lambda w: (w / "instructions/CLAUDE.md").write_text(
    (w / "instructions/CLAUDE.md").read_text() + "\n## New rule\n\nbe nice\n"))
rc, out = ac(B, "sync")
check("be nice" in cb.read_text() and "changed on two machines" in out, "a same-note conflict doesn't block other updates", out)
rc, out = ac(B, "sync")
check(rc == 0, "the same conflict isn't reported again", out)
check(origin_file("memory/workspace-dash/n1.md") in ("n1 edited on A\n", "n1 edited on B\n"), "conflict resolved, one version pushed")

# --- index edits merge three-way; deletions propagate (with a backup) -----------------------------------------
ac(A, "sync")
(mem(A) / "MEMORY.md").write_text((mem(A) / "MEMORY.md").read_text().replace("- [Old](old.md) — stale\n", ""))
(mem(A) / "old.md").unlink()
(mem(B) / "MEMORY.md").write_text((mem(B) / "MEMORY.md").read_text() + "- [B2](b2.md) — added on B\n")
(mem(B) / "b2.md").write_text("b2\n")
ac(A, "sync"); ac(B, "sync"); ac(A, "sync")
for h in (A, B):
    i = (mem(h) / "MEMORY.md").read_text()
    check("b2.md" in i and "old.md" not in i and not (mem(h) / "old.md").exists(), f"index edits merged on {h.name}", i)

# --- a mass deletion is not propagated; a secret is not exported; neither blocks syncing ---------------------
for n in ("note-a", "note-b", "n1", "n2", "n3", "n4", "b2"):
    (mem(A) / f"{n}.md").unlink()
(mem(A) / "secret.md").write_text("token ghp_" + "a" * 36 + "\n")
(mem(A) / "safe.md").write_text("task-runner-for-worktrees-and-simulators-cleanup is fine\n")
rc, out = ac(A, "sync")
check("kept them instead" in out and (mem(A) / "n2.md").exists(), "mass deletion restored instead of propagated", out)
check("contains a secret" in out and origin_file("memory/workspace-dash/secret.md") is None, "secret note not exported")
check(origin_file("memory/workspace-dash/safe.md") is not None, "sk- inside a word is not a secret")
rc, out = ac(A, "sync")
check("contains a secret" in out, "secret keeps being reported until removed")
(mem(A) / "secret.md").unlink()

# --- an edit inside the live copy is saved, reported once, and reset ------------------------------------------
live_b = B / ".local/share/agent-config/live"
(live_b / "skills/alpha/SKILL.md").write_text("edited in the wrong place\n")
rc, out = ac(B, "sync")
patches = list((B / ".local/share/agent-config/live-edits").glob("*.patch"))
check("edited the live copy" in out and patches and "wrong place" in patches[0].read_text()
      and "wrong place" not in (live_b / "skills/alpha/SKILL.md").read_text(), "live-copy edit saved as patch and reset", out)
rc, out = ac(B, "sync")
check("edited the live copy" not in out, "reported only once")

# --- the editing clone: fast-forwarded when clean, untouched when someone is working in it --------------------
push_from_work(A, "docs: rule two", lambda w: (w / "instructions/AGENTS.md").write_text("# Codex rules\n\nrule two\n"))
work_b = B / "workspace/agent-conf"
(work_b / "scratch.txt").write_text("untracked")  # untracked files don't count as someone working
ac(B, "sync")
check("rule two" in (work_b / "instructions/AGENTS.md").read_text(), "clean editing clone fast-forwarded")
(work_b / "skills/alpha/SKILL.md").write_text("work in progress\n")
push_from_work(A, "docs: rule three", lambda w: (w / "instructions/AGENTS.md").write_text("# Codex rules\n\nrule three\n"))
ac(B, "sync")
check((work_b / "skills/alpha/SKILL.md").read_text() == "work in progress\n" and
      "rule three" not in (work_b / "instructions/AGENTS.md").read_text(), "dirty editing clone left alone")
check("rule three" in (B / ".codex/AGENTS.md").read_text(), "...while the machine still gets the update")

# --- removing a skill uninstalls it; externals update even with untracked files -------------------------------
def drop_beta(w):
    j = json.loads((w / "skills.json").read_text())
    del j["beta"]
    (w / "skills.json").write_text(json.dumps(j, indent=1))
push_from_work(A, "chore: drop beta", drop_beta)
(A / "workspace/ext/.DS_Store").write_text("x")
(ext_src / "SKILL.md").write_text("---\nname: ext\n---\nv2\n"); sh("git", "commit", "-qam", "v2", cwd=ext_src)
rc, out = ac(A, "sync")
check(not (A / ".codex/skills/beta").exists() and "removed" in out, "dropped skill uninstalled", out)
check("v2" in (A / ".claude/skills/ext/SKILL.md").read_text(), "external updates despite untracked files")

# --- git writing non-UTF-8 bytes to stderr doesn't crash the sync --------------------------------------------
hook = A / "workspace/ext/.git/hooks/post-merge"
hook.write_text("#!/bin/sh\nprintf 'remote says \\342\\050 hi\\n' >&2\n"); hook.chmod(0o755)
(ext_src / "SKILL.md").write_text("---\nname: ext\n---\nv3\n"); sh("git", "commit", "-qam", "v3", cwd=ext_src)
rc, out = ac(A, "sync")
check(rc == 0 and "UnicodeDecodeError" not in out and "v3" in (A / ".claude/skills/ext/SKILL.md").read_text(),
      "non-UTF-8 git stderr tolerated", out)
hook.unlink()

# --- hand-edited generated file: regenerated, copy kept, reported once ---------------------------------------
cb.write_text(cb.read_text() + "\nlocal hack\n")
rc, out = ac(B, "sync")
saved = list((B / ".local/share/agent-config/backup").rglob("CLAUDE.md"))
check("edited by hand" in out and "local hack" not in cb.read_text() and any("local hack" in s.read_text() for s in saved),
      "hand edit replaced, kept in backup, reported", out)
rc, out = ac(B, "sync")
check(rc == 0, "next sync is clean again", out)

# --- round-2 bugs: missing folders, deleted index, broken manifest, rewritten history, backups ------------
ac(A, "sync"); ac(B, "sync")
before = origin_file("memory/workspace-dash/MEMORY.md")
shutil.rmtree(mem(B).parent)  # the whole project folder vanished on B
rc, out = ac(B, "sync")
check(origin_file("memory/workspace-dash/n2.md") is not None and (mem(B) / "n2.md").exists(),
      "a missing local folder is pulled, not treated as deletions", out + f"\norigin n2: {origin_file('memory/workspace-dash/n2.md')!r}; B has: {sorted(p.name for p in mem(B).glob('*')) if mem(B).exists() else None}")
(mem(A) / "MEMORY.md").unlink()
ac(A, "sync")
check(origin_file("memory/workspace-dash/MEMORY.md") == before and (mem(A) / "MEMORY.md").exists(),
      "a deleted index doesn't empty the shared one")
(mem(A) / "n2.md").write_text("n2 v2 from A\n")
ac(A, "sync")
ac(B, "sync")
check(any(p.read_text() == "n2 from A\n" for p in (B / ".local/share/agent-config/backup").rglob("n2.md")),
      "a local note overwritten by sync is backed up first")
push_mem(mem_origin, "chore: drop all memory", lambda w: shutil.rmtree(w / "memory/workspace-dash"))
rc, out = ac(B, "sync")
check((mem(B) / "n2.md").exists() and "deleted by the repo" in out, "a mass deletion from the repo is not applied", out)
tmp = T / "rewrite"
sh("git", "clone", "-q", str(mem_origin), str(tmp))
sh("git", "reset", "-q", "--hard", "HEAD~5", cwd=tmp)
sh("git", "push", "-q", "-f", "origin", "main", cwd=tmp)
rc, out = ac(A, "sync")
check("history was rewritten" in out and (mem(A) / "n2.md").read_text() == "n2 v2 from A\n",
      "rewritten history pauses memory sync instead of reverting it", out)
links_before = sorted(str(p) for p in (B / ".claude/skills").iterdir())
push_from_work(A, "broken manifest", lambda w: (w / "skills.json").write_text('{"alpha": {},}'))
rc, out = ac(B, "sync")
check(rc == 1 and "cannot read" in out and sorted(str(p) for p in (B / ".claude/skills").iterdir()) == links_before,
      "a broken skills.json uninstalls nothing and is reported", out)

# --- one sync at a time -----------------------------------------------------------------------------------------
with open(B / ".local/share/agent-config/sync.lock", "w") as lk:
    fcntl.flock(lk, fcntl.LOCK_EX)
    rc, out = ac(B, "sync")
check(rc == 75, "a second concurrent sync exits 75")

# --- the scheduler bootstrap: holds the lock for the whole sync, and skips when a sync is running ------------
st_a = A / ".local/share/agent-config/state.json"
sa = json.loads(st_a.read_text())
sa.pop("memory_base_commit", None)  # recover from the rewritten-history test above
st_a.write_text(json.dumps(sa))
(mem(A) / "boot.md").write_text("from a bootstrap run\n")
p = subprocess.run([sys.executable, str(SRC / "scheduler/run-sync")], env={**ENV, "AGENT_CONFIG_HOME": str(A)},
                   capture_output=True, text=True)
check(p.returncode in (0, 1) and origin_file("memory/workspace-dash/boot.md") is not None,
      "bootstrap runs a sync that pushes memory", p.stdout + p.stderr)
with open(A / ".local/share/agent-config/sync.lock", "w") as lk:
    fcntl.flock(lk, fcntl.LOCK_EX)
    head = sh("git", "-C", str(A / ".local/share/agent-config/live"), "rev-parse", "HEAD").stdout
    (live_a / "skills/alpha/SKILL.md").write_text("mid-sync state\n")
    p = subprocess.run([sys.executable, str(SRC / "scheduler/run-sync")], env={**ENV, "AGENT_CONFIG_HOME": str(A)},
                       capture_output=True, text=True)
    untouched = (live_a / "skills/alpha/SKILL.md").read_text() == "mid-sync state\n"
sh("git", "-C", str(live_a), "checkout", "-q", "--", "skills/alpha/SKILL.md")
check(p.returncode == 0 and "skipping" in p.stdout and untouched, "bootstrap never touches the live copy during a sync", p.stdout)

# --- pre-commit hook --------------------------------------------------------------------------------------------
hook_repo = T / "hook"
sh("git", "init", "-q", str(hook_repo))
shutil.copytree(SRC / ".githooks", hook_repo / ".githooks")
sh("git", "config", "core.hooksPath", ".githooks", cwd=hook_repo)


def try_commit(text):
    (hook_repo / "f.md").write_text(text)
    sh("git", "add", "f.md", cwd=hook_repo)
    return sh("git", "commit", "-qm", "x", cwd=hook_repo, check_rc=False)


check(try_commit("ok: task-runner-for-worktrees-and-simulators-cleanup\n").returncode == 0, "hook allows sk- inside words")
check(try_commit("token ghp_" + "a" * 36 + "\n" + "filler line\n" * 60000).returncode != 0, "hook blocks a token in a big diff")

# --- a second config + memory origin pair for symlink attacks and split-repo edge cases -----------------------
gorigin = T / "g-origin.git"
sh("git", "clone", "-q", "--bare", str(seed), str(gorigin))
gmem_origin = T / "g-mem-origin.git"
sh("git", "clone", "-q", "--bare", str(mem_seed), str(gmem_origin))


def gmachine(name, host):
    home = T / name
    (home / ".claude/projects").mkdir(parents=True)
    (home / ".codex").mkdir()
    sh("git", "clone", "-q", str(gorigin), str(home / "workspace/agent-conf"))
    (home / ".config/agent-config").mkdir(parents=True)
    (home / ".config/agent-config/host").write_text(host)
    (home / ".config/agent-config/memory-repo").write_text(str(gmem_origin) + "\n")
    return home


def gpush(home, msg, edit):
    work = home / "workspace/agent-conf"
    sh("git", "pull", "-q", "--ff-only", cwd=work)
    edit(work)
    sh("git", "add", "-A", cwd=work); sh("git", "commit", "-qm", msg, cwd=work); sh("git", "push", "-q", cwd=work)


G, U = gmachine("G", "mac"), gmachine("U", "box")
live_g = G / ".local/share/agent-config/live"

# --- symlinks under memory/ can't write, read or smuggle anything ---------------------------------------------
secret = T / "secret.txt"
secret.write_text("HA_TOKEN=very-secret\n")
mem(G).mkdir(parents=True, exist_ok=True)
(mem(G) / "MEMORY.md").write_text("- [G note](g-note.md) — local\n")
(mem(G) / "g-note.md").write_text("g\n")
ac(G, "sync")
work_alpha = G / "workspace/agent-conf/skills/alpha/SKILL.md"
alpha_before = work_alpha.read_text()


def plant_links(w):
    (w / "memory/workspace-pwn").symlink_to("../../../../../workspace/agent-conf/skills")
    idx = w / "memory/workspace-dash/MEMORY.md"
    idx.unlink(missing_ok=True)
    idx.symlink_to(secret)


push_mem(gmem_origin, "chore(memory): sync from box", plant_links)
(G / ".claude/projects" / key(G, "pwn") / "memory").mkdir(parents=True)
for n in ("alpha/SKILL", "a", "b", "c", "d"):
    (G / ".claude/projects" / key(G, "pwn") / f"memory/{n}.md").parent.mkdir(parents=True, exist_ok=True)
    (G / ".claude/projects" / key(G, "pwn") / f"memory/{n}.md").write_text("INJECTED SKILL\n")
(mem(G) / "MEMORY.md").write_text("- [G note](g-note.md) — local, edited\n")
rc, out = ac(G, "sync")
check(work_alpha.read_text() == alpha_before and "INJECTED" not in (G / ".claude/skills/alpha/SKILL.md").read_text(),
      "a symlinked memory slot can't write outside memory/", out)
check("is a symlink" in out, "...and is reported", out)
check("very-secret" not in (origin_file_of(gmem_origin, "memory/workspace-dash/MEMORY.md") or ""),
      "a symlinked MEMORY.md can't push a local file's contents", out)

# --- a stale scheduler bootstrap is reported -------------------------------------------------------------------
gpush(G, "chore: add the scheduler", lambda w: shutil.copytree(SRC / "scheduler", w / "scheduler"))
(G / ".local/share/agent-config/run-sync").write_text("# an old bootstrap\n")
rc, out = ac(G, "sync")
check("run-sync is out of date" in out, "a stale bootstrap is reported", out)
(G / ".local/share/agent-config/run-sync").unlink()

# --- leftovers from the retired laptop gate are repaired -------------------------------------------------------
sh("git", "config", "core.hooksPath", str(G / ".local/share/agent-config/trusted/.githooks"), cwd=G / "workspace/agent-conf")
st = G / ".local/share/agent-config/state.json"
st.write_text(json.dumps({**json.loads(st.read_text()), "approved": ["x"], "trusted_commit": "x"}))
ac(G, "sync")
check(sh("git", "config", "core.hooksPath", cwd=G / "workspace/agent-conf").stdout.strip() == ".githooks" and
      "approved" not in json.loads(st.read_text()), "a formerly gated machine's hooksPath and state are cleaned up")
ext_g = G / "workspace/ext"
shutil.rmtree(ext_g, ignore_errors=True)
sh("git", "clone", "-q", "--no-checkout", str(ext_src), str(ext_g))
ac(G, "sync")
check((ext_g / "SKILL.md").exists(), "a --no-checkout external skill clone gets checked out")

# --- memory/ itself as a symlink: memory sync stops instead of copying the target ---------------------------
home_like = T / "home-like"
(home_like / ".ssh").mkdir(parents=True)
(home_like / ".ssh/id_ed25519").write_text("PRIVATE\n")
def memory_link(w):
    shutil.rmtree(w / "memory", ignore_errors=True)
    (w / "memory").symlink_to(home_like)
push_mem(gmem_origin, "chore(memory): replace memory", memory_link)
rc, out = ac(G, "sync")
check("memory/ in the memory repo is a symlink" in out and
      not list((G / ".local/share/agent-config/memory-base").rglob("id_ed25519")),
      "a symlinked memory/ stops memory sync and copies nothing", out)

# --- shared config user without a memory repo: skills/instructions sync cleanly, memory skipped ---------------
S = machine("S", "shared")
sh("git", "remote", "set-url", "origin", str(gorigin), cwd=S / "workspace/agent-conf")
mem(S).mkdir(parents=True)
(mem(S) / "local-only.md").write_text("private local note\n")
rc, out = ac(S, "sync")
check(rc == 0 and (S / ".claude/skills/alpha").is_symlink() and not (S / ".local/share/agent-config/memory").exists()
      and (mem(S) / "local-only.md").read_text() == "private local note\n",
      "host without memory_repo syncs config/skills cleanly without touching memory", out)

# --- setup --memory-repo none disables memory sync even when hosts.json sets memory_repo ----------------------
N = machine("N", "box")
sh("git", "remote", "set-url", "origin", str(gorigin), cwd=N / "workspace/agent-conf")
rc, out = ac(N, "setup", "--host", "box", "--memory-repo", "none", "--no-schedule")
n_st = json.loads(ac(N, "status")[1])
check(rc == 0 and not (N / ".local/share/agent-config/memory").exists()
      and n_st.get("memory_repo") is None and n_st.get("memory_head") is None,
      "setup --memory-repo none disables memory sync and clears memory status", out)

# --- brand-new empty memory repo (no commits yet) accepts first push without deleting local notes -------------
empty_mem = T / "empty-mem.git"
sh("git", "init", "-q", "--bare", str(empty_mem))
E = machine("E", "shared")
sh("git", "remote", "set-url", "origin", str(gorigin), cwd=E / "workspace/agent-conf")
mem(E).mkdir(parents=True)
(mem(E) / "first.md").write_text("hello empty repo\n")
rc, out = ac(E, "setup", "--host", "shared", "--memory-repo", str(empty_mem), "--no-schedule")
check(rc == 0 and origin_file_of(empty_mem, "memory/workspace-dash/first.md") == "hello empty repo\n"
      and (mem(E) / "first.md").read_text() == "hello empty repo\n",
      "empty memory repo initializes cleanly on first push", out)

# --- transport/spelling change of the same memory repo updates remote in place without dropping base ----------
e_base_before = json.loads((E / ".local/share/agent-config/state.json").read_text())["memory_base_commit"]
rc, out = ac(E, "setup", "--host", "shared", "--memory-repo", f"file://{empty_mem}/", "--no-schedule")
e_state_after = json.loads((E / ".local/share/agent-config/state.json").read_text())
e_remote = sh("git", "-C", str(E / ".local/share/agent-config/memory"), "remote", "get-url", "origin").stdout.strip()
check(rc == 0 and e_state_after["memory_base_commit"] == e_base_before and e_remote == f"file://{empty_mem}/",
      "same memory repo via different URL spelling updates origin in place and keeps base", out)

# --- interrupted sync leaving dirty MEMORY_LIVE recovers cleanly on the next run ------------------------------
(E / ".local/share/agent-config/memory/memory/workspace-dash/first.md").write_text("interrupted mid-merge\n")
push_mem(empty_mem, "chore(memory): remote update",
         lambda w: (w / "memory/workspace-dash/first.md").write_text("remote v2\n"))
rc, out = ac(E, "sync")
check(rc == 0 and (mem(E) / "first.md").read_text() == "remote v2\n",
      "dirty MEMORY_LIVE from interrupted sync recovers cleanly on next run", out)

# --- broken remote on an existing memory clone reports an error instead of treating it as empty ---------------
moved_mem = T / "empty-mem-offline.git"
empty_mem.rename(moved_mem)
rc, out = ac(E, "sync")
moved_mem.rename(empty_mem)
check(rc == 1 and "ls-remote" in out and (mem(E) / "first.md").read_text() == "remote v2\n",
      "unreachable existing memory remote fails with error instead of acting empty", out)

# --- switching memory_repo re-clones cleanly and doesn't treat old memory-base as deletions -------------------
empty_mem2 = T / "empty-mem2.git"
sh("git", "init", "-q", "--bare", str(empty_mem2))
rc, out = ac(E, "setup", "--host", "shared", "--memory-repo", str(empty_mem2), "--no-schedule")
check(rc == 0 and origin_file_of(empty_mem2, "memory/workspace-dash/first.md") == "remote v2\n"
      and (mem(E) / "first.md").read_text() == "remote v2\n",
      "switching memory_repo re-clones and preserves local notes", out)

# --- legacy migration: when agent-memory is behind old base_commit, local notes are kept, not deleted ---------
mig_mem = T / "mig-mem.git"
sh("git", "clone", "-q", "--bare", str(empty_mem), str(mig_mem))
M = machine("M", "shared")
sh("git", "remote", "set-url", "origin", str(gorigin), cwd=M / "workspace/agent-conf")
(M / ".config/agent-config/memory-repo").write_text(str(mig_mem) + "\n")
mem(M).mkdir(parents=True)
(mem(M) / "first.md").write_text("remote v2\n")
(mem(M) / "ahead-note.md").write_text("created after agent-memory snapshot\n")
(M / ".local/share/agent-config/memory-base/workspace-dash").mkdir(parents=True)
(M / ".local/share/agent-config/memory-base/workspace-dash/first.md").write_text("remote v2\n")
(M / ".local/share/agent-config/memory-base/workspace-dash/ahead-note.md").write_text("created after agent-memory snapshot\n")
(M / ".local/share/agent-config/state.json").write_text(json.dumps({"base_commit": "deadbeef" * 5}))
rc, out = ac(M, "sync")
m_state = json.loads((M / ".local/share/agent-config/state.json").read_text())
check(rc == 0 and "history was rewritten" not in out and "base_commit" not in m_state
      and m_state.get("memory_base_commit")
      and (mem(M) / "ahead-note.md").exists()
      and origin_file_of(mig_mem, "memory/workspace-dash/ahead-note.md") == "created after agent-memory snapshot\n",
      "legacy migration with base ahead of agent-memory keeps and pushes local notes instead of deleting them", out)

# --- legacy migration: when agent-memory contains the old base_commit memory tree, 3-way deletions propagate --
match_cfg = T / "match-cfg.git"
sh("git", "clone", "-q", "--bare", str(seed), str(match_cfg))
match_seed = Path(tempfile.mkdtemp(dir=T))
sh("git", "clone", "-q", str(match_cfg), str(match_seed))
(match_seed / "memory/workspace-dash").mkdir(parents=True)
(match_seed / "memory/workspace-dash/keep.md").write_text("keep\n")
(match_seed / "memory/workspace-dash/drop-me.md").write_text("drop\n")
sh("git", "add", "memory", cwd=match_seed)
sh("git", "commit", "-qm", "chore(memory): legacy", cwd=match_seed)
sh("git", "push", "-q", "origin", "main", cwd=match_seed)
legacy_sha = sh("git", "rev-parse", "HEAD", cwd=match_seed).stdout.strip()
match_mem = T / "match-mem.git"
sh("git", "init", "-q", "--bare", str(match_mem))
match_mem_seed = Path(tempfile.mkdtemp(dir=T))
sh("git", "init", "-q", str(match_mem_seed))
shutil.copytree(match_seed / "memory", match_mem_seed / "memory")
sh("git", "add", "memory", cwd=match_mem_seed)
sh("git", "commit", "-qm", "seed memory", cwd=match_mem_seed)
sh("git", "remote", "add", "origin", str(match_mem), cwd=match_mem_seed)
sh("git", "push", "-q", "origin", "main", cwd=match_mem_seed)
M2 = machine("M2", "shared")
shutil.rmtree(M2 / "workspace/agent-conf")
sh("git", "clone", "-q", str(match_cfg), str(M2 / "workspace/agent-conf"))
(M2 / ".config/agent-config/memory-repo").write_text(str(match_mem) + "\n")
mem(M2).mkdir(parents=True)
(mem(M2) / "keep.md").write_text("keep\n")  # drop-me.md was deleted locally since legacy_sha
shutil.copytree(match_seed / "memory", M2 / ".local/share/agent-config/memory-base")
(M2 / ".local/share/agent-config/state.json").write_text(json.dumps({"base_commit": legacy_sha}))
rc, out = ac(M2, "sync")
check(rc == 0 and origin_file_of(match_mem, "memory/workspace-dash/drop-me.md") is None
      and origin_file_of(match_mem, "memory/workspace-dash/keep.md") == "keep\n",
      "legacy migration with matching memory tree preserves 3-way deletion propagation", out)

# --- private overlay repo: merges hosts.json, skills.json, private skills, notes, claude files, memory_repo ---
ov_origin = T / "overlay-origin.git"
sh("git", "init", "-q", "--bare", str(ov_origin))
ov_seed = T / "ov-seed"
for d in ("hosts/privbox", "skills/priv-skill", "claude/agents", ".githooks"):
    (ov_seed / d).mkdir(parents=True)
(ov_seed / "hosts/privbox/notes.md").write_text("# Private box notes\n")
(ov_seed / "skills/priv-skill/SKILL.md").write_text("---\nname: priv-skill\n---\nprivate\n")
(ov_seed / "claude/agents/priv-agent.md").write_text("private agent\n")
(ov_seed / ".githooks/pre-commit").write_text("#!/bin/sh\nexit 0\n")
ov_mem = T / "ov-mem.git"
sh("git", "init", "-q", "--bare", str(ov_mem))
(ov_seed / "hosts.json").write_text(json.dumps({
    "privbox": {"notes": "hosts/privbox/notes.md", "memory_repo": str(ov_mem),
                "git_config": {"user.name": "priv-signer"}}}, indent=1))
(ov_seed / "skills.json").write_text(json.dumps({
    "priv-skill": {"targets": ["claude"]},
    "alpha": {"targets": ["claude"], "hosts": ["other-host"]}}, indent=1))
sh("git", "init", "-q", cwd=ov_seed); sh("git", "add", ".", cwd=ov_seed); sh("git", "commit", "-qm", "ov", cwd=ov_seed)
sh("git", "remote", "add", "origin", str(ov_origin), cwd=ov_seed); sh("git", "push", "-q", "origin", "main", cwd=ov_seed)

O = machine("O", "shared")
sh("git", "remote", "set-url", "origin", str(gorigin), cwd=O / "workspace/agent-conf")
sh("git", "clone", "-q", str(ov_origin), str(O / "workspace/agent-conf-private"))
mem(O).mkdir(parents=True)
(mem(O) / "ov-note.md").write_text("from overlay host\n")
rc, out = ac(O, "setup", "--host", "privbox", "--overlay-repo", str(ov_origin), "--no-schedule")
o_st = json.loads(ac(O, "status")[1])
check(rc == 0 and (O / ".claude/skills/priv-skill").resolve() == (O / ".local/share/agent-config/overlay/skills/priv-skill").resolve()
      and not (O / ".claude/skills/alpha").exists()
      and (O / ".claude/agents/priv-agent.md").is_symlink()
      and "# Private box notes" in (O / ".claude/CLAUDE.md").read_text()
      and origin_file_of(ov_mem, "memory/workspace-dash/ov-note.md") == "from overlay host\n"
      and o_st.get("overlay_repo") == str(ov_origin) and o_st.get("overlay_head")
      and sh("git", "-C", str(O / "workspace/agent-conf-private"), "config", "core.hooksPath").stdout.strip() == ".githooks",
      "overlay merges private hosts, skills, overrides, notes, agents, memory_repo, and hooksPath", out)

# disabling overlay unlinks overlay-only skills and clears overlay status
rc, out = ac(O, "setup", "--host", "shared", "--overlay-repo", "none", "--no-schedule")
o_st2 = json.loads(ac(O, "status")[1])
check(rc == 0 and not (O / ".claude/skills/priv-skill").exists() and (O / ".claude/skills/alpha").is_symlink()
      and o_st2.get("overlay_repo") is None and o_st2.get("overlay_head") is None,
      "setup --overlay-repo none disables overlay, unlinks private skills, and clears overlay status", out)

# --- owner/repo shorthand inherits SSH, HTTPS, and SSH-alias transport; repo_identity normalises spellings ----
import importlib.machinery, importlib.util
loader = importlib.machinery.SourceFileLoader("ac_mod", str(SRC / "bin/agent-config"))
spec = importlib.util.spec_from_loader("ac_mod", loader)
ac_mod = importlib.util.module_from_spec(spec)
loader.exec_module(ac_mod)
for sample_origin, expected in (
    ("git@github.com:PastaPastaPasta/agent-conf.git", "git@github.com:PastaPastaPasta/agent-memory.git"),
    ("https://github.com/PastaPastaPasta/agent-conf.git", "https://github.com/PastaPastaPasta/agent-memory.git"),
    ("ssh://git@github.com/PastaPastaPasta/agent-conf.git", "ssh://git@github.com/PastaPastaPasta/agent-memory.git"),
    ("gh:PastaPastaPasta/agent-conf.git", "gh:PastaPastaPasta/agent-memory.git"),
):
    fake = Path(tempfile.mkdtemp(dir=T))
    sh("git", "init", "-q", str(fake))
    sh("git", "remote", "add", "origin", sample_origin, cwd=fake)
    ac_mod.LIVE, ac_mod.WORK = fake, fake
    got = ac_mod.parse_repo_spec("PastaPastaPasta/agent-memory")
    check(got == expected, f"owner/repo shorthand matches {sample_origin.split(':')[0]} transport", f"got={got!r} want={expected!r}")
check(ac_mod.repo_identity("git@github.com:PastaPastaPasta/agent-memory.git")
      == ac_mod.repo_identity("https://github.com/PastaPastaPasta/agent-memory")
      == ac_mod.repo_identity("ssh://git@github.com/PastaPastaPasta/agent-memory.git"),
      "repo_identity normalizes SSH and HTTPS spellings of the same repo")

# --- ~/workspace/agent-memory editing clone is fast-forwarded and wired to its .githooks ----------------------
push_mem(empty_mem, "chore: add pre-commit hook",
         lambda w: ((w / ".githooks").mkdir(exist_ok=True), (w / ".githooks/pre-commit").write_text("#!/bin/sh\nexit 0\n")))
sh("git", "clone", "-q", str(empty_mem), str(E / "workspace/agent-memory"))
(E / ".config/agent-config/memory-repo").write_text(str(empty_mem) + "\n")
push_mem(empty_mem, "chore(memory): remote note", lambda w: (w / "memory/workspace-dash/from-remote.md").write_text("hi\n"))
rc, out = ac(E, "sync")
check(rc == 0 and (E / "workspace/agent-memory/memory/workspace-dash/from-remote.md").exists()
      and sh("git", "-C", str(E / "workspace/agent-memory"), "config", "core.hooksPath").stdout.strip() == ".githooks",
      "clean ~/workspace/agent-memory editing clone is fast-forwarded and configures .githooks", out)

print("FAILURES:", fails)
sys.exit(1 if fails else 0)
