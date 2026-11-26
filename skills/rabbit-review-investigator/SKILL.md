---
name: rabbit-review-investigator
description: Independently verify PR review comments from humans or bots (CodeRabbit, thepastaclaw, Codex) against the codebase before editing code. Use when asked to triage, investigate, or respond to review feedback.
---

# Code Review Investigator

Investigate code review feedback before modifying code. Validate the technical merit of the feedback, adapt the investigation posture based on whether the reviewer is a human or an automated bot, and keep changes tightly focused to prevent PR creep.

## Inputs

Collect:
- The review comment or suggestion text (from a human reviewer or bot)
- File paths, line references, or PR context
- Current repository/branch state and constraints

If file references are missing, search the repository to locate the affected code paths.

## Scope Control & PR Focus

- **Prevent PR Creep:** Address only the specific feedback point. Do not bundle opportunistic refactings, unrelated code formatting, or scope expansions.
- **De-couple Secondary Issues:** If investigating review feedback uncovers a larger unrelated bug or structural issue, document it separately (e.g., as a follow-up issue or distinct PR) rather than expanding the current PR's scope.
- **Minimal Atomic Edits:** Keep diffs as small and targeted as possible to simplify re-review.

## Reviewer Posture & Handling

### 🤖 Automated Bots (CodeRabbit, DeepSource, Linters, AI Bots)
- **Stance:** High skepticism. Bots lack full architectural, consensus, and project-historical context.
- **Workflow:** Trace call paths, data flow, edge cases, and existing test coverage.
- **Classification:** Categorize as:
  - `VALID ISSUE`: The bot identified a genuine bug, defect, or beneficial cleanup.
  - `FALSE POSITIVE`: The suggestion is incorrect, irrelevant, or violates project invariants.
  - `PARTIAL`: The concern has merit, but the bot's proposed fix is flawed or incomplete.
- **Action:** Fix only if verified valid or partially valid with a corrected implementation.

### 👤 Human Reviewers (Maintainers, Teammates, Security Auditors)
- **Stance:** High intent and context respect. Humans bring design vision, team conventions, domain knowledge, and subtle context.
- **Workflow:** Understand *why* the reviewer requested the change (readability, API design, security, maintainability, performance).
- **Handling:**
  - **Agreed Change:** Implement requested changes cleanly while maintaining repository standards and keeping scope tight.
  - **Technical Counterproposal:** If the request has unintended trade-offs, performance regressions, or conflicts with repository constraints, prepare a clear, collaborative explanation presenting the trade-offs and alternative solutions.
  - **Clarification:** If requirements or rationale are ambiguous, outline the options clearly.

## Execution & Git Workflow

- **Minimal Changes:** Keep edits focused strictly on the validated review point.
- **Commit Standards:** Follow local repository commit policies (e.g., GPG signing, conventional commit messages). Do not bypass commit signing flags unless explicitly directed.
- **Verification:** Run relevant unit/functional tests and linters before committing.

## Response Structure

Provide a clear, structured summary:
1. **Source & Assessment:** Identify reviewer source (Human or Bot) and summarize the core claim.
2. **Scope & Investigation Findings:** Detail the code paths examined and confirm the change remains tightly focused.
3. **Outcome / Action Taken:** Explain the changes implemented (with commit info/test results) or the reasoning for declining/proposing an alternative.
