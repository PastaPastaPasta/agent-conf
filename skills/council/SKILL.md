---
name: council
description: Run a multi-model design council where independent frontier models review a proposal and must reach consensus. Use when the user says 'council' or for critical consensus, security, or protocol design decisions.
---

# Council

## Members

Check the `limits` skill, call `orchestrator_capabilities`, then start the three seats `limits` lists with `delegate_task`, in parallel, `mode: "async"`. When every subscription has room they are:

| Seat | Provider | Model | Options |
| --- | --- | --- | --- |
| Opus | `claudeAgent` | `claude-opus-5-5` | `effort: high` |
| Astra | `codex` | `gpt-6.2-astra` | `reasoningEffort: high` |
| Muse | `muse` | `muse-wonder-full-1.0` | `effort: high` |

- When OpenAI or Muse is DEFICIT, CRITICAL or UNKNOWN, Fable 5.2 high (`claudeAgent`, `claude-fable-5-2`) takes that seat — check `claude_fable` in `limits` first so you don't route into an exhausted Fable sub-limit.
- A council always has an Anthropic seat and models from at least two providers. When Astra and Muse are both short, the less short of them keeps its seat, so the council is Opus, Fable and that one. Never run an all-Claude council.
- If `limits` lists no council, stop and report it. If `limits` is unreachable or stale, use the default table above (Opus + Astra + Muse) rather than swapping non-Claude seats to Fable.

Use exactly these seats at these efforts. If one is unavailable or errors twice, stop and report it.

## Brief

Give each member the same brief: goal, constraints, relevant files or diff command, and what is out of scope. Leave out your own proposal. Members stay read-only: no edits, commits, pushes, PR comments or subagents.

## Rounds

1. Round 1: each member proposes a design, or reviews the change with findings (blocker, should, nit) and a score out of 10.
2. Merge the results into one design or one set of fixes. Send it, with every open objection, to all three, each in a fresh `delegate_task`. That is the next round.
3. Each member replies `AGREE` or `OBJECT: <reason>`, plus a score for reviews. Revise and repeat.
4. Done when all three reply `AGREE` to the same version. A missing reply is not agreement.
5. After three rounds without agreement, stop and report each open disagreement with every member's position.

## Report

Give the result, the number of rounds, each member's scores and any open disagreements in your final reply to the user, and nowhere else. Never put council results in a PR description, PR comment or commit message.

## Scope

Rare paths, small performance costs, extra compatibility and "while you're here" ideas are nits. Decline them in one line and list them as follow-ups.
