"""Scenario tests for pr_wait.py against a fake `gh` driven by a fixture file. Run: python3 -I test_pr_wait.py"""
import json, os, subprocess, sys, tempfile, textwrap, time

SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pr_wait.py")
tmp = tempfile.mkdtemp()
bindir, fixture, sdir = f"{tmp}/bin", f"{tmp}/fixture.json", f"{tmp}/state"
os.makedirs(bindir)
with open(f"{bindir}/gh", "w") as f:
    f.write(textwrap.dedent(f"""\
        #!{sys.executable}
        import json, sys
        fx = json.load(open({fixture!r}))
        args = sys.argv[1:]
        path = next(a for a in args[1:] if a.startswith("repos/")).split("?")[0]
        if fx.get("error"):
            sys.stderr.write(fx["error"]); sys.exit(1)
        data = fx["routes"][path]
        if "--jq" in args:
            jq = args[args.index("--jq") + 1]
            items = data[jq.split("[]")[0].lstrip(".")] if jq.startswith(".check_") else data
            for it in items: print(json.dumps(it))
        else:
            print(json.dumps(data))
        """))
os.chmod(f"{bindir}/gh", 0o755)
ENV = {**os.environ, "PATH": f"{bindir}:{os.environ['PATH']}", "BABYSIT_STATE_DIR": sdir}
A = "repos/o/r"
NOW = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
OLD = "2026-01-01T00:00:00Z"


def pr(state="open", merged=False, head="h1", updated=NOW, mstate="clean"):
    return {"state": state, "merged": merged, "updated_at": updated, "mergeable_state": mstate,
            "head": {"sha": head}, "base": {"ref": "develop"}}


def put(prj, issue=(), inline=(), reviews=(), runs=(), suites=None, statuses=(), head="h1"):
    if suites is None:
        suites = [{"status": "completed", "latest_check_runs_count": len(runs)}] if runs else []
    json.dump({"routes": {
        f"{A}/pulls/7": prj, f"{A}/issues/7/comments": list(issue), f"{A}/pulls/7/comments": list(inline),
        f"{A}/pulls/7/reviews": list(reviews), f"{A}/commits/{head}/check-runs": {"check_runs": list(runs)},
        f"{A}/commits/{head}/check-suites": {"check_suites": list(suites)},
        f"{A}/commits/{head}/status": {"statuses": list(statuses)}}}, open(fixture, "w"))


def run(*args, bg=False):
    cmd = [sys.executable, SCRIPT, *args]
    if bg:
        return subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=ENV)
    p = subprocess.run(cmd, capture_output=True, text=True, env=ENV, timeout=120)
    return p.returncode, (json.loads(p.stdout) if p.stdout.strip() else {"stderr": p.stderr})


def com(i, body="looks wrong", user="coderabbitai", ts=NOW):
    return {"id": i, "body": body, "user": {"login": user}, "updated_at": ts, "html_url": f"u{i}"}


def crun(i, name, status="completed", concl="success", app="github-actions"):
    return {"id": i, "name": name, "status": status, "conclusion": concl if status == "completed" else None,
            "app": {"slug": app}}


def types(out):
    return sorted(e["type"] for e in out["events"])


fails = 0
def check(cond, msg):
    global fails
    print(("ok   " if cond else "FAIL ") + msg)
    fails += not cond


FOOTER = "fixed\n---\n🤖 Posted autonomously by Claude (claude-opus-5-5) on behalf of pasta."
reviews = [{"id": 100 + i, "body": f"r{i}", "state": "COMMENTED", "user": {"login": "thepastaclaw"},
            "submitted_at": NOW, "updated_at": NOW} for i in range(35)]
reviews += [{"id": 999, "body": "", "state": "COMMENTED", "user": {"login": "x"}, "submitted_at": NOW},
            {"id": 998, "body": "", "state": "CHANGES_REQUESTED", "user": {"login": "human"}, "submitted_at": OLD},
            {"id": 997, "body": "", "state": "APPROVED", "user": {"login": "human"}, "submitted_at": NOW},
            {"id": 996, "body": "draft", "state": "PENDING", "user": {"login": "me"}}]  # no timestamps at all

# 1. first pass: every review page, own reply filtered, a quoted footer is NOT filtered, latest review state wins
quoted = "> fixed\n> 🤖 Posted autonomously by Claude on behalf of pasta.\n\nno it isn't"
CODEX_FOOTER = "done\n---\n🤖 Posted autonomously by Codex on behalf of pasta."
CURSOR_FOOTER = "done\n---\n🤖 Posted autonomously by Cursor on behalf of pasta."
GEMINI_FOOTER = "done\n---\n🤖 Posted autonomously by Gemini on behalf of pasta."
OPENCODE_FOOTER = "done\n---\n🤖 Posted autonomously by OpenCode (inkling-2-mini) on behalf of pasta."
put(pr(), issue=[com(1), com(2, FOOTER), com(3, quoted, user="human"), com(4, CODEX_FOOTER),
                 com(5, CURSOR_FOOTER), com(6, GEMINI_FOOTER), com(7, OPENCODE_FOOTER)], reviews=reviews,
    runs=[crun(10, "build", "in_progress")])
code, out = run("once", "o/r#7")
ids = {e.get("id") for e in out["events"]}
check(code == 0 and sum(e.get("kind") == "review" for e in out["events"]) == 37, f"all reviews reported {out.get('error','')}")
check(2 not in ids and 4 not in ids and 5 not in ids and 6 not in ids and 7 not in ids and 3 in ids and 999 not in ids,
      "own Claude/Codex/Cursor/Gemini/OpenCode replies skipped; quoted reply kept; empty container skipped")
check(out["prs"]["o/r#7"]["reviews"] == {"human": "APPROVED"}, "latest decisive review per reviewer")
token1 = out["ack_token"]

# 2. a fresh session must not be able to ack what it never saw: bogus token keeps everything
code, out = run("once", "--ack", "bogus", "o/r#7")
check(code == 0 and len(out["events"]) == 39, "unacked events survive a bogus/other-session ack")

# 3. ack with the real token, then quiet
code, out = run("once", "--ack", token1, "o/r#7")
check(code == 2 and out["exit"] == "quiet" and not out["events"], f"acked => quiet ({out['exit']})")

# 4. bot edits its comment in place: once waits for a fresh edit to settle, then reports it exactly once
ENV["BABYSIT_EDIT_SETTLE"] = "3"
fresh = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
put(pr(updated=OLD), issue=[com(1, "<!-- gate -->\n✅ final verdict", ts=fresh)], reviews=reviews,
    runs=[crun(10, "build", "in_progress")])
code, out = run("once", "o/r#7")
ev = out["events"][0] if out["events"] else {}
check(types(out) == ["comment_edited"] and ev.get("body") == "✅ final verdict",
      f"settling edit waited for and reported, markup stripped ({types(out)})")
code, out = run("once", "--ack", out["ack_token"], "o/r#7")
check(code == 2 and out["acked"] == {"o/r#7": 1}, "same edit not reported twice; ack count reported")
code, out = run("ack", "--ack", "nope", "o/r#7")
check("warning" in out and out["acked"] == {}, "unknown ack token warns")

# 5. CI between workflow stages: all existing runs done but suite still open => not complete
put(pr(), reviews=reviews, runs=[crun(10, "build"), crun(11, "lint")],
    suites=[{"status": "queued", "latest_check_runs_count": 2}, {"status": "queued", "latest_check_runs_count": 0}])
code, out = run("once", "o/r#7")
check(code == 2 and out["prs"]["o/r#7"]["ci"]["pending"] == 1, "open suite keeps CI pending; empty suites ignored")

# 6. early failure, then a failed rerun is reported again with completion; cancelled kept separate
put(pr(), reviews=reviews, runs=[crun(10, "build", "in_progress"), crun(11, "lint", concl="failure")])
code, out = run("once", "o/r#7")
check(types(out) == ["ci_failed"], f"early failure before completion ({types(out)})")
run("ack", "--ack", out["ack_token"], "o/r#7")
put(pr(), reviews=reviews, runs=[crun(10, "build"), crun(11, "lint", concl="failure"), crun(12, "lint", concl="failure"),
                                 crun(13, "tsan", concl="cancelled")])
code, out = run("once", "o/r#7")
comp = next((e for e in out["events"] if e["type"] == "ci_complete"), {})
check(types(out) == ["ci_complete", "ci_failed"], f"failed rerun re-reported + completion ({types(out)})")
check(comp.get("failed") == ["lint"] and comp.get("cancelled") == ["tsan"], "cancelled kept separate from failed")
run("ack", "--ack", out["ack_token"], "o/r#7")

# 7. same name from two apps isn't collapsed; zero checks is never green; head move reported
put(pr(head="h2"), reviews=reviews, head="h2",
    runs=[crun(20, "build", app="github-actions"), crun(21, "build", "in_progress", app="circleci")])
code, out = run("once", "o/r#7")
check("head_moved" in types(out) and "ci_complete" not in types(out), f"per-app checks; head move ({types(out)})")
run("ack", "--ack", out["ack_token"], "o/r#7")
put(pr(head="h3"), reviews=reviews, head="h3")
code, out = run("once", "o/r#7")
check(not any(e["type"] == "ci_complete" for e in out["events"]), "zero checks is not green")
run("ack", "--ack", out["ack_token"], "o/r#7")

# 8. errors: 404 fails fast even in wait; rate limit in once is exit 1; output is always JSON
json.dump({"error": "gh: Not Found (HTTP 404)"}, open(fixture, "w"))
t = time.time()
code, out = run("wait", "o/r#7", "--interval", "1", "--max-error-seconds", "60")
check(code == 1 and time.time() - t < 10 and "404" in out.get("error", ""), "404 fails fast with JSON error")
json.dump({"error": "gh: API rate limit exceeded (HTTP 403)"}, open(fixture, "w"))
code, out = run("once", "o/r#7")
check(code == 1 and out["exit"] == "error" and not out["events"], "rate limit is an error exit, not an event")
code, out = run("wait", "o/r#7", "--interval", "1", "--max-error-seconds", "2")
check(code == 1 and "rate limit" in out.get("error", ""), "wait surfaces persistent rate limiting")
json.dump({"error": "gh: Bad Gateway (HTTP 502)"}, open(fixture, "w"))
t = time.time()
code, out = run("wait", "o/r#7", "--interval", "1", "--timeout", "3", "--max-error-seconds", "60")
check(code == 2 and time.time() - t < 8 and "502" in out.get("last_error", ""),
      f"errors never outlive --timeout ({time.time() - t:.1f}s)")

# 9. a background wait does not block a concurrent once/ack on the same PR (lock is per pass)
put(pr(head="h3"), reviews=reviews, head="h3", runs=[crun(30, "build", "in_progress")])
bg = run("wait", "o/r#7", "--interval", "1", "--timeout", "8", bg=True)
time.sleep(2)
t = time.time()
code, out = run("once", "o/r#7")
check(code == 2 and time.time() - t < 5, f"once doesn't block behind a running wait ({time.time() - t:.1f}s)")
bg.wait(timeout=30)
check(bg.returncode == 2, "background wait times out with exit 2")

# 10. merged => terminal event; acking it => exit 3; no state deletion so reopen is detectable
put(pr(state="closed", merged=True, head="h3"), head="h3")
code, out = run("wait", "o/r#7", "--interval", "1", "--timeout", "5")
check(code == 0 and types(out) == ["merged"], "merge reported")
code, out = run("wait", "--ack", out["ack_token"], "o/r#7")
check(code == 3 and out["exit"] == "all_closed", "acked merge => exit 3")
put(pr(head="h3"), reviews=reviews, head="h3", runs=[crun(30, "build")])
code, out = run("once", "o/r#7")
check("reopened" in types(out), "reopen detected")
run("ack", "--ack", out["ack_token"], "o/r#7")

# 11. conflict, and gc lists closed PRs without deleting unless --yes
put(pr(mstate="dirty", head="h4"), head="h4", runs=[crun(40, "build")])
code, out = run("once", "o/r#7")
check("conflict" in types(out), "merge conflict reported")
put(pr(state="closed", head="h4"), head="h4")
code, out = run("gc")
check(len(out["stale"]) == 1 and os.path.exists(f"{sdir}/o__r__pr7.watch.json"), "gc lists without deleting")
code, out = run("gc", "--yes")
check(not os.path.exists(f"{sdir}/o__r__pr7.watch.json"), "gc --yes deletes closed PR state")

print("FAILURES:", fails)
sys.exit(1 if fails else 0)
