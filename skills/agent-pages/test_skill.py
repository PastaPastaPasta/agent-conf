"""The agent-pages skill stays registered and keeps the publish contract."""
import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[2]
SKILL = pathlib.Path(__file__).resolve().parent / "SKILL.md"
text = SKILL.read_text()
meta, body = text.split("---", 2)[1:]

def field(name):
    match = re.search(rf"^{name}: (.+)$", meta, re.M)
    assert match, name
    return match.group(1)

assert field("name") == "agent-pages"
description = field("description")
assert description.startswith("Publish ")
assert "Use when " in description
assert "harness-hosted artifacts or canvases (e.g. claude.ai artifacts)" in description

manifest = json.loads((ROOT / "skills.json").read_text())
assert manifest["agent-pages"] == {}, manifest["agent-pages"]

for phrase in (
    "PastaPastaPasta/agent-pages",
    "https://pastapastapasta.github.io/agent-pages/",
    "This skill takes precedence",
    "The site is public",
    "Publish only what is already public knowledge",
    "public forever",
    "Do not put it on a branch",
    "`fleet` skill",
    "home-directory paths",
    "memory notes or transcripts",
    "<!doctype html>",
    '<meta charset="utf-8">',
    '<meta name="viewport" content="width=device-width, initial-scale=1">',
    "<title>",
    "index.html",
    '<li><a href="slug.html">Title</a><span class="date">YYYY-MM-DD</span>',
    ".nojekyll",
    ".DS_Store",
    "ahead of `origin/main`",
    "slug/index.html",
    "one row per URL",
    "git pull --rebase",
    "Never `git add -A`",
    "git push origin main",
    "git rebase --abort",
    "Never force-push",
    "If signing fails, stop and tell the user",
    "capture-visual-evidence",
    "feat: publish",
    "gh repo clone",
    "?v=",
    "pending",
):
    assert phrase in text, phrase

print("agent-pages skill contract ok")
