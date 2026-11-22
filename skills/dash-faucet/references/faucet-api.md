# Faucet API reference

`faucet.thepasta.org` and `faucet.dashhq.org` serve the same Cloudflare Worker
from `PastaPastaPasta/dash-faucet-cf`. The README and `src/index.ts` are the
authoritative API specification. There is no `/openapi.json`.

## Routes

| Route | Purpose |
|---|---|
| `GET /health` | liveness |
| `GET /api/status` | balance, limits, captcha endpoints |
| `POST /cap/v1/challenge`, `/cap/v1/redeem` | soft proof of work (native clients) |
| `POST /cap/hard/challenge`, `/cap/hard/redeem` | hard proof of work (browser only) |
| `POST /api/core-faucet` | send testnet tDASH to an address |
| `POST /api/invitation-faucet` | mainnet identity invitations; Turnstile only, not for agents |

`/api/asset-lock-proof` and `/api/faucet` (identity packages) no longer exist;
they return 404.

## Status

```json
{
  "status": "ok", "network": "testnet", "balance": 16878.94608668,
  "coreFaucetAmount": 1, "rateLimitPerHour": 3,
  "rateLimits": { "soft": 3, "turnstile": 10, "hard": 25 },
  "capEndpoint": "https://faucet.thepasta.org/cap/v1/",
  "hardCapEndpoint": "https://faucet.thepasta.org/cap/hard/",
  "spentTodaySats": 300000000, "dailyBudgetSats": 100000000000,
  "amountLimits": {
    "turnstileAbove": 10, "publicMax": 100,
    "signedInMax": 5000, "perIpDaily": 100
  },
  "accountUrl": "https://faucet.dashhq.org/keys",
  "apiKeysEnabled": true,
  "providers": [{ "name": "insight", "ok": true, "height": 1588867, "error": null }]
}
```

`amountLimits` values are DASH. At or below `turnstileAbove`, either Turnstile
or the soft cap.js proof of work is sufficient. Above it and through
`publicMax`, Turnstile is required. Above `publicMax`, an API key, a dash.org
signed-in session, or a code is required. `signedInMax` is the signed-in
per-request ceiling; `perIpDaily` is the rolling 24-hour captcha-path allowance
for one IP, or `null` when disabled. `spentTodaySats` and `dailyBudgetSats` are
duffs. A `503` with `status: "low_balance"` means wait.

## Core faucet

`POST /api/core-faucet` accepts a JSON object with:

| Field | Meaning |
|---|---|
| `address` | required testnet P2PKH address (`y...`) |
| `amount` | optional DASH amount, at least `0.001`, at most 8 decimals; unkeyed requests are paid exactly this amount |
| `capToken` | single-use soft proof-of-work token from `/cap/v1/redeem` |
| `turnstileToken` | browser Turnstile token |
| `hardCapToken` | alias for `capToken`, accepted for old web clients |
| `code` / `promoCode` | admin-issued redemption code; captcha is still required |

Without `amount`, the payout is `coreFaucetAmount`. An unkeyed proof-of-work
client can ask through `amountLimits.turnstileAbove`; a larger ask needs
Turnstile, and an ask above `amountLimits.publicMax` needs a dash.org sign-in or
a code. The same address returns its first transaction with `replay: true` for
the rest of the UTC day. Ordinary unkeyed captcha-path payouts count the
requested amount against the per-IP allowance, the global `dailyBudgetSats`,
and (for asks above `turnstileAbove`) the smaller large-request share of that
budget. A code replaces those public limits with its own amount, expiry, and
redemption rules; its amount is a ceiling, so a request may ask for less.

With `Authorization: Bearer dfk_…`, no captcha is needed. A trusted key accepts
`amount` up to `keyMaxPerRequest` (5000 tDASH in production). An `mn` key pays
exactly 1000 tDASH and must omit `amount`. Key payouts skip public IP, replay,
and daily-budget limits, but still respect the faucet's reserve. Dash.org users
can self-serve trusted keys at `https://faucet.dashhq.org/keys`.

Successful response:

```json
{
  "txid": "...", "amount": 10, "address": "y...",
  "network": "testnet", "replay": false,
  "relays": ["insight", "dapi:68.67.122.11"]
}
```

`keyId`, `code`, `dryRun`, and `relays` appear when applicable.

Errors carry a flat shape and a nested `detail` copy:

```json
{
  "error": "Large amounts need the Turnstile captcha; proof of work is not enough",
  "requiresTurnstile": true,
  "detail": {
    "error": "Large amounts need the Turnstile captcha; proof of work is not enough",
    "requiresTurnstile": true
  }
}
```

- `400`: invalid address or amount, rejected proof, or a proof-of-work request above `turnstileAbove` (`requiresTurnstile: true`). When no captcha token is supplied, a testnet response may instead include `requiresProofOfWork: true` to tell the browser to obtain one.
- `403`: an unkeyed request above `publicMax` needs a dash.org sign-in or code (`requiresSignIn: true`; production also includes `accountUrl`). An expired signed-in session uses the same marker. With API keys disabled on the Worker, the same request gets a `400` without the marker.
- `401`: unknown, expired, or revoked API key.
- `429`: per-IP request limit, per-IP rolling amount allowance, large-request budget, or global daily budget. The body includes `retryAfter` and the response includes `Retry-After`; `requiresHardCaptcha` appears only when the hard proof can raise the hourly ceiling. A budget or allowance explanation may be in `detailMessage`.
- `503`: insufficient funds, unavailable chain providers, or a fragmented/confirming wallet. `No coin large enough` may include `retryAfter`; a broadcast that could not be confirmed may still have landed, so check the chain before retrying.

The helper never retries these responses. A person can use the browser for
Turnstile or sign-in/code flows; do not automate Turnstile or the hard captcha.

## Proof of work

```text
POST {capEndpoint}challenge  {}
  -> { "challenge": { "c": 100, "s": 32, "d": 4 }, "token": "<50 hex>", "expires": <ms> }
POST {capEndpoint}redeem     { "token": "...", "solutions": [n1..nc] }
  -> { "success": true, "token": "<capToken>", "expires": <ms> }
```

The helper implements the cap.js PRNG and SHA-256 searches. A cap token is
single-use and only authorizes the soft proof-of-work tier.

## Verification

Verify a returned txid with a local testnet node (`dash-cli -testnet
getrawtransaction <txid> 1`) or Insight:
`https://insight.testnet.networks.dash.org/insight-api/tx/<txid>`. Check
confirmations, `txlock`, and `vout`; a broadcast txid is not confirmation.
