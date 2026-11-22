---
name: platform-explorer-api
description: Work with the Dash Platform Explorer REST API documented at platform-explorer.com and exposed on the live host platform-explorer.pshenmic.dev. Use when Codex needs to discover the explorer API, choose endpoints for network status, validators, blocks, transactions, identities, DPNS aliases, or data contracts, verify whether a route is live, and produce curl, JavaScript, or integration examples against the explorer.
---

# Platform Explorer API

Use the explorer docs site to discover routes, but treat the live API host as the source of truth for callable requests.

## Quick Start

1. Distinguish docs from API traffic.
- Docs UI: `https://platform-explorer.com/api`
- Live API base: `https://platform-explorer.pshenmic.dev`

2. Probe the API before writing code.
- Start with `GET /status`.
- For collection routes, request a small page such as `?page=1&limit=1` when supported.
- If a route is only mentioned in older public notes, verify it live before relying on it.

3. Load the detailed route catalog when needed.
- Read [api-reference.md](./references/api-reference.md) for:
  - verified routes and example payloads
  - older documented routes that may have drifted
  - ready-to-use curl and JavaScript snippets

## Workflow

1. Identify the user goal.
- Network health or version info: use `/status`
- Free-form lookup by alias or keyword: use `/search`
- Platform entity lists and details: use the matching collection and item route
- Schema inspection: use `/dataContract/:id`

2. Prefer a two-step lookup.
- Use a collection or `/search` route to discover IDs and hashes.
- Follow with the item route for the full record.

3. Report route confidence explicitly.
- `verified live` if you tested it against `platform-explorer.pshenmic.dev`
- `documented but unverified` if it only appears in public route lists
- `currently failing` if the live host returns 404 or server errors

4. Preserve raw identifiers exactly.
- Do not normalize case in hashes, IDs, or `proTxHash` values.
- Keep large numeric values as strings unless the client explicitly handles bigint-sized values.

## Response Patterns

- `/status` returns a single object with network, block, version, and indexer health data.
- Most list routes return `{ "resultSet": [...], "pagination": { ... } }`.
- `/search` can return a keyed object such as `{ "identities": [...] }`.
- Item routes return a single JSON object.

## Guardrails

- Do not call `https://platform-explorer.com/api/...` as if it were the REST base; that host serves the docs UI.
- Expect drift between the published route list and the live deployment.
- Validate questionable routes with a small live request before promising them to the user.
- Mention date-sensitive validation when summarizing results.
- If a route returns `404` or a server error, offer the closest verified alternative instead of assuming the docs are wrong or the host is down.

## Output Style

When answering with this skill:

- Name the exact base URL you used.
- Show the exact route and query string.
- Include one minimal working example first.
- Note whether the route was verified live or only documented.
