"""Cases for claude/scripts/rm-safety-allow.py: ALLOW = prints an allow decision, ASK = not approved (prints
nothing, or a deny when the command has a delete). EXACT cases tell a deny from a prompt."""
import atexit, json, os, pathlib, shutil, subprocess, sys, tempfile

REPO = pathlib.Path(__file__).resolve().parent.parent
HOOK = REPO / "claude/scripts/rm-safety-allow.py"
HOME = str(pathlib.Path.home())
ENV = {k: v for k, v in os.environ.items() if k not in ("CDPATH", "GIT_DIR", "GIT_WORK_TREE")} | {"TMPDIR": "/tmp"}
NX = "/tmp/rm-safety-test-missing"  # a scratch dir that doesn't exist
ALLOW, ASK, DENY = "allow", "ask", "deny"

# The prompts T3 recorded on agentbox and strixbox in the week to 2026-10-30. Full text where a transcript
# kept it; otherwise the recorded text with its `…` truncations, plus a plausible complete form.
GATE_D52 = r"""set -e; GF=/work/scratch/gate-fast; cp -p $GF/gate.sh $GF/gate.sh.pre-d52; cp -p $GF/gate.sh $GF/gate.sh.new
python3 - <<'EOF'
p='/work/scratch/gate-fast/gate.sh.new'; s=open(p).read()
anchor='echo "GATE EXIT $rc"\nexit $rc\n'
assert s.count(anchor)==1
new='''# Low disk (D52, manager 10-26): under GATE_LOWDISK_GIB (260) free on /work, drop this slot's secondary
# targets after the run (we still hold the slot lock); `target` stays as the warm cache. target-aux goes only
# under GATE_LOWDISK_AUX_GIB (220): its cold oracle-diff rebuild is the lane most likely to break the budget.
lowdisk_free=$(df --output=avail -BG /work | tail -1 | tr -dc 0-9)
if [ -n "$lowdisk_free" ] && [ "$lowdisk_free" -lt "${GATE_LOWDISK_GIB:-260}" ]; then
    lowdisk_drop=(target-clippy target-rdashd target-planted target-pure)
    [ "$lowdisk_free" -lt "${GATE_LOWDISK_AUX_GIB:-220}" ] && lowdisk_drop+=(target-aux)
    lowdisk_done=()
    for t in "${lowdisk_drop[@]}"; do [ -d "$SLOT_DIR/$t" ] && rm -rf "$SLOT_DIR/$t" && lowdisk_done+=("$t"); done
    echo "lowdisk: /work ${lowdisk_free}G free (< ${GATE_LOWDISK_GIB:-260}G): dropped slot $SLOT's ${lowdisk_done[*]:-nothing}; now $(df --output=avail -BG /work | tail -1 | tr -d ' ') free"
fi
'''
s=s.replace(anchor,new+anchor); open(p,'w').write(s)
EOF
bash -n $GF/gate.sh.new && echo syntax-ok
# exercise the block alone against a fake slot
T=/work/scratch/sb1-pfgc/d52test; rm -rf $T; mkdir -p $T/slot/{target,target-aux,target-clippy,target-rdashd,target-planted,target-pure}
blk=$(sed -n '/^# Low disk (D52/,/^fi$/p' $GF/gate.sh.new)
for env in "GATE_LOWDISK_GIB=1" "GATE_LOWDISK_GIB=99999 GATE_LOWDISK_AUX_GIB=1" "GATE_LOWDISK_GIB=99999 GATE_LOWDISK_AUX_GIB=99999"; do
  mkdir -p $T/slot/{target-aux,target-clippy,target-rdashd,target-planted,target-pure}
  env $env SLOT_DIR=$T/slot SLOT=x bash -c "$blk"; echo "  [$env] left: $(ls $T/slot | tr '\n' ' ')"
done; rm -rf $T"""

RP1A = r"""cd ~/workspace/rdc-wt/rp1a-1b && T=$PWD/target/debug; rm -f /work/scratch/rp1a/fc5.rc; systemd-run --user --unit=rp1a-1b-fc5 --same-dir --collect bash -c "F='python3 contrib/node/func-compat/func-compat.py run --core /work/scratch/rp1a/core-clone --work /work/scratch/rp1a/fc-work --pin v24.0 --rdashd $T/rdashd --rdash-cli $T/rdash-cli -j 4'; \$F --phase M2 --out /work/scratch/rp1a/fc5-m2 > /work/scratch/rp1a/fc5-m2.log 2>&1; a=\$?; \$F --phase M3 --out /work/scratch/rp1a/fc5-m3 rpc_generate.py mining_basic.py rpc_invalidateblock.py rpc_preciousblock.py > /work/scratch/rp1a/fc5-m3.log 2>&1; b=\$?; echo \$a \$b > /work/scratch/rp1a/fc5.rc"; timeout 590 bash -c 'until [ -f /work/scratch/rp1a/fc5.rc ]; do sleep 5; done'; cat /work/scratch/rp1a/fc5.rc; grep -hE "^\| [0-9]|ratchet|complete|partial" /work/scratch/rp1a/fc5-m2.log /work/scratch/rp1a/fc5-m3.log"""

STDIN_PROBE = r"""cd /work/scratch/ci-stage2/reviews/opus-r2-tmp && rm -rf stdin-probe && cargo new -q --vcs none stdin-probe && cd stdin-probe && printf 'fn main(){println!("cargo:rerun-if-changed=build.rs");}\n' > build.rs && CARGO_TARGET_DIR=$PWD/target bash -c 'n=0; while read -r -a cmd; do [ ${#cmd[@]} -gt 0 ] || continue; n=$((n+1)); rc=0; "${cmd[@]}" --message-format=json-render-diagnostics > step$n.json || rc=$?; echo "ran $n: ${cmd[1]} rc=$rc"; done <<<"cargo check --keep-going --all-targets
cargo build
"' 2>&1 | grep ran"""

OBSERVED = [
    # "This shell -c script runs rm and could not be checked"
    # As recorded, `…` sits where systemd-run's command would be, so bash -c is only an argument: prompt.
    (ASK, "systemd-run --user --unit=gv-extract-rest4 … bash -c 'rm -f /work/scratch/grovedb-verified/rest-build.log /work/scratch/grovedb-verified/rest-ax.log …'"),
    (ALLOW, "systemd-run --user --unit=gv-extract-rest4 --same-dir --collect bash -c 'rm -f /work/scratch/grovedb-verified/rest-build.log /work/scratch/grovedb-verified/rest-ax.log; cd /work/scratch/grovedb-verified && ./extract.sh rest > rest-build.log 2>&1'"),
    # SLOT_DIR is only set later, by `env ... bash -c "$blk"`, and $blk is an opaque script: stays a prompt.
    (ASK, GATE_D52),
    # cp, outside the allowlist, runs before a delete through a dir it could have swapped for a symlink.
    (ASK, "set -e; GF=/work/scratch/gate-fast; cp -p $GF/gate.sh $GF/gate.sh.pre-d52; T=/work/scratch/sb1-pfgc/d52test; rm -rf $T; mkdir -p $T/slot; rm -rf $T"),
    # $F runs a command named by a variable, and bash -c gets $PWD, unknown, spliced into its script.
    (ASK, RP1A),
    # "${cmd[@]}" runs a command named by an unknown expansion: stays a prompt.
    (ASK, STDIN_PROBE),
    # "Dangerous rm operation on statically-unresolvable target: <session cwd>/*"
    (ALLOW, "cd /work/scratch/rambench && sudo rm -rf disk/* 2>/dev/null; rm -rf disk/*; systemd-run --user --unit=rambench --same-dir --collect ./bench.sh"),
    (ASK, "mkdir -p /work/tmp/tarcmp && cd /work/tmp/tarcmp && rm -rf * && npm pack …"),  # npm and tar aren't allowed
    (ASK, "mkdir -p /work/tmp/tarcmp && cd /work/tmp/tarcmp && rm -rf * && npm pack @dashevo/evo-sdk@latest && tar tzf *.tgz | sort > a.txt"),
    (ALLOW, "cd /work/scratch/dn-review && rm -f * && python3 -I - <<'EOF' …"),
    (ALLOW, "cd /work/scratch/dn-review && rm -f * && python3 -I - <<'EOF'\nimport json, pathlib\nprint(json.dumps(sorted(p.name for p in pathlib.Path('.').iterdir())))\nEOF"),
    # "Dangerous rm operation not ruled out": with no delete there is nothing for the hook to vouch for.
    (ASK, 'git worktree add -q --detach /work/scratch/bp-rc5-develop upstream/develop …; for c in … ; do … $(cd $wt && echo "$p" | git apply --check … || …)'),  # `…` reads as an unknown program given $( ) output
    (ASK, 'git worktree add -q --detach /work/scratch/bp-rc5-develop upstream/develop; wt=/work/scratch/bp-rc5-develop; for c in a1b2 c3d4; do p=$(git show $c); echo "$c $(cd $wt && echo "$p" | git apply --check - 2>&1 || echo FAIL)"; done'),
]

CASES = OBSERVED + [
    # scratch roots
    (ALLOW, "rm -rf /work/scratch/foo"),
    (ALLOW, "rm -rf /work/tmp/a/b/c"),
    (ALLOW, "rm -f /tmp/x.log /var/tmp/y"),
    (ALLOW, 'rm -rf "$TMPDIR/foo" ${TMPDIR}/bar'),
    (ALLOW, "rm -rf /work/scratch/x/*"),
    (ALLOW, "rmdir /work/scratch/empty"),
    (ALLOW, "unlink /tmp/sock"),
    (ALLOW, "shred -u -n 3 /work/scratch/k.pem"),
    (ALLOW, "find /work/scratch/build -name '*.o' -delete"),
    (ALLOW, "find /work/tmp/x -type f -exec rm -f {} +"),
    (ALLOW, "git -C /work/scratch/repo clean -fdx"),
    (ALLOW, "rm -rf -- /work/scratch/a"),
    (ALLOW, "/bin/rm -rf /work/scratch/a"),
    (ALLOW, "\\rm -rf /work/scratch/a"),
    (ALLOW, "rm -rf /work/scratch/a 2>/dev/null || true"),
    (ALLOW, "timeout 30 rm -rf /work/scratch/a"),
    (ALLOW, "sudo rm -rf /work/scratch/docker-out"),
    (ALLOW, "sudo -u root rm -rf /work/scratch/docker-out"),
    (ALLOW, "nice -n 10 ionice -c 3 rm -rf /work/scratch/big"),
    (ASK, "echo $(rm -f /tmp/x; echo done)"),
    (ASK, "x=`rm -f /tmp/y`"),
    (ALLOW, "bash -c 'rm -rf /work/scratch/a' && sh -c \"rm -f /tmp/b\""),
    (ASK, "bash -lc 'cd /work/scratch/x && rm -rf *'"),
    (ALLOW, "bash <<'EOF'\nrm -rf /work/scratch/hd\nEOF"),
    (ASK, "cat > /work/scratch/run.sh <<EOF\necho rm-free text\nEOF"),
    # relative paths
    (ALLOW, "rm -rf build target/debug"),
    (ALLOW, "rm -f ./out.log"),
    (ASK, "rm -rf node_modules && npm ci"),
    (ALLOW, "cd /work/scratch/x && rm -rf build"),
    # globs after a cd into scratch
    (ALLOW, "cd /work/scratch/x && rm -rf *"),
    (ALLOW, "cd /work/scratch/x && rm -rf ./*"),
    (ALLOW, "cd /work/scratch/x && rm -f *.log"),
    (ALLOW, "cd /work/scratch/x || exit 1; rm -rf *"),
    (ASK, "set -e; cd /work/scratch/x; rm -rf *"),  # Claude Code's eval in an && list ignores set -e
    (ALLOW, "cd /work/scratch/x && cd sub && rm -rf *"),
    (ALLOW, "cd /work/scratch/x && find . -name '*.tmp' -delete"),
    (ALLOW, "cd /work/scratch/repo && git clean -fdx"),
    (ALLOW, "cd $TMPDIR/foo && rm -rf *"),
    # variables
    (ALLOW, "D=/work/scratch/foo; rm -rf $D"),
    (ALLOW, 'D=/work/scratch/foo; rm -rf "$D/sub" "${D}/x"'),
    (ALLOW, "GF=/work/scratch/gf; SLOT_DIR=$GF/slots; for t in a b; do rm -rf \"$SLOT_DIR/$t\"; done"),
    (ALLOW, "T=$(mktemp -d); trap 'true' EXIT; rm -rf $T"),
    (ALLOW, 'T="$(mktemp -d /work/scratch/x.XXXX)" && rm -rf "$T"/*'),
    (ASK, 'set -e; T=$(mktemp -d); rm -rf "$T"/*'),
    (ALLOW, 'T=$(mktemp -d) || exit 1; rm -rf "$T"/x'),
    (ALLOW, "T=$(mktemp -d) || exit 1; trap 'rm -rf \"$T\"' EXIT; cd \"$T\" && touch a"),
    (ALLOW, 'T=$(mktemp -d); rm -rf "$T"'),  # an empty $T is a no-op
    (ASK, 'export T=$(mktemp -d); rm -rf "$T"'),  # exported uppercase names aren't allowed
    (ALLOW, "mkdir -p /tmp/x/{a,b} && echo $UNSET && rm -rf /tmp/x/a"),
    (ASK, "nice -n 5 cargo build --release && rm -rf /work/scratch/rm-safety-test-target"),
    (ALLOW, "cat > /tmp/x/notes.txt <<'E'\nhello\nE\nrm -f /tmp/x/old.txt"),
    (ALLOW, "./build.sh && rm -rf /tmp/rm-safety-test-out"),
    (ALLOW, "/bin/rm -rf /tmp/x/out && /usr/bin/ls /tmp/x"),
    (ALLOW, "trap -- 'rm -rf /tmp/x/a' EXIT; sleep 1"),
    (ALLOW, "true && { cd /tmp/x && rm -rf *; }"),
    (ALLOW, "if test -d /tmp/x; then rm -rf /tmp/x/a; elif true; then rm -rf /tmp/x/b; else :; fi"),
    (ALLOW, "cd /tmp/x && git clean -fdx"),
    (ALLOW, "n=3; [[ $n -gt 1 ]] && rm -f /tmp/x/a"),
    (ALLOW, "true\nrm -f /tmp/rm-safety-ok"),
    (ALLOW, "export d=/work/scratch/e; bash -c 'rm -rf $d/x'"),
    (ALLOW, "cat <<'E'\nline\\\nE\nrm -f /tmp/rm-safety-ok"),  # a quoted heredoc doesn't join lines
    (ALLOW, "T=/work/scratch/x/t; rm -rf $T/out"),
    (ALLOW, "d=/work/scratch/e bash -c 'rm -rf $d/x'"),
    (ALLOW, 'export t=$(mktemp -d); rm -rf "$t"'),
    (ALLOW, "cd /work/scratch/x || exit 1; rm -rf *"),
    (ALLOW, "find /work/tmp/x -name '*.o' -type f -delete -print"),
    (ALLOW, "cd /work/scratch/x && rm -rf out && ./build.sh"),
    (ALLOW, "/usr/bin/rm -rf /work/scratch/x/d && /bin/ls /work/scratch/x"),  # the delete the round-3 cases below end with
    (ALLOW, "rm -rf /work/scratch/x/d/* && python3 -c 1"),
    (ALLOW, "python3 -c 1 && rm -rf /tmp/rm-safety-ok"),
    (ASK, "rm -f /tmp/rm-safety-ok && sort -u -k2 /tmp/x/a | head"),  # a direct child of a scratch root: no link to plant
    (ALLOW, "systemd-run --user --wait bash -c 'rm -rf /work/scratch/x/d/*'; python3 -c 1"),
    (ASK, "sudo -n rm -rf /work/scratch/x/d && cargo build && npm pack && make -C /work/scratch/x all"),
    (ASK, "cd /work/scratch/x && rm -rf out && git status --short && tar czf out.tgz src"),
    (ALLOW, "python3 -I - <<'E'\nprint(1)\nE\nrm -f /tmp/rm-safety-test-a"),
    (ASK, "./build.sh && rm -rf /tmp/rm-safety-test-missing/out"),  # build.sh may have made that dir a symlink
    (ALLOW, 'for f in /work/scratch/x/a /work/scratch/x/b; do rm -f "$f"; done'),
    (ALLOW, 'for t in a b-1 c.log; do rm -rf "/work/scratch/slots/$t"; done'),
    (ALLOW, 'rm -rf "${TMPDIR:-/tmp}/foo"'),
    (ALLOW, "bash <<'EOF'\nD=/work/scratch/hd\nrm -rf $D/x\nEOF"),
    (ALLOW, "cd /work/scratch/x && pushd sub && rm -rf *"),
    (ASK, "export D=/work/scratch/e; bash -c 'rm -rf $D/x'"),
    (ALLOW, "D=/work/scratch/e; bash -c \"rm -rf $D/x\""),
    (ASK, "D=/work/scratch/e bash -c 'rm -rf $D/x'"),
    (ASK, "eval 'rm -rf /work/scratch/ev'"),
    # no delete operation at all
    (ASK, "ls -la"),
    (ASK, "cargo build 2>&1 | tail -3"),
    (ASK, "echo $(date) > /work/scratch/now"),

    # never approved (the brief's negative set first)
    (ASK, "rm -rf ~"),
    (ASK, "rm -rf /"),
    (ASK, 'rm -rf "$HOME"'),
    (ASK, "rm -rf /work/home/agent"),
    (ASK, "rm -rf .."),
    (ASK, "rm -rf *"),
    (ASK, "cd ~ && rm -rf *"),
    (ASK, 'rm -rf "$UNSET/"'),
    (ASK, "find / -delete"),
    (ASK, "bash -c 'rm -rf ~'"),
    (ASK, "rm -rf /*"),
    (ASK, "rm -rf ~/"),
    (ASK, "rm -rf $HOME"),
    (ASK, "rm -rf ${HOME}/x"),
    (ASK, "rm -rf ~/workspace/foo"),
    (ASK, "rm -rf /work"),
    (ASK, "rm -rf /work/home"),
    (ASK, "rm -rf /work/home/agent/workspace"),
    (ASK, "rm -rf /work/home/agent/workspace/platform"),
    (ASK, "rm -rf .git"),
    (ASK, "rm -rf repo/.git"),
    (ASK, "rm -rf /work/scratch/repo/.git"),
    (ASK, "rm -rf ."),
    (ASK, "rm -rf ./*"),
    (ASK, "rm -rf .*"),
    (ASK, "rm -rf ../x"),
    (ASK, "rm -rf a/../../x"),
    (ASK, "rm -rf /work/scratch"),
    (ASK, "rm -rf /work/scratch/"),
    (ASK, "rm -rf /work/scratch/*"),
    (ASK, "rm -rf /work/scratch/.."),
    (ASK, "rm -rf /work/scratch/../home"),
    (ASK, "rm -rf /tmp"),
    (ASK, "rm -rf /tmp/*"),
    (ASK, "rm -rf /work/scratchy/x"),
    (ASK, "rm -rf /etc/foo"),
    (ASK, 'rm -rf "$TMPDIR"'),
    (ASK, 'rm -rf "$TMPDIR/"'),
    (ASK, "rm -rf $TMPDIR/*"),
    (ASK, "rm -rf /work/scratch/$X"),
    (ASK, "rm -rf $X"),
    (ASK, "rm -rf $PWD/x"),
    (ASK, "rm -rf $(pwd)"),
    (ASK, "rm -rf `pwd`/x"),
    (ASK, "rm -rf $1/x"),
    (ASK, "rm -rf ${D:-/}"),
    (ASK, "rm -f *.log"),
    (ASK, "rm -rf dir/*"),
    (ASK, "cd /work/scratch/x; rm -rf *"),
    (ASK, "cd /work/scratch/x && true; rm -rf *"),
    (ASK, "cd /work/scratch/x && true || rm -rf *"),
    (ASK, "cd /work/scratch/x || true; rm -rf *"),
    (ASK, "if cd /work/scratch/x; then :; fi; set -e; rm -rf *"),
    (ASK, "cd /work/scratch/x | true && rm -rf *"),
    (ASK, "(cd /work/scratch/x) && rm -rf *"),
    (ASK, "$(cd /work/scratch/x) && rm -rf *"),
    (ASK, "cd /work/scratch && rm -rf *"),
    (ASK, "cd ~ && rm -rf workspace"),
    (ASK, "cd /work/home/agent && rm -rf workspace"),
    (ASK, "cd $SOMEWHERE && rm -rf build"),
    (ASK, "cd && rm -rf build"),
    (ASK, "cd - && rm -rf build"),
    (ASK, "cd /work/scratch/x && for d in a b; do rm -rf *; cd ~; done"),
    (ASK, "cd /work/scratch/x && f() { cd ~; }; f; rm -rf build"),
    (ASK, "cd /work/scratch/x && source env.sh && rm -rf *"),
    (ASK, "systemd-run --user bash -c 'rm -rf build'"),
    (ASK, "systemd-run --user --working-directory=/work/home/agent bash -c 'rm -rf build'"),
    (ASK, "env -C ~ rm -rf build"),
    (ASK, "sudo -D /work/home/agent rm -rf build"),
    (ASK, "git -C ~ clean -fdx"),
    (ASK, "git clean -fdx"),
    (ASK, "git --work-tree=/work/home/agent clean -fdx /work/scratch/a"),
    (ASK, "find . -delete"),
    (ASK, "find -delete"),
    (ASK, "find ~ -name '*.o' -delete"),
    (ASK, "find /work/scratch/x -exec sh -c 'rm -rf ~' \\;"),
    (ASK, "find /work/scratch/x | xargs rm -rf"),
    (ASK, "ls | xargs rm"),
    (ASK, "echo rm -rf ~"),
    (ASK, "ssh box 'rm -rf ~'"),
    (ASK, "python3 -c \"import os; os.system('rm -rf ~')\""),
    (ASK, "rm -rf \"$(cat list)\""),
    (ASK, "rm -rf ~/$(echo x)"),
    (ASK, "D=$(pwd); rm -rf \"$D\""),
    (ASK, "D=/work/scratch/a; D=~; rm -rf $D"),
    (ASK, "D=/work/scratch/a; read D; rm -rf $D"),
    (ASK, "D=/work/scratch/a; for D in ~; do :; done; rm -rf $D"),
    (ASK, "D=/work/scratch/a; unset D; rm -rf $D/x"),
    (ASK, "D=/work/scratch/a | true; rm -rf $D/x"),
    (ASK, "T=/work/scratch/a; for i in 1 2; do rm -rf $T; T=~; done"),
    (ASK, "GF=/work/scratch/x; bash -c 'rm -rf $GF/y'"),
    (ASK, "export D=/work/scratch/x; sudo bash -c 'rm -rf $D/y'"),
    (ASK, "sudo bash -c 'rm -rf $TMPDIR/y'"),
    (ASK, "bash -c \"$SCRIPT\""),
    (ASK, "bash -c \"$(cat script.sh)\""),
    (ASK, "env $X bash -c 'rm -rf /work/scratch/a'"),
    (ASK, "env -S 'rm -rf ~'"),
    (ASK, "R=rm; $R -rf /work/scratch/a"),
    (ASK, "eval \"$CMD\""),
    (ASK, "eval 'rm -rf ~'"),
    (ASK, "x=$(rm -rf ~)"),
    (ASK, "echo `rm -rf ~`"),
    (ASK, "cat <(rm -rf ~)"),
    (ASK, "cat <<EOF\n$(rm -rf ~)\nEOF"),
    (ASK, "bash <<'EOF'\nrm -rf ~\nEOF"),
    (ASK, "bash <<'EOF'\nrm -rf \\\n  ~\nEOF"),
    (ASK, "bash <<< 'rm -rf ~'"),
    (ASK, "rm -rf \\\n  ~"),
    (ASK, "rm -rf /work/scratch/a ~"),
    (ASK, "rmdir ~/x"),
    (ASK, "unlink /etc/passwd"),
    (ASK, "shred -u ~/.ssh/id_ed25519"),
    (ASK, "rm -rf 'unterminated"),
    (ASK, "case $x in a) rm -rf /work/scratch/a;; esac"),
    (ASK, "rm -rf /work/scratch/{..,x}/y"),
    (ASK, "rm -rf /work/scratch/x\x01"),
    # word splitting, brace expansion, globs carried in values
    (ASK, 'D="/work/scratch/a /"; rm -rf $D'),
    (ALLOW, 'D="/work/scratch/a /"; rm -rf "$D"'),
    (ASK, "D='/work/scratch/*'; rm -rf $D"),
    (ALLOW, "D='/work/scratch/x/*'; rm -rf $D"),
    (ASK, "rm -rf /work/scratch/{a,}"),
    (ASK, "rm -rf /work/scratch/x/{a,b}"),  # brace expansion in targets is not modeled
    (ASK, "rm -rf {a,..}"),
    (ASK, "rm -rf /work/scratch/x/.*"),
    (ASK, "IFS=x; rm -rf /work/scratch/x"),
    (ASK, "CDPATH=/work/home/agent; cd /work/scratch/x && cd workspace && rm -rf *"),
    (ASK, "find -L /work/scratch/x -delete"),
    (ASK, "find /work/scratch/x -follow -delete"),
] + [(ASK, cmd) for cmd in [
    # command names the hook can't read
    r"$'\x72m' -rf ~", "$(printf r)m -rf ~", "${RM:-rm} -rf ~/workspace", "{rm,-rf,~}", "flock /tmp/l {rm,-rf,~}",
    r"eval $'\x72m -rf ~'", r"bash -c $'\x72m -rf ~'", 'bash -c "$(echo r)m -rf ~"', 'bash -c "$X; true"',
    'eval "$CMD" x', 'trap "$(echo r)m -rf ~" EXIT', "cp /usr/bin/r[m] /tmp/x/d && /tmp/x/d -rf ~",
    # brace expansion and $'...' in targets
    "rm -rf /tmp/x/{.,}./{.,}./work/home/agent", "cd /tmp/x && rm -rf {a,~}", "cd /tmp/x && rm -rf {a,/work/home/agent}",
    r"rm -rf $'\x2f'work/home/agent", r"rm -rf $'\057work/home/agent'",
    # unknown expansions anywhere in a target
    "rm -rf /tmp/x/$(echo ../../work/home/agent)", "rm -rf /work/scratch/a/`echo ../../home/agent`",
    "rm -rf foo/$(echo ../..)", "rm -rf foo/$x", 'rm -rf foo/"$@"', 'rm -rf "/tmp/x/$UNSET"',
    "cd /tmp/x/$(echo ../../work/home/agent) && rm -rf *",
    # code the walker must not skip
    "f() ( rm -rf ~ ); f", "a=($(rm -rf ~))", "(true) > >(rm -rf ~)", "(bash) <<'E'\nrm -rf ~\nE",
    "bash <<'E'\nx=r\n${x}m -rf ~\nE", "bash <<'E'\necho \"\n\"; rm -rf ~ #\"\nE", "cat <<E\n$(r\\m -rf ~)\nE",
    "cd /tmp/x && bash <<'E'\ncd /work/home/agent\nrm -rf *\nE",
    "x=/tmp/a; bash <<'E'\nx=/work/home/agent\nrm -rf $x/workspace\nE",
    # lexer desyncs
    "echo $((r\\m -rf ~) )", 'echo $(("r"m -rf ~) )', "export a=${x:-'}'} ; rm -rf ~ #'", "cd ${x:-'}'} ; rm -rf ~ #'",
    # untracked ways to set a variable
    "y=; : ${y:=/work/home/agent/}; rm -rf ${y}workspace", 'declare -n d=HOME; rm -rf "$d"/workspace',
    "x=foo; x[0]=/work/home/agent; rm -rf $x/workspace",
    # conditional assignments and cds
    'false && x=/tmp/a; rm -rf "$x/work"', 'if false; then x=/tmp/a; fi; rm -rf "$x"/*', 'x=$(mktemp -d); rm -rf "$x"/*',
    "if false; then cd /tmp/x || exit; fi; rm -rf *", "set -e; if false; then cd /tmp/x; fi; rm -rf *",
    "set -e; false && cd /tmp/x; rm -rf *", "true || cd /tmp/x || exit; rm -rf *", "true || cd /tmp/x && rm -rf *",
    "set -e; if true; cd /tmp/nope; then rm -rf *; fi", "set -e; (cd /tmp/nope; rm -rf *) || true",
    "set -e; { cd /tmp/nope; rm -rf *; } || true",
    "cd /tmp/nope || return; rm -rf *", "cd /tmp/nope || exit & rm -rf *", "cd /tmp/nope || exit | cat; rm -rf *",
    "set -- -e; cd /tmp/nope; rm -rf *", "set -e; set +o errexit; cd /tmp/nope; rm -rf *",
    # cd and wrapper parsing
    "cd /tmp/x && cd -- /work/home/agent && rm -rf *", "cd /tmp/x && cd -Pe /work/home/agent && rm -rf *",
    "pushd /tmp/x && pushd +1 && rm -rf *", "cd /tmp/x && CDPATH=/work/home/agent cd workspace && rm -rf *",
    "cd /tmp/x && env -C/work/home/agent rm -rf *", "cd /tmp/x && sudo -i rm -rf *",
    'nice export y=/tmp/a; rm -rf "$y"/work', "nice set -e; cd /tmp/nope; rm -rf *", "nice cd /tmp/x && rm -rf *",
    "env cd /tmp/x && rm -rf *",
    # find
    r"find /tmp/x -maxdepth 0 -exec rm -rf /work/home/agent \;", r"find foo -exec rm -rf {}/../.. \;",
    "cd /tmp/x && find -- /work/home/agent -delete", "find -H /tmp/x/link -name '*.log' -delete",
    # git
    "git -c alias.x='!rm -rf ~' x", "git -c core.worktree=/work/home/agent clean -ffdx :/",
    "GIT_DIR=/tmp/x/.git GIT_WORK_TREE=/work/home/agent git clean -ffdx :/", "cd /tmp/x && git clean -fdx :/",
    "cd /tmp/x && git clean -fdx ':!keep'", "git clean -fdx '*'", "git clean -fdx -enx",
    # symlinks the command itself creates
    "ln -s /work/home/agent l && rm -rf l/", "ln -s .git g && rm -rf g/",
    f"mkdir -p {NX} && ln -s /work/home/agent {NX}/l && rm -rf {NX}/l/",
    f"mkdir -p {NX} && cd {NX} && ln -s ~ l && rm -rf l/*",
    # aliases and shells reading stdin
    "alias x=rm\nx -rf ~", "shopt -s expand_aliases\nalias cd=true\ncd /tmp/x && rm -rf *",
    "printf '%s' \"$(printf r)m -rf ~\" | bash", 'source /dev/stdin <<< "$(echo r)m -rf ~"',
    # round 2: programs that may run their arguments, given unknown or brace-expanded ones
    "taskset 1 ${x:-rm} -rf ~", "strace -f $(printf r)m -rf ~", "xargs {r,}m -rf <<< ~", "nice -n 1 ${q:-rm} -rf ~",
    "taskset 1 $(printf r)m -rf ~", "timeout 5 {r,}m -rf ~", "watch -n1 rm -rf ~",
    # functions, other shells, user switches
    "f() { ${q:-rm} -rf ~; }; f", "function f { rm -rf ~; }; f", "zsh -c 'rm -rf ~'", "ksh -c 'rm -rf ~'",
    "su -c 'rm -rf ~'", "sudo -i <<'E'\nrm -rf ~\nE", "sudo su <<'E'\nrm -rf ~\nE", "sudo -s rm -rf ~",
    "busybox rm -rf ~", "zsh -c 'rm -rf =(true)'",
    # values bash runs as code later
    "PS4='$(rm -rf ~)'; set -x; true", "x='a[$(rm -rf ~)]'; echo $((x))", "x='a[$(rm -rf ~)]'; echo ${a[x]}",
    "BASH_ENV=/tmp/x/env bash -c true", "export PROMPT_COMMAND='rm -rf ~'", "IFS=/ ; x=a/work/home/agent; rm -rf $x",
    "x='$(rm -rf ~)'; ((x))", "let 'x=a[$(rm -rf ~)]'", "x=a; [[ $x -eq 1 ]]", "[[ x -eq 1 ]]", "LD_PRELOAD=/tmp/x/evil.so ls",
    # trap, brace groups, elif
    "trap -- 'rm -rf ~' EXIT", "trap 'rm -rf ~' EXIT",
    "true && { cd /tmp/x; } ; rm -rf *", "false || { cd /tmp/x; }; rm -rf *", "{ cd /tmp/x; } | true; rm -rf *",
    "{ cd /tmp/x; } & rm -rf *", "true | { cd /tmp/x; rm -rf *; }",
    "if false; then :; elif cd /tmp/x; then :; fi; rm -rf *",
    "if false; then :; elif true; then cd /tmp/x; fi; rm -rf *",
    # mktemp that may print something else, or nothing
    'T=$(mktemp -d; echo /work/home/agent); rm -rf "$T"', 'T=$(mktemp --help); rm -rf $T/x',
    'export T=$(mktemp -d); rm -rf "$T/x"', 'local T=$(mktemp -d); rm -rf "$T"/*', 'T=$(mktemp -d) || true; rm -rf $T/x',
    # shells reading stdin from somewhere unanalyzed
    "exec <<'E'\nrm -rf ~\nE\nbash", "exec < /tmp/x/s; bash", "bash < <(printf 'rm -rf ~')", "bash -c bash <<'E'\nrm -rf ~\nE",
    "bash -c 'source /dev/stdin' <<'E'\nrm -rf ~\nE", "bash < /tmp/x/s", "x=r; bash <<E\n${x}m -rf ~\nE",
    "cat /tmp/x/s | bash", "bash -s < /tmp/x/s",
    # scripts written and run in the same command
    "cat > /tmp/x/s.sh <<'E'\nrm -rf ~\nE\nbash /tmp/x/s.sh", "printf 'rm -rf ~' > s; source s",
    "cp /tmp/x/a /tmp/x/s.sh; bash /tmp/x/s.sh", "printf 'rm -rf ~' > /tmp/x/s && chmod +x /tmp/x/s && /tmp/x/s",
    "for i in 1 2; do ./s.sh; printf 'rm -rf ~' > s.sh; done",
    # links and mounts made by programs the old regex missed
    f'mkdir -p {NX} && "ln" -s ~ {NX}/l && rm -rf {NX}/l/*', f"/usr/bin/ln -s ~ {NX}/l; rm -rf {NX}/l/*",
    f"l\\n -s ~ {NX}/l; rm -rf {NX}/l/*", f"python3 -c 'import os; os.symlink(\"/work/home/agent\", \"{NX}\")'; rm -rf {NX}/*",
    f"git clone -q ~/workspace/agent-config {NX}; rm -rf {NX}/x", f"sudo mount --bind ~ {NX}; rm -rf {NX}/*",
    f"for i in 1 2; do rm -rf {NX}/l/*; ln -s ~ {NX}/l; done",
    # git clean that removes nested repos
    "cd /tmp/x && git clean -ffdx", "cd /tmp/x && git clean -f -f -dx", "git -C /tmp/x clean -dxff",
]] + [(ASK, cmd + "\nrm -f /tmp/rm-safety-ok") for cmd in [
    # Round 3. Each also ends with a delete the hook approves on its own, so none passes for lack of one.
    # cd and other state changes behind a variable command name
    "C=cd; $C ~; rm -rf workspace", "C=shopt; $C -s cdable_vars", "F=python3; $F -c 1",
    # set -e that may not run
    "false && set -e; cd /tmp/nx; rm -rf *", "if false; then set -e; fi; cd /tmp/nx; rm -rf *",
    "set -e | true; cd /tmp/nx; rm -rf *", "false && { set -e; }; cd /tmp/nx; rm -rf *", "set -e & cd /tmp/nx; rm -rf *",
    "false && set -a; x=/tmp/a; bash -c 'rm -rf $x/y'",
    # quoted or subscripted assignments
    "x=a; declare 'x=../home/agent/victim'; rm -rf /tmp/$x", 'x=a; export "x=../home/agent"; rm -rf /tmp/$x',
    "x=a; local 'x=../home/agent'; rm -rf /tmp/$x", "declare 'PATH=/tmp/x'", "declare -n r=HOME",
    "printf -v 'BASH_CMDS[ls]' /bin/bash; ls -c 'r\"\"m -rf ~/victim'", "a[x]=1", "declare -i x=y",
    # renamed commands
    'hash -p /bin/pwd mktemp; T=$(mktemp); rm -rf "$T"', 'hash -p /usr/bin/env ls; ls "$(printf r)m" -rf ~/victim',
    "shopt -s cdable_vars", "cd /work/scratch/x && shopt -s cdable_vars && h=/work/home/agent/victim && cd h && rm -rf *",
    # unknown text spliced into code
    "eval \"echo $(printf '; r%s -rf ~/victim' m)\"", "bash -c \"echo $(printf '; r%s -rf ~/victim' m)\"",
    "bash -c \"echo $HOME; rm -rf /tmp/x/a\"",
    # arithmetic and subscripts
    "rm=1 rf=1; echo $(( $(rm -rf ~) ))", "x=1; echo $[x]", "test -v 'a[$(rm -rf ~/victim)]'",
    "printf -v 'a[$(rm -rf ~/victim)]' x", "declare 'a[$(rm -rf ~/victim)]=1'", "unset 'a[$(rm -rf ~/victim)]'",
    "[[ -v 'a[$(rm -rf ~/victim)]' ]]", "[ -v x ]",
    # find -exec {} and other commands
    r"find /usr/bin -name rm -exec {} -rf ~/victim \;", r"find /tmp/x -exec /usr/bin/rm -rf ~/victim \;",
    r"find /tmp/x -exec env rm -rf ~/victim \;",
    # backticks: bash keeps \' inside them
    r"echo `unset \'; rm -rf ~/victim; \'`",
    # arguments other programs run as code
    "flock /tmp/l -c 'r\"\"m -rf ~/victim'", "git -c alias.x='!f(){ r$1 -rf ~/victim; }; f' x m",
    "git -c alias.c=clean c -fdx", "git rebase --exec 'r\"\"m -rf ~'", "watch 'r\"\"m -rf ~'",
    "printf 'r%s -rf ~/victim' m | xargs env", "npx rimraf /work/home/agent", "npm exec rimraf /work/home/agent",
    "npm x -- rimraf /work/home/agent", "cargo --config 'target.x.runner=\"sh\"' run", "cargo +nightly build",
    "make --eval=all:", "make -E all:", "tar -xIzstd -f /tmp/x/a.tar", "tar --to-command=sh -xf /tmp/x/a.tar",
    "tar xIf zstd /tmp/x/a.tar", "git grep -Osh x", "git fetch --upload-pack=sh", "git diff --ext-diff",
    "git -C /tmp/x --git-dir=/work/home/agent/.git clean -fdx", "git --exec-path=/tmp/d status",
    "taskset -c 0 rm -rf ~", "xargs -a /tmp/x/list rm",
    # wrapper options
    "systemd-run --user -p 'ExecStartPre=/bin/rm -rf ~/victim' true", "systemd-run --user -E BASH_ENV=/tmp/evil bash -c true",
    "systemd-run --user --property=ExecStartPre=/bin/true true", "sudo -b rm -rf /tmp/x/a", "env -S 'rm -rf ~'",
    "sudo -u $U true",
    # files written, then run by something other than ./path
    "printf 'rm -rf ~' > .git/hooks/post-checkout; git checkout -b foo", "bash --rcfile /tmp/rc -i <<'E'\ntrue\nE",
    "bash --rcfile /tmp/rc -i -c true", "printf x > ~/.local/bin/ls; ls", "printf x > Makefile; make",
    "printf x >> ~/.bash_profile; bash -l -c true", "printf x > /tmp/x/s.sh; bash /tmp/x/s.sh",
    "python3 -c 1; ./s.sh", "python3 -c 1; npm test", "printf x > package.json; npm test",
    "for i in 1 2; do npm test; printf x > node_modules/.bin/y; done",
    # mktemp that prints something else
    "T=$(mktemp --vers); rm -rf $T", "T=$(mktemp -u); rm -rf $T/x", "T=$(/usr/bin/mktemp -d); rm -rf $T/x",
    # deletes racing a background command that may plant a symlink
    "rm -rf /tmp/x/d/* & ln -sfn ~ /tmp/x/d", "rm -rf /tmp/x/d/* | python3 -c 1",
    "systemd-run --user bash -c 'sleep 1; rm -rf /tmp/x/d/*'; python3 -c 1",
    "(sleep 1; rm -rf /tmp/x/d/*) & python3 -c 1", "python3 -c 1 | rm -rf /tmp/x/d/*",
    "T=/tmp/x/d; trap 'rm -rf $T/*' EXIT; python3 -c 1",
    "for i in 1 2; do rm -rf /tmp/x/d/*; python3 -c 1; done",
    # names a glob could pass to a program as options
    # data tools that write a file named in their arguments (a program in a PATH dir, say)
    "sort -o /work/home/agent/.local/bin/ls /tmp/x/a; ls", "sort -mo/work/home/agent/.local/bin/ls /tmp/x/a",
    "uniq /tmp/x/a /work/home/agent/.local/bin/ls", "xxd -r /tmp/x/a /work/home/agent/.local/bin/ls",
    # round 4: set -e is ignored inside Claude Code's `... && eval '<command>'`
    "set -e; cd /tmp/nx; rm -rf *", 'set -e; T=$(mktemp -d); rm -rf "$T"/*', "set -o errexit; cd /tmp/nx; rm -rf *",
    # bfs takes start paths anywhere in the expression
    "find /tmp/x -delete /work/home/agent/victim", "cd /tmp/x && find -delete /work/home/agent/victim",
    "find /tmp/x -name a -delete /work/home/agent", "find /tmp/x -fprint /work/home/agent/.bashrc -delete",
    # programs by path that skip the allowlist
    "//usr/bin/rm -rf /work/home/agent/victim", "/usr/bin/./rm -rf /work/home/agent/victim",
    "/usr/bin/../bin/rm -rf /work/home/agent/victim", "//usr/bin/git clean -fdx", "/opt/x/rimraf /work/home/agent",
    "../x/run.sh", "cd /tmp/x && ../../work/home/agent/bin/x", "bash /work/home/agent/bin/x.sh",
    # a local file named like a checked command (a regular copy of rm, say) skips none of the checks
    "./rm -rf /Users/pasta/victim; rm -f /tmp/gate-marker", "./rm -rf /work/home/agent/victim; rm -f /tmp/gate-marker",
    "bin/rm -rf /work/home/agent/victim; rm -f /tmp/gate-marker",
    ".//rm -rf /work/home/agent/victim; rm -f /tmp/gate-marker",
    "./RM -rf /work/home/agent/victim; rm -f /tmp/gate-marker",
    "./rmdir /work/home/agent/victim; rm -f /tmp/gate-marker",
    "./unlink /work/home/agent/victim; rm -f /tmp/gate-marker",
    "./shred -u /work/home/agent/victim; rm -f /tmp/gate-marker",
    "./find /work/home/agent/victim -delete; rm -f /tmp/gate-marker", "./git clean -fdx; rm -f /tmp/gate-marker",
    "./sh x; rm -f /tmp/gate-marker", "./python3 -c 1; rm -f /tmp/gate-marker", "./echo x; rm -f /tmp/gate-marker",
    "./cd x; rm -f /tmp/gate-marker", "./sudo rm -rf /work/home/agent/victim; rm -f /tmp/gate-marker",
    "./xargs rm -rf /work/home/agent/victim; rm -f /tmp/gate-marker", "bash rm; rm -f /tmp/gate-marker",
    '"./rm" -rf /work/home/agent/victim; rm -f /tmp/gate-marker',
    "'./rm' -rf /work/home/agent/victim; rm -f /tmp/gate-marker",
    "./'rm' -rf /work/home/agent/victim; rm -f /tmp/gate-marker",
    r"\./rm -rf /work/home/agent/victim; rm -f /tmp/gate-marker",
    r".\/rm -rf /work/home/agent/victim; rm -f /tmp/gate-marker",
    "env ./rm -rf /work/home/agent/victim; rm -f /tmp/gate-marker",
    "sudo ./rm -rf /work/home/agent/victim; rm -f /tmp/gate-marker",
    "nice ./rm -rf /work/home/agent/victim; rm -f /tmp/gate-marker",
    "timeout 5 ./rm -rf /work/home/agent/victim; rm -f /tmp/gate-marker",
    "systemd-run --user --same-dir ./rm -rf /work/home/agent/victim; rm -f /tmp/gate-marker",
    "time ./rm -rf /work/home/agent/victim; rm -f /tmp/gate-marker",
    "! ./rm -rf /work/home/agent/victim; rm -f /tmp/gate-marker",
    "if ./rm -rf /work/home/agent/victim; then :; fi; rm -f /tmp/gate-marker",
    "{ ./rm -rf /work/home/agent/victim; }; rm -f /tmp/gate-marker",
    "(./rm -rf /work/home/agent/victim); rm -f /tmp/gate-marker",
    "echo | ./rm -rf /work/home/agent/victim; rm -f /tmp/gate-marker",
    "./rm -rf /work/home/agent/victim & rm -f /tmp/gate-marker",
    "bash -c './rm -rf /work/home/agent/victim'; rm -f /tmp/gate-marker", "command rm -rf /work/home/agent/victim",
    "command ./rm -rf /work/home/agent/victim", "builtin rm -rf /work/home/agent/victim",
    "exec rm -rf /work/home/agent/victim", "exec ./rm -rf /work/home/agent/victim; rm -f /tmp/gate-marker",
    "env rm -rf /work/home/agent/victim", r"\rm -rf /work/home/agent/victim", "'rm' -rf /work/home/agent/victim",
    '"rm" -rf /work/home/agent/victim', 'r"m" -rf /work/home/agent/victim',
    "X=./rm; $X -rf /work/home/agent/victim; rm -f /tmp/gate-marker",
    'X=./rm; "$X" -rf /work/home/agent/victim; rm -f /tmp/gate-marker', "${X} -rf /work/home/agent/victim",
    # ~user/x is a home dir's file (~bin/gnurm is /bin/gnurm); bash x searches PATH for x
    "~bin/gnurm -rf /work/home/agent/victim", "sudo -n ~bin/gnurm -rf /etc", "~sync/gnuunlink /work/home/agent/.bashrc",
    "env ~bin/gnurm -rf /work/home/agent/victim", "bash -c '~bin/gnurm -rf /work/home/agent/victim'",
    "~/x", "~+/x", "~-/x", "bash ~bin/gnurm", "bash run-with-aspell gnurm -rf /work/home/agent/victim",
    "sh run-with-aspell gnuunlink /work/home/agent/.bashrc", "bash -e run-with-aspell gnurm -rf /work/home/agent",
    # quoted keywords are plain commands to bash
    'if false; then "fi"; x=sub; "then"; fi; rm -rf /work/scratch/$x', "if false; then \\fi; x=sub; fi; rm -rf /work/scratch/$x",
    "while false; do 'done'; x=a; done; rm -rf /tmp/$x",
    # build tools: deletes, writes and runners of their own
    "tar cf /tmp/x.tar --remove-files /work/home/agent/victim", "tar -C /work/home/agent --recursive-unlink -xf /tmp/x/a.tar",
    "tar --checkpoint-act=exec=sh -cf /tmp/x/a.tar src", "CARGO_TARGET_X86_64_UNKNOWN_LINUX_GNU_RUNNER=sh cargo run",
    "TAR_OPTIONS=--checkpoint=1 tar cf /tmp/x/a.tar src", "NODE_OPTIONS=--import=x python3 -c 1", "npm_config_x=1 ls",
    "MAKEFLAGS=x ls", "RUSTC_WRAPPER=x ls", "export PYTHONPATH=/tmp/x; python3 -c 1", "env PYTHONSTARTUP=/tmp/x/a python3",
    "sudo PERL5OPT=-Mx perl -e 1", "set -a; GIT_DIR=/x; git clean -fdx", "npm install github:x/y", "git branch -D main",
    "git diff --output=/work/home/agent/.bashrc", "make -f /tmp/x/m", "cargo run & printf x > src/main.rs; wait",
    # arithmetic subscripts
    "[[ 'a[$(rm -rf ~/victim)]' -eq 0 ]]", "a=(['a[$(rm -rf ~/victim)]']=1)", "a=(x y)", "x=a; [[ 1 -eq x ]]",
    # round 5: state bash keeps that the analysis doesn't model
    "local x=sub; cd /work/scratch/foo && rm -rf $x/*", "local x=sub; rm -rf /work/scratch/$x",
    "x=sub; wait -p x; cd /work/scratch/foo && rm -rf $x/*", "x=sub; wait -fp x; rm -rf /work/scratch/$x",
    'OLDPWD=sub; cd /work/scratch/foo && rm -rf "$OLDPWD"', "DIRSTACK=sub; rm -rf $DIRSTACK",
    "_=sub; echo /work/home/agent; rm -rf $_", "rm -rf /tmp/$RANDOM/$PWD", "unset OLDPWD",
    "x=a; : {x}>/dev/null; rm -rf /work/scratch/$x", "select x in a; do rm -rf /tmp/$x; done",
    "trap 'cd /work/home/agent' DEBUG; cd /work/scratch/foo && rm -rf *", "trap 'true' RETURN ERR",
    "trap 'rm -rf /tmp/x/a' INT", "! cd /tmp/nx || exit; rm -rf *", '! T=$(mktemp -d) || exit; rm -rf "$T"/*',
    "! cd /tmp/nx && rm -rf *", '! T=$(mktemp -d) && rm -rf "$T"/*',
    "rm -f /tmp/x; cat <<E\nE\\\n\nrm -rf /work/home/agent/victim\nE",
    # round 6
    "x=sub; export x; env -u x bash -c 'rm -rf /work/scratch/$x'", "x=sub; export x; env --unset=x bash -c 'rm -rf /work/scratch/$x'",
    "d=/work/scratch/x1/work/home/agent/victim; true {IFS}<<E\nE\nrm -rf $d", "x=a; true {x}<<E\nE\nrm -rf /tmp/$x",
    "x=a; true {x}<<-E\n\tE\nrm -rf /tmp/$x", "x=a; true {x}<<<y; rm -rf /tmp/$x",
    # sort long-option abbreviations
    "sort --compr=/tmp/s /tmp/x/a", "sort --ou=/work/home/agent/.local/bin/ls /tmp/x/a",
    # writes through a symlink out of scratch
    "touch -- '--to-command=sh x.tgz'; tar xf *.tgz", "mkdir -p ./-x; make *", "python3 -c 1; tar tf *.tgz",
]]

failed = 0


def run(payload, env):
    out = subprocess.run([sys.executable, "-I", str(HOOK)], input=payload, text=True, capture_output=True, env=env)
    if out.returncode != 0 or out.stderr:
        return f"exit {out.returncode}: {out.stderr.strip()}"
    if not out.stdout.strip():
        return ASK
    allow = {"hookSpecificOutput": {"hookEventName": "PermissionRequest", "decision": {"behavior": "allow"}}}
    got = json.loads(out.stdout)
    if got == allow:
        return ALLOW
    decision = got.get("hookSpecificOutput", {}).get("decision", {})
    if set(got) == {"hookSpecificOutput"} and got["hookSpecificOutput"].get("hookEventName") == "PermissionRequest" \
            and set(decision) == {"behavior", "message"} and decision["behavior"] == "deny" \
            and '"${dir:?}/${name:?}"' in decision["message"]:
        return DENY
    return f"unexpected output {out.stdout!r}"


def check(want, payload, label, env=ENV, exact=False):
    global failed
    got = run(payload if isinstance(payload, str) else json.dumps(payload), env)
    if got != want and not (want == ASK and got == DENY and not exact):
        print(f"FAIL want={want} got={got}: {label!r}")
        failed += 1


def request(command, tool="Bash", mode="bypassPermissions", **extra):
    payload = {"session_id": "s", "cwd": str(REPO), "hook_event_name": "PermissionRequest",
               "tool_name": tool, "tool_input": {"command": command, "description": "x"}, **extra}
    if mode is not None:
        payload["permission_mode"] = mode
    return payload


for want, cmd in CASES:
    check(want, request(cmd), cmd)

SAFE = "cd /work/scratch/x && rm -f *"
PAYLOADS = [
    (ALLOW, request(SAFE, tool="Monitor"), "Monitor"),
    (ASK, request(SAFE, mode=None), "no permission_mode field"),
    (ASK, request(SAFE, tool="Write"), "non-Bash tool"),
    (ASK, request(SAFE, tool="AskUserQuestion"), "AskUserQuestion"),
    (ASK, request(SAFE, tool="mcp__t3-code__delegate_task"), "MCP tool"),
    (ASK, request(SAFE, tool="PowerShell"), "PowerShell"),
    (ASK, request(SAFE, mode="default"), "default mode"),
    (ASK, request(SAFE, mode="acceptEdits"), "acceptEdits mode"),
    (ASK, request(SAFE, mode="auto"), "auto mode"),
    (ASK, request(SAFE, mode="plan"), "plan mode"),
    (ASK, request(SAFE, mode="dontAsk"), "dontAsk mode"),
    (ASK, request(SAFE, hook_event_name="PreToolUse"), "other event"),
    (ASK, {"tool_name": "Monitor", "permission_mode": "bypassPermissions", "tool_input": {"ws": {"url": "wss://x"}}}, "Monitor ws"),
    (ASK, {"tool_name": "Bash", "permission_mode": "bypassPermissions", "tool_input": {}}, "no command"),
    (ASK, {"tool_name": "Bash", "permission_mode": "bypassPermissions", "tool_input": {"command": ["rm", "x"]}}, "argv command"),
    (ASK, request(""), "empty command"),
    (ASK, "not json", "malformed input"),
    (ASK, "[]", "JSON array"),
]
for want, payload, label in PAYLOADS:
    check(want, payload, label)

CWDS = [
    (ALLOW, "rm -rf build", str(REPO)),
    (ASK, "rm -rf agent-config", HOME + "/workspace"),
    (ASK, "rm -rf agent-config/", HOME + "/workspace"),
    (ASK, "rm -rf workspace", HOME),
    (ASK, "rm -rf .ssh", HOME),
    (ASK, "rm -rf build", HOME),
    (ASK, "rm -rf work", "/"),
    (ASK, "rm -rf scratch", "/work"),
    (ASK, "rm -rf build", None),
    (ASK, "rm -rf .ssh/known_hosts", HOME),
    (ASK, "rm -rf .claude/projects", HOME),
    (ASK, "rm -rf gh", HOME + "/.config"),
    (ASK, "sudo rm -rf etc/ssh", "/"),
    (ASK, "rm -rf x", "/usr"),
    (ASK, "rm -rf hooks", str(REPO / ".git")),
    (ASK, "rm -rf objects/x", str(REPO / ".git")),
    (ASK, "rm -rf x", HOME + "/.t3/worktrees"),
    (ASK, "rm -rf t3-x", HOME + "/.t3/worktrees/dash"),
    (ALLOW, "rm -rf target", HOME + "/.t3/worktrees/dash/t3-x"),
    (ALLOW, "rm -rf build", "/work/scratch/x"),
    (ASK, "rm -rf x", "/work/scratch"),
]
for want, cmd, cwd in CWDS:
    payload = request(cmd, cwd=cwd)
    if cwd is None:
        del payload["cwd"]
    check(want, payload, f"[cwd {cwd}] {cmd}")
TMPDIRS = [
    (ALLOW, "/work/tmp"),
    (ALLOW, "/tmp/foo"),
    (ASK, None),
    (ASK, "/"),
    (ASK, HOME),
    (ASK, "/var/folders/xy/T"),
]
for want, value in TMPDIRS:
    env = {k: v for k, v in ENV.items() if k != "TMPDIR"} | ({"TMPDIR": value} if value else {})
    check(want, request("rm -rf $TMPDIR/work/home/agent"), f"TMPDIR={value}", env)

# Symlinks: a scratch path that leads out of scratch, checked against the real filesystem.
tmp = pathlib.Path(tempfile.mkdtemp(prefix="rm-safety-test-", dir="/tmp"))
atexit.register(shutil.rmtree, tmp, ignore_errors=True)
(tmp / "real/sub").mkdir(parents=True)
(tmp / "link").symlink_to(pathlib.Path.home())
(tmp / "filelink").symlink_to(REPO / "README.md")
local_bin = pathlib.Path(tempfile.mkdtemp(prefix="rm-safety-test-", dir=REPO))
atexit.register(shutil.rmtree, local_bin, ignore_errors=True)
shutil.copy(shutil.which("rm"), local_bin / "rm")
(local_bin / "real/sub").mkdir(parents=True)
(local_bin / "build.sh").write_text("#!/bin/sh\nexit 0\n")
(local_bin / "build.sh").chmod(0o755)
SYMLINKS = [
    (ASK, request(f"cd {tmp}/link && rm -rf *"), "cd through a symlink to ~"),
    (ASK, request(f"rm -rf {tmp}/link/*"), "glob through a symlink"),
    (ASK, request(f"rm -rf {tmp}/link/"), "trailing slash through a symlink"),
    (ASK, request(f"rm -rf {tmp}/link/sub/x"), "parent through a symlink"),
    (ALLOW, request(f"rm -rf {tmp}/link"), "the symlink itself"),
    (ALLOW, request(f"cd {tmp}/real && rm -rf *"), "cd into a real dir"),
    (ASK, request(f"cd {tmp} && rm -rf link/*"), "relative glob through a symlink"),
    (ASK, request("rm -rf link/x", cwd=str(tmp)), "relative path through a symlink from the session cwd"),
    (ALLOW, request("rm -rf real/sub", cwd=str(local_bin)), "relative path in the session cwd"),
    (ASK, request(f"shred -u {tmp}/filelink"), "shred through a final symlink"),
    (ALLOW, request(f"rm -f {tmp}/filelink"), "rm of a file symlink"),
    (ASK, request(f"find -H {tmp}/link -name '*.log' -delete"), "find -H through a symlink"),
]
for want, payload, label in SYMLINKS:
    check(want, payload, label)

# A regular local copy must not bypass the checks for a recognized command name.
# Only the hook analyzes these commands; the copied executable is never run.
RELATIVE_EXECUTABLES = [
    (ASK, request(f"./rm -rf {HOME}/rm-safety-protected-victim; rm -f /tmp/rm-safety-test-ok", cwd=str(local_bin)),
     "regular local rm copy cannot skip target checks"),
    (ASK, request("./rm -f /tmp/rm-safety-test-ok; rm -f /tmp/rm-safety-test-other", cwd=str(local_bin)),
     "recognized local executables stay prompts even with scratch arguments"),
    (ALLOW, request("./build.sh; rm -f /tmp/rm-safety-test-ok", cwd=str(local_bin)),
     "ordinary local scripts remain allowed"),
]
for want, payload, label in RELATIVE_EXECUTABLES:
    check(want, payload, label)

# Unproven deletes are denied with rewrite instructions (an unattended agent can't answer a prompt); a command
# with no delete keeps its prompt, and so does any mode other than bypassPermissions.
EXACT = [
    (DENY, request("rm -rf $d/$m"), "the 11-01 prompt: unguarded variables"),
    (DENY, request("rm -rf /work/home/agent/victim"), "outside scratch"),
    (DENY, request("for t in a b; do rm -rf \"$SLOT_DIR/$t\"; done"), "loop over an unknown dir"),
    (DENY, request("bash -c \"$blk\"; /bin/rm -f x"), "path-qualified rm after an opaque script"),
    (DENY, request("find \"$D\" -name '*.o' -delete"), "find -delete"),
    (DENY, request("cd $W && git clean -fdx"), "git clean"),
    (DENY, request("rm -rf $d/$m", tool="Monitor"), "Monitor"),
    (DENY, request("rm -rf \"unterminated"), "unparseable command with a delete"),
    (ASK, request("echo \"unterminated"), "unparseable command without a delete"),
    (ALLOW, request("rm -rf /work/scratch/foo"), "proven safe"),
    (ASK, request("git push origin main"), "no delete: an explicit ask rule"),
    (ASK, request("docker run --rm img; npm run confirm-deploy"), "--rm and words containing rm aren't deletes"),
    (ASK, request("rm -rf $d/$m", mode="default"), "default mode keeps its prompt"),
    (ASK, request("rm -rf $d/$m", mode="auto"), "auto mode keeps its prompt"),
    (ASK, request("rm -rf $d/$m", mode="acceptEdits"), "acceptEdits keeps its prompt"),
    (ASK, request("rm -rf $d/$m", tool="Write"), "non-Bash tool"),
    (ASK, "not json", "unreadable input"),
    (ASK, json.dumps({"hook_event_name": "PermissionRequest", "tool_name": "Bash",
                      "permission_mode": "bypassPermissions", "tool_input": "rm -rf /"}), "malformed tool_input"),
]
for want, payload, label in EXACT:
    check(want, payload, label, exact=True)

total = len(CASES) + len(PAYLOADS) + len(CWDS) + len(TMPDIRS) + len(SYMLINKS) + len(RELATIVE_EXECUTABLES) + len(EXACT)
print(f"rm-safety-allow: {total - failed}/{total} cases pass")
sys.exit(1 if failed else 0)
