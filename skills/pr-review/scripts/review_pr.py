#!/usr/bin/env python3
"""Collect a structured, thorough PR review packet for one GitHub pull request."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Tuple
import sys


HEURISTIC_RULES = [
    ("high", re.compile(r"\b(eval|exec|system\()", re.IGNORECASE), "Dynamic execution (eval/exec/system) may execute untrusted input."),
    ("high", re.compile(r"\b(sql|query)\b.*\+\s*\"|\+\s*.*\b(sql|query)\b", re.IGNORECASE), "Possible unsafe string-built query or command concatenation."),
    ("high", re.compile(r"pickle\.loads\(|yaml\.load\(|subprocess\.Popen\(|child_process\.exec", re.IGNORECASE), "High-risk deserialization or child-process execution path."),
    ("medium", re.compile(r"TODO|FIXME|HACK|XXX", re.IGNORECASE), "Incomplete or placeholder implementation marker introduced."),
    ("medium", re.compile(r"\b(api|auth|password|secret|private|token)_(key|token|secret)\b", re.IGNORECASE), "Possible credential-like token handling in diff."),
    ("medium", re.compile(r"\bcatch\s*\(\s*\w*\s*\)\s*\{\s*\}|except\s*:\s*$", re.IGNORECASE), "Empty or overly-broad error handling may hide defects."),
    ("medium", re.compile(r"\bconsole\.log\(|print\(|dbg!\(|log\(" , re.IGNORECASE), "Debug logging in code changes may leak or noise output in production."),
    ("low", re.compile(r"\btimeout\s*[:=]\s*None\b|ssl_verify\s*[:=]\s*False|verify\s*[:=]\s*False", re.IGNORECASE), "Potentially weak network/security default."),
]


def run(cmd: List[str], check: bool = True, cwd: Optional[str] = None) -> str:
    proc = subprocess.run(cmd, cwd=cwd, text=True, capture_output=True)
    if check and proc.returncode != 0:
        raise RuntimeError(f"command failed: {' '.join(cmd)}\n{proc.stderr.strip()}")
    return proc.stdout.strip()


def run_json(cmd: List[str], cwd: Optional[str] = None) -> Any:
    output = run(cmd, cwd=cwd)
    return json.loads(output) if output else []


def parse_repo(remote_url: str) -> str:
    match = re.search(r"github.com[:/](?P<owner>[^/]+)/(?P<repo>[^/.]+)(?:\.git)?$", remote_url)
    if not match:
        raise ValueError(f"Unrecognized remote URL: {remote_url}")
    return f"{match.group('owner')}/{match.group('repo')}"


def infer_repo(explicit: Optional[str]) -> str:
    if explicit:
        return explicit
    root = run(["git", "rev-parse", "--show-toplevel"], check=False)
    if not root:
        raise RuntimeError("Not in a git repository and --repo was not provided")
    remote = run(["git", "remote", "get-url", "origin"], check=False)
    if not remote:
        raise RuntimeError("origin remote not found and --repo was not provided")
    return parse_repo(remote)


def ensure_auth() -> None:
    status = run(["gh", "auth", "status"], check=False)
    if "Logged in to github.com" not in status:
        raise RuntimeError("GitHub CLI is not authenticated. Run `gh auth login` first.")


def api(endpoint: str, extra: Optional[List[str]] = None, paginate: bool = False) -> Any:
    args = ["gh", "api", endpoint]
    if paginate:
        args.append("--paginate")
    if extra:
        args.extend(extra)
    return run_json(args)


def list_api(endpoint: str) -> List[Dict[str, Any]]:
    items = api(endpoint, paginate=True)
    return items if isinstance(items, list) else [items]


def dt(value: str) -> str:
    if not value:
        return ""
    return datetime.fromisoformat(value.replace("Z", "+00:00")).strftime("%Y-%m-%d %H:%M UTC")


def comment_lines(items: Iterable[Dict[str, Any]], limit: int) -> List[str]:
    lines: List[str] = []
    for item in list(items)[:limit]:
        author = item.get("user", {}).get("login", "unknown")
        created = item.get("created_at", "")
        body = item.get("body", "").strip().replace("\n", " ")
        lines.append(f"- @{author} ({created}): {body}")
    return lines


def local_checkout(pr_number: str, repo: str) -> str:
    try:
        run(["gh", "pr", "checkout", pr_number, "--repo", repo])
        sha = run(["git", "rev-parse", "HEAD"])
        return f"checked out at {sha[:12]}"
    except Exception as exc:
        return f"failed ({exc})"


def parse_hunks(patch: str, file_path: str) -> Tuple[List[Dict[str, Any]], int]:
    """Parse patch hunks into findings and count added lines."""
    findings: List[Dict[str, Any]] = []
    added_lines = 0
    current_line = 1
    hunk_re = re.compile(r"@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")

    for raw in patch.splitlines():
        if raw.startswith("@@"):
            m = hunk_re.match(raw)
            if m:
                current_line = int(m.group(1))
            continue

        if raw.startswith("+") and not raw.startswith("+++"):
            added_lines += 1
            content = raw[1:]
            for severity, pattern, msg in HEURISTIC_RULES:
                if pattern.search(content):
                    findings.append(
                        {
                            "file": file_path,
                            "line": current_line,
                            "severity": severity,
                            "signal": msg,
                            "evidence": content.strip(),
                        }
                    )
            current_line += 1
            continue

        if raw.startswith("-") or raw.startswith(" "):
            if not raw.startswith("-++"):
                continue
        # keep line counters aligned when no newline deletion? this is sufficient for our heuristic scope
        if raw.startswith(" "):
            current_line += 1

    return findings, added_lines


def classify_file_risk(file_name: str, status: str, additions: int, deletions: int, patch: Optional[str]) -> List[str]:
    tags: List[str] = []
    lowered = file_name.lower()
    if any(x in lowered for x in ("auth", "security", "permission", "crypto", "secret", "password", "token")):
        tags.append("auth/security")
    if any(x in lowered for x in ("migrate", "migration", "schema", "ddl")):
        tags.append("migration/schema")
    if any(x in lowered for x in ("api", "router", "endpoint", "handler", "controller", "contract")):
        tags.append("api surface")
    if any(x in lowered for x in ("db", "database", "model", "dao", "query")):
        tags.append("data persistence")
    if status == "removed":
        tags.append("deletion risk")
    if additions + deletions > 400:
        tags.append("large file delta")
    if patch is None:
        tags.append("large diff omitted by API")
    return tags


def risk_notes(pr: Dict[str, Any], status: Dict[str, Any], checks: List[Dict[str, Any]], file_count: int, added_lines: int) -> List[str]:
    notes: List[str] = []
    body = (pr.get("body") or "").strip()

    if not body:
        notes.append("PR body is empty.")
    elif "testing" not in body.lower():
        notes.append("PR body has no explicit testing section.")

    if pr.get("draft"):
        notes.append("PR is marked as draft.")

    if (pr.get("additions", 0) + pr.get("deletions", 0)) > 1200 or file_count > 30 or added_lines > 2500:
        notes.append("Large change surface; require deeper manual review and potentially spot-check behavior boundaries.")

    merge_state = pr.get("mergeable_state")
    if merge_state in {"dirty", "blocked", "unknown"}:
        notes.append(f"Merge state risk: {merge_state}")

    if status.get("state") and status.get("state") != "success":
        notes.append(f"Commit status is `{status.get('state')}`.")

    non_success = [c for c in checks if c.get("conclusion") not in (None, "success")]
    if non_success:
        names = ", ".join(sorted({str(c.get("name")) for c in non_success}))
        notes.append(f"Non-success checks present: {names}")

    if pr.get("changed_files") and not pr.get("changed_files"):
        notes.append("No changed files found from API response.")

    if not notes:
        notes.append("No obvious process-level blockers detected from metadata.")
    return notes


def finding_signal(mergeable_state: Optional[str], status_state: str, unresolved_checks: bool, has_high: bool, has_medium: bool) -> str:
    if mergeable_state in {"dirty", "blocked"}:
        return "REQUIRES CHANGES"
    if unresolved_checks or status_state not in {"", "success"}:
        return "APPROVED WITH SUGGESTIONS"
    if has_high:
        return "REQUIRES CHANGES"
    if has_medium:
        return "APPROVED WITH SUGGESTIONS"
    return "APPROVED"


def sort_findings(findings: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rank = {"high": 0, "medium": 1, "low": 2}
    return sorted(findings, key=lambda f: (rank.get(f["severity"], 9), f["file"], f.get("line", 0)))


def build_report(repo: str, pr_number: str, do_checkout: bool, max_comments: int, json_only: bool) -> str:
    pr = api(f"repos/{repo}/pulls/{pr_number}")
    files = list_api(f"repos/{repo}/pulls/{pr_number}/files")
    issue_comments = list_api(f"repos/{repo}/issues/{pr_number}/comments")
    inline_comments = list_api(f"repos/{repo}/pulls/{pr_number}/comments")
    reviews = list_api(f"repos/{repo}/pulls/{pr_number}/reviews")

    head_sha = pr.get("head", {}).get("sha", "")
    status = api(f"repos/{repo}/commits/{head_sha}/status") if head_sha else {}
    check_payload = api(
        f"repos/{repo}/commits/{head_sha}/check-runs",
        extra=["-H", "Accept: application/vnd.github+json"],
    ) if head_sha else {}
    checks = check_payload.get("check_runs", check_payload if isinstance(check_payload, list) else [])

    commit_payload = api(f"repos/{repo}/pulls/{pr_number}/commits") if pr_number else []
    commit_count = len(commit_payload) if isinstance(commit_payload, list) else 0

    checkout_msg = local_checkout(pr_number, repo) if do_checkout else "not requested"

    all_findings: List[Dict[str, Any]] = []
    risk_tags_by_file: List[str] = []
    total_added = 0

    for f in files[:250]:
        patch = f.get("patch")
        file_name = f.get("filename", "")
        file_findings, added = parse_hunks(patch or "", file_name)
        all_findings.extend(file_findings)
        total_added += added
        risk_tags_by_file.extend(
            [f"{file_name}: {tag}" for tag in classify_file_risk(file_name, f.get("status", ""), f.get("additions", 0), f.get("deletions", 0), patch)]
        )

    notes = risk_notes(pr, status, checks if isinstance(checks, list) else [], pr.get("changed_files", 0), total_added)
    sorted_findings = sort_findings(all_findings)
    has_high = any(f["severity"] == "high" for f in sorted_findings)
    has_medium = any(f["severity"] == "medium" for f in sorted_findings)
    unresolved_check = any((c.get("conclusion") not in (None, "success")) for c in (checks if isinstance(checks, list) else []))
    outcome = finding_signal(pr.get("mergeable_state"), status.get("state", ""), unresolved_check, has_high, has_medium)

    lines: List[str] = [
        "# PR Review Packet",
        "",
        "## PR Metadata",
        f"- Repository: {repo}",
        f"- PR: #{pr.get('number')} — [{pr.get('title', '')}]({pr.get('html_url', '')})",
        f"- State: {pr.get('state')}",
        f"- Draft: {pr.get('draft', False)}",
        f"- Author: @{pr.get('user', {}).get('login', '')}",
        f"- Created: {dt(pr.get('created_at', ''))}",
        f"- Updated: {dt(pr.get('updated_at', ''))}",
        f"- Base: `{pr.get('base', {}).get('ref', '')}`",
        f"- Head: `{pr.get('head', {}).get('ref', '')}` ({pr.get('head', {}).get('sha', '')[:12] if pr.get('head', {}).get('sha') else ''})",
        f"- Mergeable: {pr.get('mergeable')}",
        f"- Merge state: {pr.get('mergeable_state')}",
        f"- Files changed: {pr.get('changed_files', 0)}",
        f"- Additions / Deletions: +{pr.get('additions', 0)} / -{pr.get('deletions', 0)}",
        f"- Commits in PR: {commit_count}",
        f"- Labels: {', '.join(l.get('name', '') for l in pr.get('labels', []) if l.get('name')) or 'none'}",
        f"- Requested reviewers: {', '.join(u.get('login', '') for r in pr.get('requested_reviewers', []) for u in [r] if u.get('login')) or 'none'}",
        f"- CI status: {status.get('state', 'unknown')}",
        f"- Check runs: {len(checks) if isinstance(checks, list) else 0}",
        f"- Local checkout: {checkout_msg}",
        "",
        "## PR Body",
        "```text",
        f"{(pr.get('body') or '').strip()}",
        "```",
    ]

    lines += [
        "",
        "## File risk map",
    ]
    if risk_tags_by_file:
        lines.extend([f"- {entry}" for entry in sorted(set(risk_tags_by_file))])
    else:
        lines.append("- no file-level risks detected")

    lines += [
        "",
        "## Detailed findings",
        "Sorted by severity, then file/line.",
    ]
    if sorted_findings:
        for f in sorted_findings:
            lines.append(f"- [{f['severity'].upper()}] `{f['file']}:{f.get('line', 0)}`: {f['signal']}")
            lines.append(f"  - evidence: `{f['evidence']}`")
            lines.append("  - recommendation: validate intent, escape boundaries, and add/extend tests around this exact branch")
    else:
        lines.append("- No heuristic-based findings matched from changed lines.")

    lines += [
        "",
        "## Files and diff snippets",
    ]
    for file_entry in files[:200]:
        filename = file_entry.get("filename", "")
        lines.append(f"- `{file_entry.get('status', '')}` {filename} (+{file_entry.get('additions', 0)} -{file_entry.get('deletions', 0)})")
        patch = file_entry.get("patch", "")
        if patch:
            lines.extend(["```diff", patch[:3000], "```"])

    lines += [
        "",
        "## Review discussion",
        "### Issue comments",
    ]
    lines.extend(comment_lines(issue_comments, max_comments) or ["- none"])
    lines.append("### Inline review comments")
    lines.extend(comment_lines(inline_comments, max_comments) or ["- none"])
    lines.append("### Review summaries")
    if reviews:
        for review in reviews[:max_comments]:
            summary = (review.get("body") or "").strip().replace("\n", " ")
            lines.append(f"- @{review.get('user', {}).get('login', 'unknown')} [{review.get('state', '')}]: {summary}")
    else:
        lines.append("- none")

    lines += [
        "",
        "## CI / checks",
        "### Commit status contexts",
    ]
    for ctx in status.get("statuses", []):
        lines.append(f"- {ctx.get('context')}: {ctx.get('state')} ({ctx.get('description', '')})")
    if checks:
        lines.append("### Check runs")
        for c in checks[:160]:
            lines.append(f"- {c.get('name')}: {c.get('status')} ({c.get('conclusion')})")
    if not status.get("statuses") and not checks:
        lines.append("- no check data returned")

    lines += [
        "",
        "## Early-risk signals",
    ]
    lines.extend([f"- {note}" for note in notes])

    if not json_only:
        lines += [
            "",
            "## Suggested review checkpoints",
            "1. Validate authn/authz, input validation, and privilege checks in touched auth/data paths.",
            "2. Confirm error handling preserves observability and does not suppress critical failures.",
            "3. Verify transactional boundaries and idempotency where state is modified.",
            "4. Ensure migration/compatibility impact is intentional and safe for rolling deploys.",
            "5. Confirm test changes cover new branches and negative paths.",
            f"",
            f"## Review outcome\n{outcome}",
        ]

    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect PR data for a review")
    parser.add_argument("pr_number", help="Pull request number")
    parser.add_argument("--repo", help="owner/repo when not running in the target repo")
    parser.add_argument("--local-checkout", action="store_true", help="Attempt gh pr checkout")
    parser.add_argument("--max-comments", type=int, default=40, help="Max comments per section")
    parser.add_argument("--json-only", action="store_true", help="Skip opinionated checklist section")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        ensure_auth()
        repo = infer_repo(args.repo)
        print(build_report(repo, args.pr_number, args.local_checkout, args.max_comments, args.json_only))
        return 0
    except Exception as exc:
        print(f"pr-review failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
