---
name: leaving-pr-comments
description: Required AI attribution footer, /self-reviewed rule, and formatting for every GitHub comment posted on pasta's behalf. Use whenever posting or editing any GitHub PR comment, inline review comment, review, issue comment, or discussion reply (via gh, gh api, or any MCP tool).
---

# Leaving PR Comments

## Attribution

Every GitHub comment posted on pasta's behalf (issue/PR comments, reviews, inline
review comments, discussion replies, via `gh`, `gh api`, or any MCP tool) must
end with this footer, exactly once (when editing a comment that already has it,
keep one copy):

```md
Actual comment.

---
🤖 Posted autonomously by <Harness> (<model-slug>) on behalf of pasta.
```

- `<Harness>` is your harness name: `Claude`, `Codex`, `Cursor`, `Gemini`, or
  `OpenCode`.
- `<model-slug>` is the exact ID of the model you are running as (for example
  `claude-opus-5-5`, `gpt-6.2-astra`, `grok-4.7`, `gemini-4-neon`, or
  `inkling-2-mini`).
- Do not reword the prefix: `pr_wait.py` recognizes our own replies by
  `Posted autonomously by <Harness>`.
- Never add this footer to PR/issue descriptions, commit messages, or code.

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
