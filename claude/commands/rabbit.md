# Code Review Investigation

You have received code review feedback (from a human reviewer or an automated tool like CodeRabbit). Your task is to **investigate** the feedback before making code changes, while strictly preserving PR focus and avoiding scope creep.

## The Review Feedback

$ARGUMENTS

---

## Scope Control & PR Focus

- **Prevent PR Creep:** Focus exclusively on addressing the requested review point. Do not add unrelated cleanups, formatting tweaks, or additional features.
- **Isolate Secondary Issues:** If resolving feedback reveals a separate bug or technical debt, log or flag it for a separate PR rather than expanding the scope of this PR.
- **Keep Diffs Minimal:** Prefer narrow, precise changes that are easy for reviewers to verify.

---

## Mission & Workflow

Validate the review feedback thoroughly before taking action. Adjust your approach based on the source of the review:

### 🤖 Automated Bots (CodeRabbit, Linters, AI Tools)
- **Skeptical Verification:** Bots frequently misinterpret context, generate false positives, or propose suboptimal fixes.
- **Trace the Code:** Inspect callers, callees, edge cases, and repo invariants.
- **Classify:**
  - **VALID ISSUE:** Real problem identified; implement minimal fix.
  - **FALSE POSITIVE:** Incorrect or unnecessary; do not make changes, explain why.
  - **PARTIAL:** Valid concern, but bot's fix is wrong; implement the correct alternative.

### 👤 Human Reviewers (Maintainers, Teammates, Auditors)
- **Presume Intent & Context:** Humans bring domain expertise, architectural vision, and team standards.
- **Understand the Rationale:** Determine whether the comment concerns correctness, maintainability, readability, or design patterns.
- **Determine Next Step:**
  - **Implement:** Make the requested change cleanly and concisely.
  - **Discuss/Alternative:** If the suggestion introduces trade-offs, regressions, or conflicts with repo constraints, articulate a clear, respectful technical rationale and alternative proposal.

---

## Quality & Repository Standards

- Follow repository commit conventions (including GPG signing rules where required).
- Run affected unit tests and linters before finalizing changes.
- Keep changes strictly scoped to the review feedback.
