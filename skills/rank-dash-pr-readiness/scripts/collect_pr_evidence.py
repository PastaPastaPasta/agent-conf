#!/usr/bin/env python3
"""Collect a complete, analysis-friendly snapshot of open GitHub PR evidence."""

from __future__ import annotations

import argparse
import concurrent.futures
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


LIST_FIELDS = (
    "number,title,url,author,state,closedAt,mergedAt,isDraft,createdAt,updatedAt,baseRefName,headRefName,"
    "mergeable,mergeStateStatus,reviewDecision,reviewRequests,labels,additions,"
    "deletions,changedFiles,statusCheckRollup"
)
DETAIL_FIELDS = "body,comments,reviews,latestReviews,commits,files"

THREAD_QUERY = r"""
query($owner: String!, $repo: String!, $number: Int!, $after: String) {
  repository(owner: $owner, name: $repo) {
    pullRequest(number: $number) {
      reviewThreads(first: 100, after: $after) {
        totalCount
        pageInfo { hasNextPage endCursor }
        nodes {
          id
          isResolved
          isOutdated
          path
          line
          originalLine
          diffSide
          comments(first: 100) {
            totalCount
            pageInfo { hasNextPage endCursor }
            nodes {
              id
              author { login }
              authorAssociation
              body
              createdAt
              updatedAt
              url
              state
              outdated
              path
              line
              originalLine
              replyTo { id }
            }
          }
        }
      }
    }
  }
}
"""


def run_gh(args: list[str], *, timeout: int = 240) -> Any:
    command = ["gh", *args]
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("gh is not installed or is not on PATH") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"gh command timed out after {timeout}s: {' '.join(command[:4])}") from exc
    if completed.returncode:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise RuntimeError(f"gh exited {completed.returncode}: {detail}")
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"gh returned invalid JSON: {exc}") from exc


def split_repo(repo: str) -> tuple[str, str]:
    pieces = repo.strip().split("/")
    if len(pieces) != 2 or not all(pieces):
        raise ValueError("--repo must be OWNER/REPO")
    return pieces[0], pieces[1]


def list_prs(repo: str, limit: int, selected: list[int]) -> list[dict[str, Any]]:
    if selected:
        numbers = selected
    else:
        try:
            return run_gh(
                [
                    "pr",
                    "list",
                    "-R",
                    repo,
                    "--state",
                    "open",
                    "--limit",
                    str(limit),
                    "--json",
                    LIST_FIELDS,
                ]
            )
        except Exception as exc:
            print(f"gh pr list failed ({exc}); falling back to REST listing + per-PR view...", file=sys.stderr)
            completed = subprocess.run(
                ["gh", "api", f"repos/{repo}/pulls?state=open&per_page=100", "--paginate", "--jq", ".[].number"],
                check=True,
                capture_output=True,
                text=True,
            )
            numbers = [int(line.strip()) for line in completed.stdout.splitlines() if line.strip()]
            if limit:
                numbers = numbers[:limit]

    def fetch_base(num: int) -> dict[str, Any]:
        return run_gh(["pr", "view", "-R", repo, str(num), "--json", LIST_FIELDS])

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        return list(executor.map(fetch_base, numbers))


def collect_threads(owner: str, repo_name: str, number: int) -> tuple[list[dict[str, Any]], list[str]]:
    after: str | None = None
    threads: list[dict[str, Any]] = []
    warnings: list[str] = []
    expected_total: int | None = None

    while True:
        args = [
            "api",
            "graphql",
            "-f",
            f"owner={owner}",
            "-f",
            f"repo={repo_name}",
            "-F",
            f"number={number}",
            "-f",
            f"query={THREAD_QUERY}",
        ]
        if after:
            args.extend(["-f", f"after={after}"])
        payload = run_gh(args)
        if payload.get("errors"):
            raise RuntimeError(f"GraphQL errors: {json.dumps(payload['errors'], ensure_ascii=False)}")
        pull = payload.get("data", {}).get("repository", {}).get("pullRequest")
        if pull is None:
            raise RuntimeError("GraphQL returned no pull request")
        page = pull["reviewThreads"]
        expected_total = page["totalCount"]
        for thread in page["nodes"]:
            comments = thread.get("comments", {})
            if comments.get("pageInfo", {}).get("hasNextPage"):
                warnings.append(
                    f"thread {thread.get('id')} has more than 100 comments; nested comments were truncated"
                )
            thread["comments"] = comments.get("nodes", [])
            thread["comment_count"] = comments.get("totalCount", len(thread["comments"]))
            threads.append(thread)
        if not page["pageInfo"]["hasNextPage"]:
            break
        after = page["pageInfo"]["endCursor"]

    if expected_total is not None and len(threads) != expected_total:
        warnings.append(f"expected {expected_total} review threads but collected {len(threads)}")
    return threads, warnings


def check_identity(check: dict[str, Any]) -> str:
    kind = check.get("__typename", "Check")
    if kind == "CheckRun":
        return f"{kind}:{check.get('workflowName', '')}:{check.get('name', '')}"
    return f"{kind}:{check.get('context') or check.get('name', '')}"


def check_time(check: dict[str, Any]) -> str:
    return str(
        check.get("startedAt")
        or check.get("completedAt")
        or check.get("createdAt")
        or check.get("updatedAt")
        or ""
    )


def summarize_checks(checks: list[dict[str, Any]]) -> dict[str, Any]:
    latest_by_identity: dict[str, dict[str, Any]] = {}
    for check in checks:
        identity = check_identity(check)
        previous = latest_by_identity.get(identity)
        if previous is None or check_time(check) >= check_time(previous):
            latest_by_identity[identity] = check

    categories: dict[str, list[dict[str, Any]]] = {
        "successful": [],
        "failing": [],
        "pending": [],
        "cancelled": [],
        "neutral": [],
        "unknown": [],
    }
    failing_conclusions = {"FAILURE", "TIMED_OUT", "ACTION_REQUIRED", "STARTUP_FAILURE", "STALE"}
    neutral_conclusions = {"NEUTRAL", "SKIPPED"}

    for check in latest_by_identity.values():
        kind = check.get("__typename")
        if kind == "StatusContext":
            state = str(check.get("state", "")).upper()
            category = {
                "SUCCESS": "successful",
                "FAILURE": "failing",
                "ERROR": "failing",
                "PENDING": "pending",
                "EXPECTED": "pending",
            }.get(state, "unknown")
        else:
            status = str(check.get("status", "")).upper()
            conclusion = str(check.get("conclusion", "")).upper()
            if status and status != "COMPLETED":
                category = "pending"
            elif conclusion == "SUCCESS":
                category = "successful"
            elif conclusion in failing_conclusions:
                category = "failing"
            elif conclusion == "CANCELLED":
                category = "cancelled"
            elif conclusion in neutral_conclusions:
                category = "neutral"
            elif not conclusion:
                category = "pending"
            else:
                category = "unknown"
        categories[category].append(check)

    for values in categories.values():
        values.sort(key=lambda item: (check_identity(item), check_time(item)))
    return {
        "observed_rollup_entries": len(checks),
        "current_contexts": len(latest_by_identity),
        **categories,
    }


def summarize_threads(threads: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "total": len(threads),
        "unresolved": sum(not thread.get("isResolved", False) for thread in threads),
        "unresolved_current": sum(
            not thread.get("isResolved", False) and not thread.get("isOutdated", False)
            for thread in threads
        ),
        "unresolved_outdated": sum(
            not thread.get("isResolved", False) and thread.get("isOutdated", False)
            for thread in threads
        ),
    }


def collect_one(repo: str, owner: str, repo_name: str, base: dict[str, Any]) -> dict[str, Any]:
    number = int(base["number"])
    details = run_gh(["pr", "view", "-R", repo, str(number), "--json", DETAIL_FIELDS])
    threads, warnings = collect_threads(owner, repo_name, number)
    merged = {**base, **details}
    merged["reviewThreads"] = threads
    merged["thread_summary"] = summarize_threads(threads)
    merged["check_summary"] = summarize_checks(merged.get("statusCheckRollup", []))
    merged["collection_warnings"] = warnings
    return merged


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default="dashpay/dash", help="GitHub repository as OWNER/REPO")
    parser.add_argument("--output", required=True, type=Path, help="Output JSON path")
    parser.add_argument("--limit", type=int, default=500, help="Maximum open PRs to list")
    parser.add_argument("--workers", type=int, default=6, help="Concurrent PR collectors")
    parser.add_argument(
        "--pr",
        action="append",
        type=int,
        default=[],
        help="Collect a specific PR (repeatable; intended for diagnostics)",
    )
    parser.add_argument(
        "--allow-partial",
        action="store_true",
        help="Write partial results and exit successfully when individual PR collection fails",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.limit < 1 or args.workers < 1:
        raise SystemExit("--limit and --workers must be positive")
    owner, repo_name = split_repo(args.repo)

    bases = list_prs(args.repo, args.limit, args.pr)
    hit_list_limit = not args.pr and len(bases) == args.limit
    if hit_list_limit:
        print(
            f"warning: collected exactly --limit={args.limit}; increase the limit to prove complete coverage",
            file=sys.stderr,
        )
    print(f"Collecting detailed evidence for {len(bases)} PRs from {args.repo}...", file=sys.stderr)

    results: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    def safe_collect(base: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        number = base.get("number")
        try:
            pr = collect_one(args.repo, owner, repo_name, base)
            print(f"  collected #{number}", file=sys.stderr)
            return pr, None
        except Exception as exc:  # preserve other PRs so all failures can be reported together
            print(f"  failed #{number}: {exc}", file=sys.stderr)
            return None, {"number": number, "error": str(exc)}

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
        for pr, error in executor.map(safe_collect, bases):
            if pr is not None:
                results.append(pr)
            if error is not None:
                errors.append(error)

    base_numbers = {int(item["number"]) for item in bases}
    result_numbers = {int(item["number"]) for item in results}
    warning_prs = [
        {"number": item["number"], "warnings": item.get("collection_warnings", [])}
        for item in results
        if item.get("collection_warnings")
    ]
    complete = not errors and not warning_prs and not hit_list_limit and result_numbers == base_numbers
    generated_at = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    payload = {
        "schema_version": 1,
        "repository": args.repo,
        "generated_at": generated_at,
        "complete": complete,
        "selected_prs_only": bool(args.pr),
        "listed_pr_count": len(bases),
        "collected_pr_count": len(results),
        "collection_errors": errors,
        "collection_warnings": warning_prs,
        "hit_list_limit": hit_list_limit,
        "pull_requests": sorted(results, key=lambda item: int(item["number"]), reverse=True),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(results)} PRs to {args.output}", file=sys.stderr)

    if not complete and not args.allow_partial:
        print("collection is incomplete; refusing a successful exit", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
