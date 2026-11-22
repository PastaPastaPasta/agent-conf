"""Cases for claude/scripts/git-guard.sh: 2 = blocked, 0 = allowed."""
import atexit, json, pathlib, shutil, subprocess, sys, tempfile

GUARD = pathlib.Path(__file__).resolve().parent.parent / "claude/scripts/git-guard.sh"

CASES = [
    (2, "git add -A"),
    (2, "git add ."),
    (2, "git add --all"),
    (2, "git add -u"),
    (2, "git -C repo add --all"),
    (2, "cd x && git add -A && git commit -m hi"),
    (2, "git add -- ."),
    (2, "git add -Av"),
    (2, "git add :/"),
    (2, 'git commit -am "msg"'),
    (2, "git commit -a -m msg"),
    (2, "git commit --all"),
    (0, "git add foo.txt bar/baz.py"),
    (0, "git add ./src/main.rs"),
    (0, "git add -p foo"),
    (0, 'git add src/ && git commit -m "x"'),
    (0, 'git commit -m "fix a bug"'),
    (0, "git commit --amend --no-edit"),
    (0, "git commit -m msg -S"),
    (0, "git status"),
    (0, "echo git add -A"),
    # signing
    (2, "git commit --no-gpg-sign -m msg"),
    (2, "git -C repo commit -m msg --no-gpg-sign"),
    (2, "git rebase --no-gpg-sign main"),
    (2, "git tag --no-sign v1"),
    (2, "git -c commit.gpgsign=false commit -m msg"),
    (2, "git -c commit.gpgSign=false commit -m msg"),
    (2, "git -c gpg.format=openpgp commit -m msg"),
    (2, "git config commit.gpgsign false"),
    (2, "git config --global user.signingkey ~/.ssh/other.pub"),
    (2, "git config --local gpg.format openpgp"),
    (2, "git config --unset user.signingkey"),
    (2, "git config unset commit.gpgsign"),
    (2, "git config set commit.gpgsign false"),
    (2, "GIT_CONFIG_COUNT=0 git commit -m msg"),
    (2, "export GIT_CONFIG_COUNT=0"),
    (2, "unset GIT_CONFIG_COUNT GIT_CONFIG_KEY_0"),
    (2, "env -u GIT_CONFIG_COUNT git commit -m msg"),
    (2, "GIT_CONFIG_GLOBAL=/dev/null git commit -m msg"),
    (0, "git config user.signingkey"),
    (0, "git config --get commit.gpgsign"),
    (0, "git config user.signingkey 2>/dev/null"),
    (0, "git config --get-all gpg.format"),
    (0, "git config user.name pasta"),
    (0, "git config --list"),
    (0, "git log --format='%h %G?' -3"),
    (0, "git commit -S -m msg"),
    (0, "echo $GIT_CONFIG_COUNT"),
    (0, "env | grep GIT_CONFIG_"),
    # review round 1: quoted text is not flags
    (0, 'git commit -m "fix: block --no-gpg-sign in the guard"'),
    (0, 'git commit -m "docs: explain git add -A and -u rules"'),
    (0, 'git commit -m "feat: support -a flag in parser"'),
    (0, 'git commit -m "chore: drop --all option"'),
    (0, 'git commit -m "feat: add -Wall to cflags"'),
    (0, "git commit -m \"$(cat <<'EOF'\nfeat: block git add -A and --no-gpg-sign\n\nit's done\nEOF\n)\""),
    (0, "git commit -F - <<'EOF'\nfeat: block --no-gpg-sign usage\nEOF"),
    (0, "echo GIT_CONFIG_COUNT=$GIT_CONFIG_COUNT"),
    (0, "env | grep '^GIT_CONFIG_COUNT='"),
    (0, "rg -n 'GIT_CONFIG_KEY_0=' ~/workspace/agent-config"),
    (0, "unset GIT_CONFIG_NOSYSTEM"),
    (0, 'grep -rn "unset GIT_CONFIG_" .'),
    (0, "git config --global commit.gpgsign true"),
    (0, "git -c commit.gpgsign=true commit -m x"),
    (0, "git commit -m msg 2>&1 | tail -3"),
    # review round 1: misses
    (2, "git commit -m \"$(cat <<'EOF'\nfeat: x\nEOF\n)\" --no-gpg-sign"),
    (2, "git commit \\\n  --no-gpg-sign -m msg"),
    (2, 'git -c "commit.gpgsign=false" commit -m x'),
    (2, "git -c 'commit.gpgsign=false' commit -m x"),
    (2, "git config --get commit.gpgsign && git config --global commit.gpgsign false"),
    (2, "git config --global --list; git config --global commit.gpgsign false"),
    (2, "unset GIT_DIR GIT_CONFIG_COUNT"),
    (2, "if git commit --no-gpg-sign -m x; then echo ok; fi"),
    (2, "git stage ."),
    (2, 'git -C "my repo" add -A'),
    (2, "timeout 60 git commit --no-gpg-sign -m x"),
    (2, "git config --global --remove-section gpg"),
    (2, "echo $(git add -A)"),
    (2, "env GIT_CONFIG_COUNT=0 git commit -m x"),
]

# Rule 3 runs against throwaway checkouts. Remote names differ by machine, so
# each layout is covered: "plat" = laptop/agentbox (origin = dashpay, fork =
# PastaPastaPasta), "plat2" = origin is the fork and upstream is dashpay.
TMP = pathlib.Path(tempfile.mkdtemp())
atexit.register(shutil.rmtree, TMP, True)
DASHPAY, FORK = "git@github.com:dashpay/platform.git", "git@github.com:PastaPastaPasta/platform.git"
REPOS = {  # name: (HEAD branch, {remote: url}, branch's tracking remote)
    "plat": ("feat/x", {"origin": DASHPAY, "fork": FORK}, "fork"),
    "plat-y": ("feat/y", {"origin": DASHPAY, "fork": FORK}, "origin"),
    "plat2": ("feat/z", {"origin": "https://github.com/PastaPastaPasta/platform", "upstream": DASHPAY}, None),
    "plat3": ("feat/w", {"origin": DASHPAY, "fork": "ssh://git@ssh.github.com:443/PastaPastaPasta/platform.git",
                         "fork2": "git@github-agent:PastaPastaPasta/platform.git"}, None),
    "other": ("main", {"origin": "git@github.com:someone/platform.git"}, None),
}
for name, (branch, remotes, track) in REPOS.items():
    d = TMP / name
    subprocess.run(["git", "init", "-q", "-b", branch, str(d)], check=True)
    for r, url in remotes.items():
        subprocess.run(["git", "-C", str(d), "remote", "add", r, url], check=True)
    if track:
        subprocess.run(["git", "-C", str(d), "config", f"branch.{branch}.remote", track], check=True)
P = TMP / "plat"

FORK_CASES = [  # (want, command, cwd)
    (2, "git push fork feat/x", "plat"),
    (2, "git push", "plat"),
    (2, "git push -u fork HEAD", "plat"),
    (2, "git push --force-with-lease=feat/x:abc fork feat/x", "plat"),
    (2, "git push https://github.com/PastaPastaPasta/platform.git feat/x", "plat"),
    (2, "gh pr create --repo dashpay/platform --head PastaPastaPasta:feat/x --base v5.1-dev", "plat"),
    (2, "gh pr create --repo dashpay/platform --base v5.1-dev --body-file /tmp/b.md", "plat"),
    (2, "gh pr create --fill", "plat"),
    (2, "gh pr new -R dashpay/platform -H pastapastapasta:feat/x", "plat"),
    (2, "gh pr create --repo=https://github.com/dashpay/platform --head=PastaPastaPasta:feat/x", "plat"),
    (2, "GH_REPO=dashpay/platform gh pr create --head PastaPastaPasta:feat/x", "other"),
    (2, 'gh pr create --repo dashpay/platform --head "PastaPastaPasta:feat/x" --title "fix: x"', "other"),
    (2, "gh api repos/dashpay/platform/pulls -f title=x -f head=PastaPastaPasta:feat/x -f base=v5.1-dev", "other"),
    (2, f"cd {P} && git push fork feat/x", "other"),
    (2, f"git -C {P} push fork feat/x", "other"),
    (2, "git fetch fork && git push fork feat/x", "plat"),
    (2, "git push origin feat/z", "plat2"),
    (2, "git push", "plat2"),
    (2, f"(cd {P} && git push fork feat/x)", "other"),
    (2, f"cd {P} 2>/dev/null && git push fork feat/x", "other"),
    (2, f"pushd {P} >/dev/null && git push fork feat/x", "other"),
    (2, 'gh pr create --repo dashpay/platform --head "PastaPastaPasta:$(git branch --show-current)" --title x', "plat"),
    (2, "gh pr create --repo dashpay/platform -H=PastaPastaPasta:feat/x", "plat"),
    (2, "git push fork feat/w", "plat3"),
    (2, "git push fork2 feat/w", "plat3"),
    (2, "PLATFORM_FORK_OK=1 git push fork pin && git push fork feat/x", "plat"),
    (2, "git push --repo fork feat/x", "plat"),
    (0, "git push origin feat/x", "plat"),
    (0, "git push -u origin HEAD", "plat"),
    (0, "PLATFORM_FORK_OK=1 git push fork feat/x", "plat"),
    (0, "git push fork --delete feat/x", "plat"),
    (0, "git push fork :feat/x :feat/old", "plat"),
    (0, "gh pr create --repo dashpay/platform --head feat/x --base v5.1-dev", "plat"),
    (0, "gh pr create --repo dashpay/platform --head dashpay:feat/x", "plat"),
    (0, "gh pr create --repo dashpay/dash --head PastaPastaPasta:feat/x", "plat"),
    (0, "gh pr create --repo PastaPastaPasta/platform --head feat/x", "plat"),
    (0, "gh api repos/dashpay/platform/pulls -f head=feat/x -f base=v5.1-dev", "plat"),
    (0, "gh api repos/dashpay/platform/pulls/5611", "plat"),
    (0, "gh pr create --fill", "plat-y"),
    (0, "git push", "plat-y"),
    (0, "git push upstream feat/z", "plat2"),
    (0, "git push origin main", "other"),
    (0, "gh pr checks 5611 --repo dashpay/platform", "plat"),
    (0, "git fetch fork", "plat"),
    (0, "echo git push fork feat/x", "plat"),
    (0, 'git commit -m "docs: never git push fork"', "plat"),
    (0, "git push fork feat/x", "other"),
    (0, "git push fork feat/x --dry-run", "plat"),
    (0, "gh api repos/dashpay/platform/pulls -X GET -f head=PastaPastaPasta:feat/x -f state=all", "plat"),
    (0, "git push https://github.com/HashEngineering/platform.git feat/x", "plat"),
]

failed = 0
def check(want, payload, label):
    global failed
    got = subprocess.run([str(GUARD)], input=json.dumps(payload), text=True, capture_output=True).returncode
    if got != want:
        print(f"FAIL want={want} got={got}: {label}")
        failed += 1

for want, cmd in CASES:
    check(want, {"tool_input": {"command": cmd}}, cmd)
for want, cmd, cwd in FORK_CASES:
    check(want, {"tool_input": {"command": cmd}, "cwd": str(TMP / cwd)}, f"[{cwd}] {cmd}")
# Codex shapes: argv-array command, and exec_command's cmd + workdir.
check(2, {"tool_input": {"command": ["bash", "-lc", "git push fork feat/x"]}, "cwd": str(P)}, "codex argv")
check(2, {"tool_input": {"cmd": "git push fork feat/x", "workdir": str(P)}, "cwd": "/"}, "codex exec_command")
check(2, {"tool_input": {"command": ["git", "push", "fork", "feat/x"]}, "cwd": str(P)}, "codex git argv")
check(0, {"tool_input": {"command": ["git", "push", "origin", "feat/x"]}, "cwd": str(P)}, "codex argv ok")
check(0, {"tool_input": {"command": ["apply_patch", "*** Begin Patch\n git add -A\n git push fork feat/x\n"]}, "cwd": str(P)}, "codex apply_patch")
total = len(CASES) + len(FORK_CASES) + 5
print(f"git-guard: {total - failed}/{total} cases pass")
sys.exit(1 if failed else 0)
