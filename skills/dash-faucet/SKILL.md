---
name: dash-faucet
description: Request testnet DASH (tDASH) from faucet.thepasta.org or faucet.dashhq.org to fund a testnet wallet or Platform identity asset lock. Use when you need tDASH or want to check faucet status.
---

# Dash Testnet Faucet

Use this skill whenever development or testing needs Dash testnet funds. faucet.thepasta.org and faucet.dashhq.org serve the same faucet Worker and dispense testnet DASH to a Core address. It is not a wallet or bridge, and its mainnet invitation feature is for humans in a browser, not agents.

## Operating workflow

1. Confirm the task is on Dash testnet. Refuse to send to a mainnet address (`X...`); ask for a `y...` testnet address or create one in the testnet wallet being used. Never request funds for an address the agent cannot tie to the intended testnet wallet.
2. Send with the helper (`scripts/request_core_faucet.py`, next to this file). It checks `/api/status` first and makes no request if the faucet is not `ok`:

   ```bash
   python3 -I scripts/request_core_faucet.py <testnet-address>
   ```

   It needs only the standard library. An unkeyed `--amount` is paid exactly as requested when it is at or below the proof-of-work ceiling in `/api/status`; above that, use a browser or an API key. With an API key configured (below), add `--amount <tDASH>` to ask for larger payouts.
3. Request only the amount needed, once. Do not retry rapidly, rotate IPs, or submit several addresses “just in case.”
4. Verify the txid (see below). A broadcast txid is not a confirmation.
5. Report destination, amount, txid, and whether confirmation or InstantSend verification succeeded. Do not print wallet seeds, private keys, captcha tokens, or unrelated environment values.

## How the helper authenticates

**With an API key** (preferred): if `DASH_FAUCET_KEY` is set, or `~/.config/dash-faucet/api-key` exists (mode 0600, one `dfk_…` line), the helper sends it as `Authorization: Bearer` and skips the proof of work. A `trusted` key has no captcha, per-IP or public daily limit, and takes `amount` up to 5000 tDASH. An `mn` key pays exactly one 1000 tDASH masternode collateral per call (1 a day by default). Payouts never take the faucet below its public reserve. Dash.org users can sign in at `https://faucet.dashhq.org/keys` to self-serve a trusted key; admins can issue codes or keys. Never print, log or commit a key, and never paste one into a PR, issue or chat.

**Without a key:**

`POST /api/core-faucet` needs proof of a human or of work. Browsers send a Turnstile token. Native clients (dashwallet-ios's `TestnetFaucet.swift`) solve the faucet's own cap.js proof of work instead: `POST {capEndpoint}challenge`, brute-force `c` SHA-256 prefix searches (about 6.5M hashes, about 2 s in Python), `POST {capEndpoint}redeem` for a single-use `capToken`, then `POST /api/core-faucet {"address", "capToken"}`. The helper does exactly that. This is a supported path that the faucet's README documents, not a CAPTCHA bypass. It earns the lowest per-IP ceiling (`rateLimits.soft` in `/api/status`, currently 3 an hour).

The helper never retries and never escalates to the hard tier. On a 429 it prints `retryAfter`. Honor it. If an unkeyed amount is above the proof-of-work ceiling, the helper refuses before any POST: amounts through `amountLimits.publicMax` need Turnstile, and larger amounts need a dash.org sign-in or a code. Use the web UI at either hostname for those paths; never automate the hard captcha or Turnstile. Ordinary unkeyed per-IP and daily budgets are charged by the requested amount and `/api/status` reports `amountLimits`.

Asking for the same address twice in one UTC day returns the original txid with `replay: true` rather than paying again.

## Platform identities

The current service has **no** asset-lock or identity endpoint (`/api/asset-lock-proof` and `/api/faucet` return 404; they belonged to the retired Python faucet). To fund an identity, send tDASH to a testnet address in the wallet that will build the asset lock, then create the asset lock and identity locally with the Dash/Evo SDK. Keep the asset-lock private key local.

## Errors and verification

The helper validates the address checksum locally before doing any work. The faucet pays only P2PKH (`y...`) addresses.

- `400`: invalid address, a bad `amount`, the proof was rejected, or the amount needs Turnstile (`requiresTurnstile`). A fresh helper run fetches a fresh challenge, but the helper does not retry a server response.
- `403`: the amount needs a dash.org sign-in or code (`requiresSignIn`); use the browser or configure an API key.
- `401`: the API key is unknown or revoked. Stop and tell the user; do not fall back to guessing another key.
- `429`: per-IP limit or daily budget spent. Stop, honor `retryAfter`/`Retry-After`.
- `503` "broadcast could not be confirmed", or a network failure on the final request (the helper prints "Outcome unknown"): the payout may still land, and the faucet records no claim for it, so a retry can pay twice. Check the address on Insight first. Never switch addresses to retry.
- `503` "No coin large enough": the amount needs coins that are still confirming, or more coins than one transaction carries. The faucet starts merging at once. When the body carries `retryAfter` (60 s), wait that long and try once more; a retry usually succeeds after the next block. Without `retryAfter`, no merge can help, so stop.
- Other `503`s: low balance, no spendable UTXO, or every explorer unreachable. Check `/api/status` and try later. Error responses carry no txid.
- `500`: report the non-secret detail; do not hammer the service.
- A `200` with `replay: true` is an earlier payment from today, not new funds. Report it as such. Key payouts never replay: each call pays.

Verify with a local testnet node (`dash-cli -testnet getrawtransaction <txid> 1`) or the testnet Insight the faucet itself uses: `curl -s https://insight.testnet.networks.dash.org/insight-api/tx/<txid>` (look at `confirmations`, `txlock`, `vout`). Say explicitly when verification was not possible.

Full endpoint and response reference: [faucet-api.md](./references/faucet-api.md). Source: `PastaPastaPasta/dash-faucet-cf` (Cloudflare Worker; README has the API and proof-of-work spec).
