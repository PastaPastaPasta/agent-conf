---
name: model-choice
description: Pick the model and effort for any subagent, delegation, review, council or text-generation call. Use every time you spawn a subagent (Claude Agent tool, T3 delegate_task), start a reviewer, or hand work to another model.
---

# Model Choice

Set model and effort on every delegation.

- Claude Code: Claude models through the Agent tool (`model`, `effort`) or `delegate_task` (provider `claudeAgent`, `effort`).
- Everyone else, and any non-Claude model: T3 `delegate_task`, using the provider names `limits` gives: `claudeAgent` with `effort` for Claude models, `codex` with `reasoningEffort` for GPT models, `antigravity` with `thought_level` for Gemini, `muse`, `grok` or `cursor` otherwise.

## Routing

- Check the `limits` skill when you launch a lane, not on every turn. Its routing says which subscription takes implementation and who sits on reviews and councils. If it is unreachable or stale, do not wait: follow its fallback (Claude STABLE, everything else UNKNOWN).
- A long-running manager is a persistent thread that coordinates other threads or owns a product or queue over many hours or days (parity/desktop managers, the Radar coordinator, backportsys, campaign/readiness owners, overnight watchers, landing/queue triagers). It is not a one-shot task thread working on a single PR, review or bug. When Claude is CRITICAL, managers finish their current step, keep anything security, release, or explicitly requested by pasta moving, and otherwise stop launching new non-critical work until the state recovers.
- Judgement and design always run on the Claude subscription: easy -> Opus 5.5 (`claude-opus-5-5`) medium; normal -> Opus 5.5 high; harder -> Fable 5.2 (`claude-fable-5-2`) medium; hardest -> Fable 5.2 high.
- Implementation on Claude: easy and normal -> Opus 5.5 medium; hard and hardest -> Opus 5.5 high.
- Where implementation goes depends on Claude's state in `limits`:
  - EXCESS: everything except reviews and councils stays on Claude, even when other subscriptions are in excess too.
  - STABLE: easy implementation moves to a subscription in EXCESS, and only if one is: GPT 6.2 Astra (`gpt-6.2-astra`) high, Muse Wonder full (`muse-wonder-full-1.0`) high, Grok 4.7 (`grok-4.7`) high, or Gemini 4 Neon (`gemini-4-neon`, provider `antigravity`) high.
  - LIMITED: all implementation except the hardest moves to a subscription in EXCESS or STABLE.
  - DEFICIT: long-running managers pause non-critical work. Implementation continues on other subscriptions; non-critical work blocked on design or judgement waits.
  - CRITICAL: as DEFICIT, but nearly all work pauses.
- Grok and Gemini take only easy or normal implementation: never hard implementation, judgement or management. Gemini means Gemini 4 Neon through Antigravity; never Gemini 4 Carbon, and never Gemini through Cursor. Cursor is only for Grok models; never run Opus, Gemini or anything else through it. Never run Opus through Antigravity. Never grok-4.7 through the CLI proxy (Codex provider).
- A review is one reviewer, preferably from another model family than the author: Astra high, else Opus 5.5 high when OpenAI is DEFICIT or CRITICAL, else Muse Wonder full high when Claude is too. Never Sonnet as a reviewer. `limits` names the reviewer.
- Critical design (consensus, security, protocol), or when pasta says "council" -> `council` skill.
- Codebase search -> `Explore` subagent (Haiku), in Claude Code.
- Titles and other text generation -> Luna (`gpt-6-luna`), low.

## Effort

- Before raising effort or model, give the agent a way to check its work: a test, build or script.
- Never use effort above high unless the user asks for it.
- Do not use Astra for anything that needs discretion or judgment, except inside a council or when the user asks for it (e.g. `sol loop`).
