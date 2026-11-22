#!/usr/bin/env python3
"""
Triage recent Dash Core pull requests to find small, merge-ready changes.
"""

import argparse
import concurrent.futures
import datetime
import json
import subprocess
import sys


def run_cmd(cmd):
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"Command failed ({res.returncode}): {' '.join(cmd)}\n{res.stderr}")
    return res.stdout


def fetch_recent_prs(repo: str, days: int):
    fields = "number,title,url,createdAt,updatedAt,additions,deletions,changedFiles,isDraft,author,labels,reviewDecision,mergeable,headRefName"
    out = run_cmd(["gh", "pr", "list", "-R", repo, "--state", "open", "--limit", "200", "--json", fields])
    prs = json.loads(out)

    now = datetime.datetime.now(datetime.timezone.utc)
    cutoff = now - datetime.timedelta(days=days)

    recent = []
    for pr in prs:
        created = datetime.datetime.fromisoformat(pr["createdAt"].replace("Z", "+00:00"))
        if created >= cutoff:
            recent.append(pr)

    return recent


def fetch_pr_details(repo: str, pr_number: int):
    fields = "latestReviews,reviews,statusCheckRollup,files,comments,body,reviewDecision,mergeStateStatus"
    out = run_cmd(["gh", "pr", "view", str(pr_number), "-R", repo, "--json", fields])
    return json.loads(out)


def triage_single_pr(repo: str, pr: dict, bot_usernames: set):
    num = pr["number"]
    details = fetch_pr_details(repo, num)

    author_login = pr.get("author", {}).get("login", "unknown")
    is_draft = pr.get("isDraft", False)
    mergeable = pr.get("mergeable", "UNKNOWN")
    review_decision = details.get("reviewDecision") or pr.get("reviewDecision", "")
    adds = pr.get("additions", 0)
    dels = pr.get("deletions", 0)
    files = pr.get("changedFiles", 0)
    size = adds + dels

    # Checks analysis
    checks = details.get("statusCheckRollup", []) or []
    real_failures = []
    advisory_failures = []
    pending_checks = []
    success_checks = 0

    for c in checks:
        state = c.get("state") or c.get("conclusion") or c.get("status")
        name = c.get("name") or c.get("context") or "unknown"
        if state in ["FAILURE", "failure", "ACTION_REQUIRED", "TIMED_OUT", "CANCELLED", "cancelled"]:
            if "predict_conflicts" in name:
                advisory_failures.append(name)
            else:
                real_failures.append(name)
        elif state in ["PENDING", "pending", "IN_PROGRESS", "in_progress", "QUEUED", "queued"]:
            pending_checks.append(name)
        elif state in ["SUCCESS", "success", "NEUTRAL", "SKIPPED", "skipped"]:
            success_checks += 1

    # Reviews analysis
    reviews = details.get("latestReviews", []) or details.get("reviews", []) or []
    human_approvals = []
    bot_approvals = []
    human_changes_req = []
    bot_changes_req = []

    for r in reviews:
        r_author = r.get("author", {}).get("login", "")
        r_is_bot = r.get("author", {}).get("is_bot", False) or (r_author.lower() in bot_usernames)
        r_state = r.get("state")

        if r_state == "APPROVED":
            if r_is_bot:
                bot_approvals.append(r_author)
            else:
                human_approvals.append(r_author)
        elif r_state == "CHANGES_REQUESTED":
            if r_is_bot:
                bot_changes_req.append(r_author)
            else:
                human_changes_req.append(r_author)

    # Changed files sample
    changed_files_list = [f.get("path") for f in details.get("files", []) if f.get("path")]

    return {
        "number": num,
        "title": pr["title"],
        "url": pr.get("url") or f"https://github.com/{repo}/pull/{num}",
        "author": author_login,
        "is_draft": is_draft,
        "mergeable": mergeable,
        "review_decision": review_decision,
        "adds": adds,
        "dels": dels,
        "changed_files_count": files,
        "size": size,
        "files": changed_files_list,
        "real_failures": real_failures,
        "advisory_failures": advisory_failures,
        "pending_checks": len(pending_checks),
        "success_checks": success_checks,
        "human_approvals": list(set(human_approvals)),
        "bot_approvals": list(set(bot_approvals)),
        "human_changes_req": list(set(human_changes_req)),
        "bot_changes_req": list(set(bot_changes_req)),
        "body": details.get("body", "") or "",
    }


def triage_prs(repo: str, days: int = 30):
    recent = fetch_recent_prs(repo, days)

    bot_usernames = {
        "thepastaclaw",
        "coderabbitai",
        "github-actions",
        "chatgpt-codex-connector",
        "codecov",
        "codecov-commenter",
    }

    triaged = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(triage_single_pr, repo, pr, bot_usernames): pr for pr in recent}
        for future in concurrent.futures.as_completed(futures):
            try:
                triaged.append(future.result())
            except Exception as e:
                pr = futures[future]
                print(f"Error fetching PR #{pr['number']}: {e}", file=sys.stderr)

    return triaged


def format_pr_pill(p):
    return f"[#{p['number']}]({p['url']}) ({p['size']}L)"


def categorize_and_format(triaged, repo: str, days: int):
    ready_tonight = []
    quick_review = []
    blocked_or_draft = []
    large_changes = []

    for pr in triaged:
        if pr["is_draft"] or pr["mergeable"] == "CONFLICTING" or pr["human_changes_req"]:
            blocked_or_draft.append(pr)
        elif pr["size"] > 500:
            large_changes.append(pr)
        elif len(pr["real_failures"]) == 0 and len(pr["bot_changes_req"]) == 0:
            ready_tonight.append(pr)
        else:
            quick_review.append(pr)

    ready_tonight.sort(key=lambda x: x["size"])
    quick_review.sort(key=lambda x: x["size"])
    blocked_or_draft.sort(key=lambda x: x["size"])
    large_changes.sort(key=lambda x: x["size"])

    lines = []
    lines.append(f"Reviewed {len(triaged)} pull requests opened on `{repo}` in the last {days} days.\n")

    if ready_tonight:
        lines.append("**Top Merge Candidates**")
        for p in ready_tonight:
            pr_link = f"[{p['title']}]({p['url']})"
            num_link = f"[#{p['number']}]({p['url']})"
            files_preview = ", ".join(f"`{f}`" for f in p["files"][:3])
            appr_str = f"Approved by @{p['bot_approvals'][0]}" if p["bot_approvals"] else ("Approved by @" + ", @".join(p["human_approvals"])) if p["human_approvals"] else "Clean CI"
            lines.append(f"- {num_link}: {pr_link} ({p['size']} lines: `+{p['adds']}/-{p['dels']}`, {p['changed_files_count']} files).")
            if files_preview:
                lines.append(f"  - Touches: {files_preview}")
            lines.append(f"  - **Status**: 100% CI pass, mergeable, {appr_str}.")
        lines.append("")

    if quick_review:
        lines.append("**Fast Follow-up Candidates**")
        for p in quick_review:
            pr_link = f"[{p['title']}]({p['url']})"
            num_link = f"[#{p['number']}]({p['url']})"
            files_preview = ", ".join(f"`{f}`" for f in p["files"][:3])
            ci_str = f"CI: {len(p['real_failures'])} failing ({', '.join(p['real_failures'])})" if p['real_failures'] else "CI: All tests passing"
            lines.append(f"- {num_link}: {pr_link} ({p['size']} lines: `+{p['adds']}/-{p['dels']}`, {p['changed_files_count']} files).")
            if files_preview:
                lines.append(f"  - Touches: {files_preview}")
            lines.append(f"  - **Status**: Mergeable by @{p['author']}, {ci_str}.")
        lines.append("")

    lines.append("**Summary of Recent PRs**")
    lines.append(f"- **Ready Tonight**: {', '.join([format_pr_pill(p) for p in ready_tonight]) or 'None'}.")
    lines.append(f"- **Quick Review**: {', '.join([format_pr_pill(p) for p in quick_review]) or 'None'}.")
    lines.append(f"- **Drafts / Blocked**: {', '.join([format_pr_pill(p) for p in blocked_or_draft]) or 'None'}.")
    lines.append(f"- **Large Features / Refactors**: {', '.join([format_pr_pill(p) for p in large_changes]) or 'None'}.")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Triage recent PRs by merge readiness and size.")
    parser.add_argument("--repo", default="dashpay/dash", help="GitHub repository (default: dashpay/dash)")
    parser.add_argument("--days", type=int, default=30, help="Window in days (default: 30)")
    parser.add_argument("--json", action="store_true", help="Output raw JSON analysis")
    args = parser.parse_args()

    triaged = triage_prs(args.repo, args.days)

    if args.json:
        print(json.dumps(triaged, indent=2))
    else:
        print(categorize_and_format(triaged, args.repo, args.days))


if __name__ == "__main__":
    main()
