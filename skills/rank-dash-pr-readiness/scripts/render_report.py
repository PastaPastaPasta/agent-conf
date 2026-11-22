#!/usr/bin/env python3
"""Validate semantic PR analysis and render a self-contained HTML report."""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse


STAGES = {
    "ready-to-merge": "Ready to merge",
    "final-review": "Final review",
    "review-active": "Review active",
    "needs-author": "Needs author",
    "blocked": "Blocked",
    "draft-or-stale": "Draft or stale",
}
PRIORITIES = {
    "merge-now": "Merge decision",
    "review-now": "Review next",
    "author-action": "Author action",
    "wait": "Wait",
    "low": "Low priority",
}
CONFIDENCE = {"high", "medium", "low"}
APPROVAL_CURRENCY = {"current", "probably-current", "stale", "unclear"}
APPROVAL_SCOPE = {"full", "test-only", "concept-only", "partial", "unclear"}
AUTOMATION_DISPOSITION = {"positive", "negative", "mixed", "superseded"}
BLOCKER_SEVERITY = {"blocking", "likely-blocking", "caveat"}
KNOWN_NONHUMAN = ("coderabbit", "codex", "thepastaclaw", "github-actions", "dependabot")


class ReportError(ValueError):
    pass


def esc(value: Any) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def safe_url(value: Any) -> str:
    if not isinstance(value, str):
        return "#"
    parsed = urlparse(value)
    if parsed.scheme == "https" and parsed.netloc.lower() == "github.com":
        return esc(value)
    return "#"


def require_string(obj: dict[str, Any], field: str, context: str) -> str:
    value = obj.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ReportError(f"{context}.{field} must be a non-empty string")
    return value


def require_list_of_strings(obj: dict[str, Any], field: str, context: str) -> list[str]:
    value = obj.get(field)
    if not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() for item in value):
        raise ReportError(f"{context}.{field} must be a list of non-empty strings")
    return value


def validate_analysis(evidence: dict[str, Any], analysis: dict[str, Any]) -> list[dict[str, Any]]:
    if evidence.get("schema_version") != 1:
        raise ReportError("unsupported evidence schema_version")
    if not evidence.get("complete"):
        raise ReportError("evidence snapshot is incomplete")
    repository = require_string(evidence, "repository", "evidence")
    if require_string(analysis, "repository", "analysis") != repository:
        raise ReportError("analysis.repository does not match evidence.repository")
    evidence_time = require_string(evidence, "generated_at", "evidence")
    if require_string(analysis, "evidence_generated_at", "analysis") != evidence_time:
        raise ReportError("analysis.evidence_generated_at does not match the snapshot")
    require_string(analysis, "analysis_generated_at", "analysis")
    require_string(analysis, "methodology_note", "analysis")
    require_string(analysis, "executive_summary", "analysis")

    evidence_prs = evidence.get("pull_requests")
    analysis_prs = analysis.get("pull_requests")
    if not isinstance(evidence_prs, list) or not isinstance(analysis_prs, list):
        raise ReportError("evidence.pull_requests and analysis.pull_requests must be arrays")
    evidence_numbers = [item.get("number") for item in evidence_prs]
    if any(not isinstance(number, int) for number in evidence_numbers):
        raise ReportError("every evidence PR must have an integer number")
    non_open = [item.get("number") for item in evidence_prs if item.get("state") != "OPEN"]
    if non_open:
        raise ReportError(f"readiness reports may contain only open PRs; non-open={non_open}")

    seen_numbers: list[int] = []
    seen_ranks: list[int] = []
    for index, item in enumerate(analysis_prs):
        context = f"analysis.pull_requests[{index}]"
        if not isinstance(item, dict):
            raise ReportError(f"{context} must be an object")
        number = item.get("number")
        rank = item.get("rank")
        if not isinstance(number, int) or not isinstance(rank, int):
            raise ReportError(f"{context}.number and .rank must be integers")
        seen_numbers.append(number)
        seen_ranks.append(rank)
        if item.get("stage") not in STAGES:
            raise ReportError(f"{context}.stage has an unsupported value")
        if item.get("review_priority") not in PRIORITIES:
            raise ReportError(f"{context}.review_priority has an unsupported value")
        if item.get("confidence") not in CONFIDENCE:
            raise ReportError(f"{context}.confidence has an unsupported value")
        require_string(item, "assessment", context)
        require_string(item, "next_action", context)
        require_list_of_strings(item, "why_here", context)
        require_list_of_strings(item, "caveats", context)

        for collection in ("human_approvals", "automation_signals", "blockers"):
            if not isinstance(item.get(collection), list):
                raise ReportError(f"{context}.{collection} must be an array")
        for approval_index, approval in enumerate(item["human_approvals"]):
            subcontext = f"{context}.human_approvals[{approval_index}]"
            login = require_string(approval, "login", subcontext)
            if login.lower().endswith("[bot]") or any(token in login.lower() for token in KNOWN_NONHUMAN):
                raise ReportError(f"{subcontext} appears automated and cannot be a human approval")
            if approval.get("currency") not in APPROVAL_CURRENCY:
                raise ReportError(f"{subcontext}.currency has an unsupported value")
            if approval.get("scope") not in APPROVAL_SCOPE:
                raise ReportError(f"{subcontext}.scope has an unsupported value")
            require_string(approval, "summary", subcontext)
        for signal_index, signal in enumerate(item["automation_signals"]):
            subcontext = f"{context}.automation_signals[{signal_index}]"
            require_string(signal, "source", subcontext)
            require_string(signal, "summary", subcontext)
            if signal.get("disposition") not in AUTOMATION_DISPOSITION:
                raise ReportError(f"{subcontext}.disposition has an unsupported value")
        for blocker_index, blocker in enumerate(item["blockers"]):
            subcontext = f"{context}.blockers[{blocker_index}]"
            require_string(blocker, "kind", subcontext)
            require_string(blocker, "summary", subcontext)
            if blocker.get("severity") not in BLOCKER_SEVERITY:
                raise ReportError(f"{subcontext}.severity has an unsupported value")

    if len(seen_numbers) != len(set(seen_numbers)):
        raise ReportError("analysis contains duplicate PR numbers")
    if set(seen_numbers) != set(evidence_numbers):
        missing = sorted(set(evidence_numbers) - set(seen_numbers))
        extra = sorted(set(seen_numbers) - set(evidence_numbers))
        raise ReportError(f"analysis coverage mismatch; missing={missing}, extra={extra}")
    expected_ranks = list(range(1, len(analysis_prs) + 1))
    if sorted(seen_ranks) != expected_ranks:
        raise ReportError("ranks must be unique consecutive integers beginning at 1")
    if seen_ranks != expected_ranks:
        raise ReportError("analysis.pull_requests array must be ordered by rank")
    return evidence_prs


def human_approval_summary(approvals: list[dict[str, Any]]) -> str:
    current = sum(item["currency"] in {"current", "probably-current"} for item in approvals)
    if not approvals:
        return "No human ACK recorded"
    return f"{current} current-ish / {len(approvals)} noted human ACK{'s' if len(approvals) != 1 else ''}"


def ci_summary(pr: dict[str, Any]) -> tuple[str, str]:
    checks = pr.get("check_summary", {})
    success = len(checks.get("successful", []))
    failing = len(checks.get("failing", []))
    pending = len(checks.get("pending", []))
    cancelled = len(checks.get("cancelled", []))
    total = checks.get("current_contexts", 0)
    if not total:
        return "CI not observed", "muted"
    text = f"CI {success} pass"
    if failing:
        text += f" · {failing} fail"
    if pending:
        text += f" · {pending} pending"
    if cancelled:
        text += f" · {cancelled} cancelled"
    css = "bad" if failing else "warn" if pending or cancelled else "good"
    return text, css


def compact_text(value: Any, limit: int = 320) -> str:
    text = " ".join(str(value or "").split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def render_linked_item(item: dict[str, Any], text: str, css: str = "") -> str:
    url = safe_url(item.get("url"))
    content = esc(text)
    if url != "#":
        content = f'<a href="{url}" target="_blank" rel="noopener">{content}</a>'
    class_attr = f' class="{esc(css)}"' if css else ""
    return f"<li{class_attr}>{content}</li>"


def render_signal_list(items: list[dict[str, Any]], kind: str) -> str:
    if not items:
        return '<p class="empty">None recorded.</p>'
    parts = ["<ul class=\"evidence-list\">"]
    for item in items:
        if kind == "approval":
            prefix = f"@{item['login']} · {item['currency']} · {item['scope']} — "
            css = f"approval {item['currency']}"
        elif kind == "automation":
            prefix = f"{item['source']} · {item['disposition']} — "
            css = f"automation {item['disposition']}"
        else:
            prefix = f"{item['kind']} · {item['severity']} — "
            css = f"blocker {item['severity']}"
        parts.append(render_linked_item(item, prefix + item["summary"], css))
    parts.append("</ul>")
    return "".join(parts)


def check_name(check: dict[str, Any]) -> str:
    workflow = check.get("workflowName")
    name = check.get("name") or check.get("context") or "Unnamed check"
    return f"{workflow} / {name}" if workflow else str(name)


def check_url(check: dict[str, Any]) -> Any:
    return check.get("detailsUrl") or check.get("targetUrl")


def render_raw_evidence(pr: dict[str, Any]) -> str:
    checks = pr.get("check_summary", {})
    check_items: list[str] = []
    for category in ("failing", "pending", "cancelled", "unknown"):
        for check in checks.get(category, []):
            check_items.append(
                render_linked_item(
                    {"url": check_url(check)},
                    f"{category}: {check_name(check)}",
                    category,
                )
            )
    checks_html = "<ul>" + "".join(check_items) + "</ul>" if check_items else '<p class="empty">No failing, pending, cancelled, or unknown current checks.</p>'

    thread_items: list[str] = []
    for thread in pr.get("reviewThreads", []):
        if thread.get("isResolved"):
            continue
        comments = thread.get("comments", [])
        latest = comments[-1] if comments else {}
        state = "outdated" if thread.get("isOutdated") else "current"
        summary = compact_text(latest.get("body"), 360) or "No comment body collected"
        author = (latest.get("author") or {}).get("login") or "unknown"
        thread_items.append(
            render_linked_item(
                latest,
                f"{state} thread · {thread.get('path', 'unknown path')} · latest @{author}: {summary}",
                "thread",
            )
        )
    threads_html = "<ul>" + "".join(thread_items) + "</ul>" if thread_items else '<p class="empty">No technically unresolved review threads.</p>'

    reviews = sorted(pr.get("reviews", []), key=lambda item: item.get("submittedAt") or "", reverse=True)[:8]
    review_items: list[str] = []
    for review in reviews:
        author = (review.get("author") or {}).get("login") or "unknown"
        body = compact_text(review.get("body"), 180)
        suffix = f": {body}" if body else ""
        review_items.append(
            render_linked_item(
                review,
                f"{review.get('submittedAt', 'unknown time')} · @{author} · {review.get('state', 'UNKNOWN')}{suffix}",
                "review",
            )
        )
    reviews_html = "<ul>" + "".join(review_items) + "</ul>" if review_items else '<p class="empty">No submitted reviews collected.</p>'

    files = pr.get("files", [])
    file_names = [item.get("path") or item.get("name") for item in files if item.get("path") or item.get("name")]
    files_html = esc(", ".join(file_names[:25]))
    if len(file_names) > 25:
        files_html += esc(f" … and {len(file_names) - 25} more")
    if not files_html:
        files_html = "No file list collected."

    return f"""
      <div class="raw-grid">
        <section><h4>Non-green check evidence</h4>{checks_html}</section>
        <section><h4>Technically unresolved threads</h4>{threads_html}</section>
        <section><h4>Recent submitted reviews</h4>{reviews_html}</section>
        <section><h4>Changed files</h4><p class="file-list">{files_html}</p></section>
      </div>
    """


def render_pr_card(item: dict[str, Any], pr: dict[str, Any]) -> str:
    stage = item["stage"]
    priority = item["review_priority"]
    ci_text, ci_class = ci_summary(pr)
    thread_summary = pr.get("thread_summary", {})
    unresolved = thread_summary.get("unresolved_current", 0)
    author = (pr.get("author") or {}).get("login") or "unknown"
    labels = " ".join(label.get("name", "") for label in pr.get("labels", []))
    search = " ".join(
        [
            str(pr.get("number", "")),
            str(pr.get("title", "")),
            author,
            labels,
            item["assessment"],
            item["next_action"],
            stage,
            priority,
        ]
    ).lower()
    why = "".join(f"<li>{esc(reason)}</li>" for reason in item["why_here"])
    caveats = (
        '<div class="caveats"><h4>Caveats</h4><ul>'
        + "".join(f"<li>{esc(value)}</li>" for value in item["caveats"])
        + "</ul></div>"
        if item["caveats"]
        else ""
    )
    draft_badge = '<span class="pill muted">Draft</span>' if pr.get("isDraft") else ""
    labels_html = "".join(f'<span class="label">{esc(label.get("name"))}</span>' for label in pr.get("labels", [])[:6])
    merge_state = pr.get("mergeStateStatus") or "UNKNOWN"
    updated = pr.get("updatedAt") or "unknown"

    return f"""
    <article class="pr-card" data-stage="{esc(stage)}" data-priority="{esc(priority)}" data-search="{esc(search)}">
      <div class="rank" aria-label="Rank {item['rank']}">#{item['rank']}</div>
      <div class="card-main">
        <header class="card-header">
          <div>
            <div class="eyebrow">PR #{pr['number']} · @{esc(author)} · updated {esc(updated)}</div>
            <h2><a href="{safe_url(pr.get('url'))}" target="_blank" rel="noopener">{esc(pr.get('title'))}</a></h2>
          </div>
          <div class="badges">
            <span class="pill stage-{esc(stage)}">{esc(STAGES[stage])}</span>
            <span class="pill priority-{esc(priority)}">{esc(PRIORITIES[priority])}</span>
            <span class="pill confidence">{esc(item['confidence'])} confidence</span>
            {draft_badge}
          </div>
        </header>
        <div class="facts">
          <span class="fact {ci_class}">{esc(ci_text)}</span>
          <span class="fact">{esc(human_approval_summary(item['human_approvals']))}</span>
          <span class="fact {'warn' if unresolved else 'good'}">{unresolved} technically unresolved current thread{'s' if unresolved != 1 else ''}</span>
          <span class="fact">Merge state: {esc(merge_state)}</span>
          <span class="fact">{pr.get('changedFiles', 0)} files · +{pr.get('additions', 0)} / −{pr.get('deletions', 0)}</span>
        </div>
        <div class="labels">{labels_html}</div>
        <div class="assessment-grid">
          <section>
            <h3>Semantic assessment</h3>
            <p>{esc(item['assessment'])}</p>
            <h4>Why it sits here</h4>
            <ul>{why}</ul>
          </section>
          <aside class="next-action">
            <div class="eyebrow">Best next action</div>
            <p>{esc(item['next_action'])}</p>
          </aside>
        </div>
        <div class="signal-grid">
          <section><h4>Human approval interpretation</h4>{render_signal_list(item['human_approvals'], 'approval')}</section>
          <section><h4>Automation / agent signals</h4>{render_signal_list(item['automation_signals'], 'automation')}</section>
          <section><h4>Blockers</h4>{render_signal_list(item['blockers'], 'blocker')}</section>
        </div>
        {caveats}
        <details class="raw-evidence">
          <summary>Inspect collected evidence</summary>
          {render_raw_evidence(pr)}
        </details>
      </div>
    </article>
    """


def render_next_review(items: list[dict[str, Any]], evidence_by_number: dict[int, dict[str, Any]]) -> str:
    candidates = [item for item in items if item["review_priority"] == "review-now"][:6]
    if not candidates:
        return '<p class="empty">No PR is currently a strong “review next” candidate; see merge, author, and wait actions below.</p>'
    cards: list[str] = []
    for item in candidates:
        pr = evidence_by_number[item["number"]]
        cards.append(
            f"""
            <a class="next-card" href="{safe_url(pr.get('url'))}" target="_blank" rel="noopener">
              <span class="mini-rank">Rank {item['rank']}</span>
              <strong>#{pr['number']} {esc(pr.get('title'))}</strong>
              <span>{esc(item['next_action'])}</span>
            </a>
            """
        )
    return "".join(cards)


def count_by(items: Iterable[dict[str, Any]], field: str, value: str) -> int:
    return sum(item.get(field) == value for item in items)


def build_html(evidence: dict[str, Any], analysis: dict[str, Any]) -> str:
    evidence_prs = validate_analysis(evidence, analysis)
    evidence_by_number = {item["number"]: item for item in evidence_prs}
    items = analysis["pull_requests"]
    cards = "".join(render_pr_card(item, evidence_by_number[item["number"]]) for item in items)
    next_reviews = render_next_review(items, evidence_by_number)
    stage_options = "".join(f'<option value="{esc(key)}">{esc(label)}</option>' for key, label in STAGES.items())
    priority_options = "".join(f'<option value="{esc(key)}">{esc(label)}</option>' for key, label in PRIORITIES.items())
    ready_count = count_by(items, "stage", "ready-to-merge")
    review_count = count_by(items, "review_priority", "review-now")
    author_count = count_by(items, "review_priority", "author-action")
    blocked_count = count_by(items, "stage", "blocked")
    rendered_at = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Dash Core PR merge readiness</title>
  <style>
    :root {{ --ink:#18211d; --muted:#65726b; --paper:#f5f3ec; --card:#fffef9; --line:#d9ddd5; --green:#176b4b; --green-bg:#e1f1e7; --amber:#8a5b12; --amber-bg:#fff0cc; --red:#9b3a32; --red-bg:#f9e1dc; --blue:#1b5e8a; --blue-bg:#dcecf7; --violet:#66508d; --violet-bg:#ede6f7; --shadow:0 12px 34px rgba(31,42,36,.08); }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; color:var(--ink); background:radial-gradient(circle at top right,#dcece1 0,transparent 32rem),var(--paper); font:15px/1.55 ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; }}
    a {{ color:inherit; text-decoration-color:#9ca9a1; text-underline-offset:3px; }}
    .shell {{ width:min(1500px,calc(100% - 36px)); margin:0 auto; }}
    .hero {{ padding:58px 0 28px; }}
    .hero-grid {{ display:grid; grid-template-columns:minmax(0,1.65fr) minmax(280px,.65fr); gap:36px; align-items:end; }}
    .kicker,.eyebrow {{ color:var(--muted); font-size:.75rem; font-weight:750; letter-spacing:.09em; text-transform:uppercase; }}
    h1 {{ margin:.15em 0; font-family:Georgia,"Times New Roman",serif; font-size:clamp(2.7rem,7vw,6.4rem); line-height:.91; letter-spacing:-.055em; font-weight:500; max-width:950px; }}
    .lede {{ max-width:850px; font-size:1.08rem; color:#39453f; }}
    .snapshot {{ border-left:1px solid var(--line); padding-left:24px; color:var(--muted); }}
    .snapshot strong {{ color:var(--ink); display:block; margin:.25rem 0 .8rem; }}
    .stats {{ display:grid; grid-template-columns:repeat(4,1fr); gap:12px; margin:24px 0; }}
    .stat {{ padding:18px; border:1px solid var(--line); border-radius:14px; background:rgba(255,254,249,.65); }}
    .stat strong {{ display:block; font:600 2rem/1 Georgia,serif; margin-bottom:5px; }}
    .brief {{ display:grid; grid-template-columns:minmax(0,1.1fr) minmax(300px,.9fr); gap:18px; margin:28px 0 34px; }}
    .brief > section {{ background:var(--card); border:1px solid var(--line); border-radius:18px; padding:22px; box-shadow:var(--shadow); }}
    .brief h2 {{ margin:0 0 8px; font:500 1.6rem Georgia,serif; }}
    .method {{ color:var(--muted); border-top:1px solid var(--line); padding-top:12px; margin-top:14px; }}
    .next-list {{ display:grid; gap:9px; }}
    .next-card {{ display:grid; gap:4px; padding:11px 13px; border:1px solid var(--line); border-radius:11px; text-decoration:none; background:#fbfcf8; }}
    .next-card:hover {{ border-color:#92aa9c; transform:translateY(-1px); }}
    .next-card span:last-child {{ color:var(--muted); font-size:.9rem; }}
    .mini-rank {{ color:var(--green); font-size:.72rem; font-weight:800; text-transform:uppercase; letter-spacing:.07em; }}
    .toolbar {{ position:sticky; top:0; z-index:20; display:grid; grid-template-columns:minmax(220px,1fr) 210px 210px auto; gap:10px; padding:12px; background:rgba(245,243,236,.9); border:1px solid var(--line); border-radius:14px; backdrop-filter:blur(14px); box-shadow:0 7px 22px rgba(31,42,36,.07); }}
    input,select {{ min-width:0; border:1px solid #cbd1ca; background:var(--card); border-radius:9px; padding:10px 12px; color:var(--ink); font:inherit; }}
    #visible-count {{ display:grid; place-items:center; color:var(--muted); white-space:nowrap; padding:0 8px; }}
    .ranking {{ display:grid; gap:16px; padding:22px 0 70px; }}
    .pr-card {{ display:grid; grid-template-columns:66px 1fr; background:var(--card); border:1px solid var(--line); border-radius:18px; overflow:hidden; box-shadow:var(--shadow); }}
    .pr-card[hidden] {{ display:none; }}
    .rank {{ padding:25px 10px; text-align:center; font:600 1.25rem Georgia,serif; background:#edf0e9; border-right:1px solid var(--line); color:#3d4b43; }}
    .card-main {{ min-width:0; padding:23px 25px; }}
    .card-header {{ display:flex; justify-content:space-between; gap:22px; align-items:flex-start; }}
    .card-header h2 {{ margin:4px 0 0; font:500 clamp(1.25rem,2.5vw,1.75rem)/1.2 Georgia,serif; }}
    .badges,.facts,.labels {{ display:flex; flex-wrap:wrap; gap:7px; }}
    .badges {{ justify-content:flex-end; max-width:510px; }}
    .pill,.fact,.label {{ border-radius:999px; padding:5px 9px; font-size:.77rem; font-weight:700; white-space:nowrap; }}
    .pill {{ border:1px solid transparent; }}
    .stage-ready-to-merge,.priority-merge-now,.good {{ color:var(--green); background:var(--green-bg); }}
    .stage-final-review,.priority-review-now {{ color:var(--blue); background:var(--blue-bg); }}
    .stage-review-active {{ color:var(--violet); background:var(--violet-bg); }}
    .stage-needs-author,.priority-author-action,.warn {{ color:var(--amber); background:var(--amber-bg); }}
    .stage-blocked,.priority-wait,.bad {{ color:var(--red); background:var(--red-bg); }}
    .stage-draft-or-stale,.priority-low,.muted,.confidence {{ color:#56615b; background:#eaede8; }}
    .facts {{ margin-top:15px; }}
    .fact {{ background:#eff1ed; font-weight:650; }}
    .labels {{ margin-top:8px; }} .label {{ color:#536059; border:1px solid var(--line); padding:3px 8px; font-weight:600; }}
    .assessment-grid {{ display:grid; grid-template-columns:minmax(0,1fr) minmax(250px,.38fr); gap:24px; margin-top:22px; }}
    h3,h4 {{ margin:0 0 7px; }} h3 {{ font-size:1rem; }} h4 {{ color:#4c5952; font-size:.82rem; text-transform:uppercase; letter-spacing:.04em; }}
    p {{ margin:7px 0 12px; }} ul {{ margin:7px 0; padding-left:20px; }}
    .next-action {{ align-self:start; padding:17px; border-radius:13px; background:#edf3ed; border-left:4px solid var(--green); }}
    .next-action p {{ margin:6px 0 0; font-weight:650; }}
    .signal-grid {{ display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:14px; margin-top:20px; }}
    .signal-grid > section,.caveats {{ border-top:1px solid var(--line); padding-top:13px; }}
    .evidence-list {{ list-style:none; padding:0; font-size:.9rem; }}
    .evidence-list li {{ margin:6px 0; padding-left:11px; border-left:3px solid var(--line); }}
    .evidence-list .positive,.evidence-list .current,.evidence-list .probably-current {{ border-color:var(--green); }}
    .evidence-list .negative,.evidence-list .blocking {{ border-color:var(--red); }}
    .evidence-list .mixed,.evidence-list .likely-blocking,.evidence-list .unclear {{ border-color:#d7a84c; }}
    .empty {{ color:var(--muted); font-style:italic; }}
    .raw-evidence {{ margin-top:18px; border-top:1px solid var(--line); padding-top:13px; }}
    summary {{ cursor:pointer; color:#48564e; font-weight:700; }}
    .raw-grid {{ display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:16px; margin-top:14px; font-size:.84rem; }}
    .raw-grid section {{ background:#f5f6f2; border-radius:11px; padding:13px; min-width:0; }}
    .raw-grid ul {{ overflow-wrap:anywhere; }} .file-list {{ overflow-wrap:anywhere; }}
    footer {{ color:var(--muted); padding:0 0 45px; }}
    @media (max-width:950px) {{ .hero-grid,.brief,.assessment-grid {{ grid-template-columns:1fr; }} .snapshot {{ border-left:0; border-top:1px solid var(--line); padding:18px 0 0; }} .stats {{ grid-template-columns:repeat(2,1fr); }} .toolbar {{ grid-template-columns:1fr 1fr; }} .signal-grid {{ grid-template-columns:1fr; }} .card-header {{ display:block; }} .badges {{ justify-content:flex-start; margin-top:12px; }} }}
    @media (max-width:620px) {{ .shell {{ width:min(100% - 20px,1500px); }} .hero {{ padding-top:34px; }} .stats,.toolbar,.raw-grid {{ grid-template-columns:1fr; }} .toolbar {{ position:relative; }} .pr-card {{ grid-template-columns:1fr; }} .rank {{ border-right:0; border-bottom:1px solid var(--line); text-align:left; padding:9px 18px; }} .card-main {{ padding:18px; }} .facts {{ align-items:flex-start; flex-direction:column; }} }}
    @media print {{ body {{ background:#fff; }} .toolbar {{ display:none; }} .pr-card {{ break-inside:avoid; box-shadow:none; }} .raw-evidence {{ display:none; }} }}
  </style>
</head>
<body>
  <main class="shell">
    <section class="hero">
      <div class="hero-grid">
        <div>
          <div class="kicker">dashpay/dash · maintainer intelligence</div>
          <h1>Merge readiness,<br>with the conversation intact.</h1>
          <p class="lede">Every open Dash Core pull request, ordered by semantic distance to merge. Approval counts, CI, threads, risk, recency, and reviewer intent are evidence—not a formula.</p>
        </div>
        <div class="snapshot">
          <span>Evidence snapshot</span><strong>{esc(evidence['generated_at'])}</strong>
          <span>Semantic analysis</span><strong>{esc(analysis['analysis_generated_at'])}</strong>
          <span>{len(items)} open pull requests assessed</span>
        </div>
      </div>
      <div class="stats">
        <div class="stat"><strong>{ready_count}</strong>ready to merge</div>
        <div class="stat"><strong>{review_count}</strong>worth reviewing next</div>
        <div class="stat"><strong>{author_count}</strong>need author action</div>
        <div class="stat"><strong>{blocked_count}</strong>blocked</div>
      </div>
      <div class="brief">
        <section><h2>Queue reading</h2><p>{esc(analysis['executive_summary'])}</p><p class="method"><strong>Method:</strong> {esc(analysis['methodology_note'])}</p></section>
        <section><h2>Best next reviews</h2><div class="next-list">{next_reviews}</div></section>
      </div>
    </section>
    <nav class="toolbar" aria-label="Report filters">
      <input id="search" type="search" placeholder="Search PR, author, label, assessment…" aria-label="Search report">
      <select id="stage"><option value="">All readiness stages</option>{stage_options}</select>
      <select id="priority"><option value="">All next actions</option>{priority_options}</select>
      <span id="visible-count">{len(items)} shown</span>
    </nav>
    <section class="ranking" id="ranking">{cards}</section>
  </main>
  <footer class="shell">Rendered {esc(rendered_at)} from a point-in-time GitHub snapshot. Re-run the skill before acting on stale evidence.</footer>
  <script>
    const cards = [...document.querySelectorAll('.pr-card')];
    const search = document.querySelector('#search');
    const stage = document.querySelector('#stage');
    const priority = document.querySelector('#priority');
    const count = document.querySelector('#visible-count');
    function filterCards() {{
      const query = search.value.trim().toLowerCase();
      let visible = 0;
      for (const card of cards) {{
        const show = (!query || card.dataset.search.includes(query)) && (!stage.value || card.dataset.stage === stage.value) && (!priority.value || card.dataset.priority === priority.value);
        card.hidden = !show;
        if (show) visible += 1;
      }}
      count.textContent = `${{visible}} shown`;
    }}
    search.addEventListener('input', filterCards);
    stage.addEventListener('change', filterCards);
    priority.addEventListener('change', filterCards);
  </script>
</body>
</html>
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", required=True, type=Path)
    parser.add_argument("--analysis", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReportError(f"cannot read {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ReportError(f"{path} must contain a JSON object")
    return value


def main() -> int:
    args = parse_args()
    evidence = load_json(args.evidence)
    analysis = load_json(args.analysis)
    output = build_html(evidence, analysis)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(output, encoding="utf-8")
    print(f"Rendered {len(analysis['pull_requests'])} ranked PRs to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
