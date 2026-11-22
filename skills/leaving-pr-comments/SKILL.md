---
name: leaving-pr-comments
description: Use whenever leaving comments on GitHub (PR comments, inline review comments, replies to bots or reviewers, reviews, issue comments) so they carry the right attribution and read well.
---

# Leaving PR Comments

## Attribution

Every comment posted as **PastaPastaPasta** ends with the footer from your global
instructions (CLAUDE.md, AGENTS.md, GEMINI.md, or the Cursor global workflow rule),
exactly once:

```md
Actual comment.

---
🤖 Posted autonomously by Claude (<model-slug>) on behalf of pasta.
```

`<model-slug>` is the exact ID of the model you are running as, such as
`claude-fable-5-2`. Other
harnesses use the same footer with their own name in place of `Claude`
(`Codex`, `Cursor`, or `Gemini`, per their global instructions). Do not reword
it otherwise; `pr_wait.py` recognizes our own replies by the
`Posted autonomously by <Harness>` prefix.

Comments posted through the **thepastaclaw** account get no footer: the bot
account already says it is automated. Text the user asked to post verbatim
gets no footer either, and neither do PR descriptions or commit messages.

`/self-reviewed` gets no footer. pasta allows agents to post it. The PR Hygiene
bot (`dashpay/stale_prs_are_bad`) runs `fullmatch` on the stripped body, so the
comment must be exactly `/self-reviewed` or `/self-reviewed <40-hex head sha>`.
It also skips edited comments: if one went out with a footer, delete it and
post a new bare one; don't edit it.

## Writing

- Lead with the conclusion.
- Cite the code (`file:line`), behavior, check or reproduction behind it.
- Keep it short: no filler, canned thanks, or status narration.
- Keep verified facts apart from judgment.
- When declining a finding, give the reason in one or two sentences.
- No internal review notes (council, scores, review rounds, model names) beyond
  the footer's model slug.

Before posting, check the whole comment, including quoted text and
attachments, for secrets and private details. Describe where you tested
generically ("a synced mainnet node"), never by our machine names (strixbox,
Mac Studio, CT numbers); see `file-pr`. Preview the Markdown so quotes
and blank lines render as intended. After posting, confirm GitHub returned the
comment or review URL. Resolve a review thread only after its reply has posted.
