#!/usr/bin/env python3
"""Shared PR watcher for the babysit skill. Stdlib only; talks to GitHub through `gh api` (REST).

Commands
  once PR... [--ack TOKEN]  one pass: print every event not yet acked, exit
  wait PR... [--ack TOKEN]  poll until there is something to act on, print it, exit
  ack  PR... --ack TOKEN    ack a reported batch without waiting
  gc [--yes]                list (or delete) state files whose PR is merged/closed

PR refs: owner/repo#N, a github.com pull URL, or a bare N (uses --repo or the current repo).

stdout is always one JSON object:
  {"exit", "state_dir", "events": [...], "ack_token", "prs": {ref: summary}, ["error"]}
Exit codes: 0 events to handle, 2 nothing new (wait timeout / quiet once),
            3 every PR is merged/closed and acked, 1 error.

Events stay unacked until their batch's ack_token is passed back with --ack, so a session that dies
mid-handling leaves them for the next session, and a new session can't ack what it never saw.
"""
import argparse, fcntl, hashlib, json, os, re, subprocess, sys, tempfile, time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

OWN_REPLY_MARKERS = ("Posted autonomously by Claude", "Posted autonomously by Codex",
                     "Posted autonomously by Cursor", "Posted autonomously by Gemini")
FAILED = {"failure", "timed_out", "action_required", "startup_failure", "stale", "error"}
OK = {"success", "neutral", "skipped"}
DECISIVE = {"APPROVED", "CHANGES_REQUESTED", "DISMISSED"}
FULL_REFRESH_EVERY = 10  # polls; safety net for activity that doesn't bump the PR's updated_at
GREEN_CI_EVERY = 5       # polls between CI re-checks once a head is green (late suites, reruns)
NO_CHECKS_GRACE = 600    # seconds after a head appears before "no checks" is reported
EDIT_SETTLE = int(os.environ.get("BABYSIT_EDIT_SETTLE", 60))  # seconds an edited comment must be stable


class Fail(Exception):
    """kind: rate (back off), transient (retry), fatal (give up now)."""
    def __init__(self, msg, kind="fatal"):
        super().__init__(msg)
        self.kind = kind


def gh_json(path, items=None):
    """GET a REST path; with `items` (a jq path to the array) follow every page."""
    cmd = ["gh", "api", "-H", "Accept: application/vnd.github+json", path]
    if items:
        cmd[2:2] = ["--paginate", "--jq", f"{items} | tojson"]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
    except subprocess.TimeoutExpired:
        raise Fail(f"timeout: gh api {path}", "transient")
    if p.returncode:
        err = (p.stderr or p.stdout).strip()[-400:]
        kind = ("rate" if re.search(r"rate limit|secondary|abuse|HTTP 429", err, re.I)
                else "fatal" if re.search(r"HTTP (401|403|404|410|422)", err) else "transient")
        raise Fail(f"gh api {path}: {err}", kind)
    try:
        if items:
            return [json.loads(line) for line in p.stdout.splitlines() if line.strip()]
        return json.loads(p.stdout or "null")
    except ValueError as e:
        raise Fail(f"bad JSON from gh api {path}: {e}", "transient")


def parse_ts(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def stamp(dt=None):
    return (dt or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ")


def digest(s):
    return hashlib.sha1(s.encode()).hexdigest()[:12]


def pr_state(pr):
    return "merged" if pr.get("merged") else pr["state"]


def own_reply(body):
    """Our replies end with the attribution footer; quoting or mentioning it elsewhere doesn't count."""
    lines = [ln for ln in body.splitlines() if ln.strip()]
    return bool(lines) and any(m in lines[-1] for m in OWN_REPLY_MARKERS) and not lines[-1].lstrip().startswith(">")


def parse_ref(ref, default_repo):
    m = re.search(r"github\.com/([^/]+)/([^/]+)/pull/(\d+)", ref) or re.fullmatch(r"([^/\s]+)/([^#\s]+)#(\d+)", ref)
    if m:
        return m.group(1), m.group(2), int(m.group(3))
    if not ref.isdigit():
        raise Fail(f"unrecognized PR ref: {ref}")
    if not default_repo:
        p = subprocess.run(["gh", "repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner"],
                           capture_output=True, text=True)
        default_repo = p.stdout.strip()
    if "/" not in default_repo:
        raise Fail(f"cannot resolve repo for PR {ref}; pass owner/repo#{ref} or --repo")
    return (*default_repo.split("/", 1), int(ref))


def state_dir():
    """(dir, is_fallback). The tmp fallback differs inside and outside sandboxes, so callers are told."""
    preferred = os.environ.get("BABYSIT_STATE_DIR") or os.path.expanduser("~/.claude/babysit")
    for d in (preferred, os.path.join(tempfile.gettempdir(), "babysit")):
        try:
            os.makedirs(d, exist_ok=True)
            probe = os.path.join(d, f".probe{os.getpid()}")
            open(probe, "w").close()
            os.remove(probe)
            return d, d != preferred
        except OSError:
            continue
    raise Fail("no writable state dir")


class PR:
    def __init__(self, sdir, owner, repo, num):
        self.owner, self.repo, self.num = owner, repo, num
        self.ref = f"{owner}/{repo}#{num}"
        self.api = f"repos/{owner}/{repo}"
        self.path = os.path.join(sdir, f"{owner}__{repo}__pr{num}.watch.json")
        self.s = {}

    @contextmanager
    def locked(self):
        """Reload, mutate, save under the lock. Held for one pass of one PR only, so concurrent
        once/ack/wait processes interleave instead of blocking, and nesting can't deadlock."""
        with open(self.path + ".lock", "a") as lk:
            fcntl.flock(lk, fcntl.LOCK_EX)
            try:
                with open(self.path) as f:
                    self.s = json.load(f)
            except (OSError, ValueError):
                self.s = {}
            for k, v in (("seen", []), ("unacked", []), ("batches", {}), ("bodies", {}), ("reviews", {})):
                self.s.setdefault(k, v)
            yield self.s
            tmp = f"{self.path}.{os.getpid()}.tmp"
            with open(tmp, "w") as f:
                json.dump(self.s, f, indent=1)
            os.replace(tmp, self.path)

    def _emit(self, key, ev):
        s = self.s
        if key not in s["seen"] and all(e["key"] != key for e in s["unacked"]):
            s["unacked"].append({"key": key, "pr": self.ref, **ev})

    def ack(self, token):
        """Returns how many events were acked, or None if this PR has no batch with that token."""
        if not os.path.exists(self.path):
            return None
        with self.locked() as s:
            if token not in s["batches"]:
                return None
            keys = set(s["batches"].pop(token))
            s["seen"] += [e["key"] for e in s["unacked"] if e["key"] in keys]
            s["unacked"] = [e for e in s["unacked"] if e["key"] not in keys]
            if any(k.startswith("terminal:") for k in keys):
                s["closed"] = True
            return len(keys)

    def remember_batch(self, token, keys):
        with self.locked() as s:
            s["batches"].pop(token, None)  # re-insert so it counts as newest
            s["batches"][token] = keys
            for old in list(s["batches"])[:-5]:  # bound it; only recent batches can still be acked
                del s["batches"][old]

    def poll(self, max_body):
        with self.locked() as s:
            s["polls"] = polls = s.get("polls", 0) + 1
            pr = gh_json(f"{self.api}/pulls/{self.num}")
            head, state = pr["head"]["sha"], pr_state(pr)
            s["summary"] = summary = {"state": state, "head": head[:10], "mergeable_state": pr.get("mergeable_state"),
                                      "reviews": s["reviews"]}
            if state != "open":
                if not s.get("closed"):
                    self._emit(f"terminal:{state}", {"type": state})
                return
            if s.pop("closed", False):
                s["seen"] = [k for k in s["seen"] if not k.startswith("terminal:")]
                self._emit(f"reopened:{stamp()}", {"type": "reopened"})
            if s.get("head") != head:
                if s.get("head"):
                    self._emit(f"head:{head}", {"type": "head_moved", "from": s["head"][:10], "to": head[:10]})
                s["head"], s["head_seen_at"] = head, stamp()
            if pr.get("mergeable_state") == "dirty":
                self._emit(f"conflict:{head}", {"type": "conflict", "base": pr["base"]["ref"]})
            if pr["updated_at"] != s.get("updated_at") or s.get("recheck") or polls % FULL_REFRESH_EVERY == 1:
                self._poll_feedback(max_body)
                s["updated_at"] = pr["updated_at"]
            if s.get("ci_green") == head and polls % GREEN_CI_EVERY:
                summary["ci"] = s.get("ci_summary")
            else:
                summary["ci"] = s["ci_summary"] = self._poll_ci(head)

    def _poll_feedback(self, max_body):
        s, api, n = self.s, self.api, self.num
        q = f"?per_page=100&since={s['since']}" if s.get("since") else "?per_page=100"
        issue = gh_json(f"{api}/issues/{n}/comments{q}", ".[]")
        inline = gh_json(f"{api}/pulls/{n}/comments{q}", ".[]")
        reviews = gh_json(f"{api}/pulls/{n}/reviews?per_page=100", ".[]")
        stamps, s["recheck"] = [], False
        for r in sorted(reviews, key=lambda r: r.get("submitted_at") or ""):
            if r.get("state") in DECISIVE:
                s["reviews"][(r.get("user") or {}).get("login", "?")] = r["state"]
        for kind, items in (("issue", issue), ("inline", inline), ("review", reviews)):
            for c in items:
                if c.get("updated_at"):
                    stamps.append(c["updated_at"])
                body, key = c.get("body") or "", f"{kind}:{c['id']}"
                if own_reply(body) or (kind == "review" and (c.get("state") == "PENDING" or
                                                             (not body.strip() and c.get("state") not in DECISIVE))):
                    continue  # our replies; unsubmitted drafts; empty review containers (inline comments come separately)
                text = re.sub(r"<!--.*?-->", "", body, flags=re.S).strip()  # bots pad bodies with markup
                ev = {"type": "comment", "kind": kind, "id": c["id"], "author": (c.get("user") or {}).get("login"),
                      "at": c.get("submitted_at") or c.get("updated_at"), "url": c.get("html_url"),
                      "body": text[:max_body]}
                if len(text) > max_body:
                    ev["truncated"] = len(text)
                if kind == "inline":
                    ev.update(path=c.get("path"), line=c.get("line") or c.get("original_line"),
                              in_reply_to=c.get("in_reply_to_id"))
                if kind == "review":
                    ev["state"] = c.get("state")
                if kind == "issue":  # bots (e.g. review gates) edit one comment in place with their verdict
                    h, prev = digest(body), s["bodies"].get(str(c["id"]))
                    if prev and h != prev:
                        age = (datetime.now(timezone.utc) - parse_ts(c["updated_at"])).total_seconds()
                        if age < EDIT_SETTLE:
                            s["recheck"] = True  # still being edited; look again next poll
                            continue
                        key, ev["type"] = f"edit:{c['id']}:{h}", "comment_edited"
                    s["bodies"][str(c["id"])] = h
                self._emit(key, ev)
        if stamps:  # server timestamps only, minus a margin; ids dedupe the overlap
            s["since"] = stamp(parse_ts(max(stamps)) - timedelta(minutes=10))

    def _poll_ci(self, head):
        api = self.api
        runs = gh_json(f"{api}/commits/{head}/check-runs?per_page=100", ".check_runs[]")
        suites = gh_json(f"{api}/commits/{head}/check-suites?per_page=100", ".check_suites[]")
        status = gh_json(f"{api}/commits/{head}/status?per_page=100") or {}
        latest = {((r.get("app") or {}).get("slug"), r["name"]): r for r in sorted(runs, key=lambda r: r["id"])}
        checks = [{"name": name, "id": r["id"], "url": r.get("html_url"),
                   "state": (r.get("conclusion") or "unknown") if r["status"] == "completed" else r["status"]}
                  for (_, name), r in latest.items()]
        checks += [{"name": st["context"], "id": st.get("id"), "state": st["state"], "url": st.get("target_url")}
                   for st in status.get("statuses") or []]
        failed = [c for c in checks if c["state"] in FAILED]
        cancelled = [c for c in checks if c["state"] == "cancelled"]
        pending = [c for c in checks if c["state"] not in FAILED | OK | {"cancelled"}]
        # A workflow creates later jobs' runs only when they're queued, so between stages every existing
        # run can be done while the suite isn't. Suites with no runs at all (apps that never report) don't count.
        open_suites = [x for x in suites if x["status"] != "completed" and x.get("latest_check_runs_count")]
        for c in failed:  # keyed by run id so a failed rerun is reported again
            self._emit(f"ci_failed:{head}:{c['name']}:{c['id']}",
                       {"type": "ci_failed", "check": c["name"], "conclusion": c["state"], "url": c["url"]})
        summary = {"total": len(checks), "pending": len(pending) + len(open_suites), "failed": len(failed),
                   "cancelled": len(cancelled)}
        if not checks:
            if (datetime.now(timezone.utc) - parse_ts(self.s["head_seen_at"])).total_seconds() > NO_CHECKS_GRACE:
                self._emit(f"no_checks:{head}", {"type": "no_checks", "head": head[:10]})
            return summary  # no checks is never green
        if summary["pending"]:
            self.s.pop("ci_green", None)
            return summary
        bad = sorted(f"{c['name']}={c['id']}" for c in failed + cancelled)
        self._emit(f"ci_complete:{head}:{digest(','.join(bad))}",
                   {"type": "ci_complete", "head": head[:10], "passed": len(checks) - len(bad),
                    "failed": [c["name"] for c in failed], "cancelled": [c["name"] for c in cancelled]})
        if bad:
            self.s.pop("ci_green", None)
        else:
            self.s["ci_green"] = head
        return summary


def output(code, exit_reason, ctx, prs, **extra):
    events = [e for p in prs for e in p.s.get("unacked", [])]
    token = None
    if events:
        token = digest("\n".join(sorted(e["key"] for e in events)))
        for p in prs:  # exactly the keys printed, even if another process has added more since
            if p.s.get("unacked"):
                p.remember_batch(token, [e["key"] for e in p.s["unacked"]])
    print(json.dumps({"exit": exit_reason, **ctx, "events": events, "ack_token": token,
                      "prs": {p.ref: p.s.get("summary") for p in prs}, **extra}, indent=1))
    sys.exit(code)


def cmd_watch(a, ctx):
    prs = [PR(ctx["state_dir"], *parse_ref(r, a.repo)) for r in a.prs]
    extra = {}
    if a.ack:
        acked = {p.ref: p.ack(a.ack) for p in prs}
        extra["acked"] = {ref: n for ref, n in acked.items() if n is not None}
        if not extra["acked"]:
            extra["warning"] = f"ack token {a.ack} matched no batch (already acked, expired, or from another session)"
    if a.cmd == "ack":
        output(0, "acked", ctx, [], **extra)
    start = time.time()
    interval = a.interval or max(120, 15 * len(prs))  # ~1-4 REST calls per PR per poll
    deadline, delay, err_since, transient_tries = start + a.timeout, interval, None, 0
    while True:
        try:
            for p in prs:
                p.poll(a.max_body)
            delay, err_since, transient_tries = interval, None, 0
        except Fail as e:
            err_since = err_since or time.time()
            transient_tries += 1
            if (e.kind == "fatal" or (a.cmd == "once" and (e.kind == "rate" or transient_tries > 3))
                    or time.time() - err_since > a.max_error_seconds):
                output(1, "error", ctx, prs, error=str(e), **extra)
            delay = 5 * transient_tries if a.cmd == "once" else min(900 if e.kind == "rate" else 600, delay * 2)
            if a.cmd == "wait" and time.time() + delay > deadline:
                output(2, "timeout", ctx, prs, last_error=str(e), **extra)
            time.sleep(delay)
            continue
        if any(p.s["unacked"] for p in prs):
            output(0, "events", ctx, prs, **extra)
        if all(p.s.get("closed") for p in prs):
            output(3, "all_closed", ctx, prs, **extra)
        if a.cmd == "once":
            # A bot verdict edited in just before this wake is still settling; give it a moment.
            if any(p.s.get("recheck") for p in prs) and time.time() - start < EDIT_SETTLE:
                time.sleep(min(20, EDIT_SETTLE))
                continue
            output(2, "quiet", ctx, prs, **extra)
        if time.time() + delay > deadline:
            output(2, "timeout", ctx, prs, **extra)
        time.sleep(min(delay, max(1, deadline - time.time())))


def cmd_gc(a, ctx):
    sdir = ctx["state_dir"]
    pat = re.compile(r"^(.+?)_{1,2}(.+?)_{1,2}pr(\d+)(\.watch|\.notes)?\.json$")
    out = []
    for f in sorted(os.listdir(sdir)):
        m = pat.match(f)
        if not m:
            continue
        try:
            state = pr_state(gh_json(f"repos/{m.group(1)}/{m.group(2)}/pulls/{m.group(3)}"))
        except Fail as e:
            out.append({"file": f, "error": str(e)[:160]})
            continue
        if state != "open":
            out.append({"file": f, "state": state, "deleted": a.yes})
            if a.yes:
                for p in (f, f + ".lock"):
                    try:
                        os.remove(os.path.join(sdir, p))
                    except OSError:
                        pass
    print(json.dumps({**ctx, "stale": out}, indent=1))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("prs", nargs="+")
    common.add_argument("--repo", default="", help="owner/repo for bare PR numbers")
    common.add_argument("--ack", metavar="TOKEN", help="ack_token of the batch you finished handling")
    for name in ("once", "wait"):
        sp = sub.add_parser(name, parents=[common])
        sp.add_argument("--interval", type=int, help="seconds between polls (default max(120, 15 x PRs))")
        sp.add_argument("--timeout", type=int, default=3300,
                        help="exit 2 after this many quiet seconds (default 3300, under the 1h prompt-cache TTL)")
        sp.add_argument("--max-error-seconds", type=int, default=1800,
                        help="wait: exit 1 if GitHub keeps failing this long (default 1800)")
        sp.add_argument("--max-body", type=int, default=1500, help="truncate comment bodies (default 1500 chars)")
    sub.add_parser("ack", parents=[common])
    sp = sub.add_parser("gc")
    sp.add_argument("--yes", action="store_true", help="delete instead of listing")
    a = ap.parse_args()
    if a.cmd == "ack" and not a.ack:
        ap.error("ack needs --ack TOKEN (the ack_token printed with the events)")
    ctx = {}
    try:
        sdir, fallback = state_dir()
        ctx = {"state_dir": sdir, **({"state_dir_fallback": True} if fallback else {})}
        (cmd_gc if a.cmd == "gc" else cmd_watch)(a, ctx)
    except Fail as e:
        print(json.dumps({"exit": "error", **ctx, "error": str(e)}))
        sys.exit(1)
    except Exception as e:  # always answer in JSON; a bare traceback reads like a dead watcher
        print(json.dumps({"exit": "error", **ctx, "error": f"{type(e).__name__}: {e}"}))
        sys.exit(1)


if __name__ == "__main__":
    main()
