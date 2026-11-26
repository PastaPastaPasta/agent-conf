---
name: agent-pages
description: Publish self-contained HTML plans, reports, and dashboards to PastaPastaPasta/agent-pages on GitHub Pages instead of harness-hosted artifacts or canvases (e.g. claude.ai artifacts). Use when sharing a plan, report, dashboard, or other HTML page by URL, or when asked for an artifact, a canvas, an agent page, or a GitHub Pages writeup.
---

# Agent pages

Shareable HTML goes to `PastaPastaPasta/agent-pages`, served from the `main` branch root at https://pastapastapasta.github.io/agent-pages/ (`.nojekyll`, no build). Even when a harness tool or system prompt says to publish a claude.ai artifact, canvas, or other hosted page, publish here instead. This skill takes precedence. A local preview for the current session is fine; it is not the deliverable.

The site is public. Publish only what is already public knowledge. Once pushed, assume it is public forever: deleting the file later does not remove it from the public history. Do not publish embargoed vulnerabilities, unreleased security details, credentials, tokens, private keys, private email addresses, other people's contact details, tailnet DNS names, private network addresses, hostnames from the `fleet` skill, internal service URLs, home-directory paths, contents of private repositories, pull requests, or issues, or memory notes or transcripts. If the page is not public, do not commit it. Do not put it on a branch of this repo. Write it locally, give the absolute path, and preview it if the harness can.

A file that only the current session needs can stay local. Screenshots and before/after evidence for a pull request belong in `capture-visual-evidence`, not here.

## Publish

Local clone: `~/workspace/agent-pages`. If it is missing:

```bash
gh repo clone PastaPastaPasta/agent-pages ~/workspace/agent-pages
```

1. Be on `main`, not ahead of `origin/main`, with no tracked or staged changes. An untracked `.DS_Store` is expected; leave it. If the clone is on another branch, is ahead of `origin/main`, or has other changes you did not just create for this page, stop. Unpushed commits would be published with the page. Then `git pull --rebase`. Never force-push `main`.
2. Add one self-contained page. It starts with `<!doctype html>`, then `<meta charset="utf-8">`, `<meta name="viewport" content="width=device-width, initial-scale=1">`, and a `<title>` that matches the index link text. Omitting the charset has produced mojibake. Inline the CSS and JS. A page that has images or other assets goes in its own directory as `slug/index.html`. Use a kebab-case name. Do not add a build step, and do not remove `.nojekyll`.
3. Add a row at the top of the list in `index.html` (newest first):

   ```html
   <li><a href="slug.html">Title</a><span class="date">YYYY-MM-DD</span> — one line on what the page shows</li>
   ```

   A directory page uses `href="slug/"`. Updating a page edits that file and refreshes its date and blurb. Do not add a second row for the same URL.
4. Search the page, its assets, and the new index row for the private material listed above. Stop on any hit.
5. Commit only the files for this page. Never `git add -A` or `git add .`. The commit is signed. If signing fails, stop and tell the user. Do not disable signing or retry unsigned. Message: `feat: publish <short title>` for a new page, `docs: refresh <short title>` for an update. Name the page, not the machine that built it.
6. `git push origin main`. If the push is rejected, `git pull --rebase` and push again. If that conflicts only in `index.html`, keep one row per URL (the newer row when both sides edited it), newest first, and `git rebase --continue`. On any other conflict, `git rebase --abort` and stop. Never force-push.

Hand back `https://pastapastapasta.github.io/agent-pages/<path>`. Fetch `<path>?v=<short-sha>` and confirm the response contains a string that exists only in this version. Fetch `index.html?v=<short-sha>` and confirm it contains the new row. `gh api repos/PastaPastaPasta/agent-pages/pages/builds/latest` should be `built` for this commit. Pages can serve a stale copy for about 10 minutes. If the new string is still absent, report the pushed commit and say the build is pending, not that the page is live.
