#!/usr/bin/env python3
"""Make one tDASH request to the Dash testnet faucet as a native client.

Browsers prove themselves with Turnstile; native clients (dashwallet-ios via
TestnetFaucet.swift) solve the faucet's documented soft-tier cap.js proof of
work instead: fetch a challenge, brute-force `c` SHA-256 prefix searches, redeem
the solutions for a single-use capToken, then present it once. The soft tier
carries the lowest per-IP ceiling (`rateLimits.soft` in /api/status). This
script never escalates to the hard tier and never retries.

Standard library only. Run: python3 request_core_faucet.py <testnet-address>
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
import time
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

MASK32 = 0xFFFFFFFF
# The faucet's soft shape is c=100, d=4 (6.55M hashes); refuse anything far
# heavier than that, as the Swift SDK does, rather than burn minutes of CPU.
MAX_WORK = 64_000_000
BASE58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
TESTNET_P2PKH_VERSION = 0x8C  # "y..."; the faucet pays only P2PKH addresses


def is_testnet_p2pkh(address: str) -> bool:
    """Base58check-decode and require the testnet P2PKH version byte."""
    try:
        n = 0
        for ch in address:
            n = n * 58 + BASE58.index(ch)
        raw = n.to_bytes(25, "big")
    except (ValueError, OverflowError):
        return False
    checksum = hashlib.sha256(hashlib.sha256(raw[:21]).digest()).digest()[:4]
    return raw[0] == TESTNET_P2PKH_VERSION and raw[21:] == checksum


def prng(seed: str, length: int) -> str:
    """cap.js' seeded PRNG: FNV-1a over the seed, then xorshift32, as hex."""
    state = 0x811C9DC5
    for ch in seed:
        state = ((state ^ ord(ch)) * 0x01000193) & MASK32
    out = ""
    while len(out) < length:
        state ^= (state << 13) & MASK32
        state ^= state >> 17
        state ^= (state << 5) & MASK32
        out += f"{state:08x}"
    return out[:length]


def solve_one(salt: str, target: str) -> int:
    """Smallest nonce with sha256(salt + str(nonce)) hex starting with target."""
    base = hashlib.sha256(salt.encode())
    nonce = 0
    while True:
        h = base.copy()
        h.update(str(nonce).encode())
        if h.hexdigest().startswith(target):
            return nonce
        nonce += 1


def solve(token: str, c: int, s: int, d: int) -> list[int]:
    return [solve_one(prng(f"{token}{i}", s), prng(f"{token}{i}d", d)) for i in range(1, c + 1)]


KEY_FILE = os.path.expanduser("~/.config/dash-faucet/api-key")


def api_key() -> str | None:
    """A faucet API key from DASH_FAUCET_KEY or ~/.config/dash-faucet/api-key, if any."""
    key = os.environ.get("DASH_FAUCET_KEY", "").strip()
    if not key and os.path.isfile(KEY_FILE):
        with open(KEY_FILE, encoding="utf-8") as handle:
            key = handle.read().strip()
    return key or None


def call(
    url: str, body: dict[str, Any] | None = None, key: str | None = None
) -> tuple[int, dict[str, Any]]:
    """Return (HTTP status, JSON object); status 0 means no usable response."""
    data = None if body is None else json.dumps(body).encode()
    headers = {"accept": "application/json", "user-agent": "dash-faucet-skill/3"}
    if key:
        headers["authorization"] = f"Bearer {key}"
    if data is not None:
        headers["content-type"] = "application/json"
    request = Request(url, data=data, headers=headers, method="GET" if data is None else "POST")
    try:
        with urlopen(request, timeout=60) as response:
            code, payload = response.status, json.load(response)
    except HTTPError as error:
        try:
            code, payload = error.code, json.load(error)
        except (OSError, ValueError):
            code, payload = error.code, {"error": error.reason}
    except (OSError, ValueError) as error:  # timeouts, resets, non-JSON 200s
        return 0, {"error": f"{type(error).__name__}: {error}"}
    return code, payload if isinstance(payload, dict) else {"error": payload}


def field(payload: dict[str, Any], key: str) -> Any:
    """Read an error field from the flat shape or FastAPI's nested `detail`."""
    detail = payload.get("detail")
    return payload.get(key, detail.get(key) if isinstance(detail, dict) else None)


def fail(message: str, payload: dict[str, Any] | None = None) -> int:
    if payload is not None:
        print(json.dumps(payload, indent=2))
    print(message, file=sys.stderr)
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Request one tDASH payout from faucet.thepasta.org or faucet.dashhq.org."
    )
    parser.add_argument("address", help="Dash testnet P2PKH address (y...)")
    parser.add_argument("--base-url", default="https://faucet.thepasta.org")
    parser.add_argument(
        "--amount",
        type=float,
        help="tDASH to request (default: the faucet's standard payout)",
    )
    args = parser.parse_args()
    key = api_key()
    if args.amount is not None and not valid_amount(args.amount):
        print("--amount must be at least 0.001 tDASH with at most 8 decimals.", file=sys.stderr)
        return 2

    address = args.address.strip()
    if not is_testnet_p2pkh(address):
        print("Refusing to send: not a valid Dash testnet P2PKH address (y...).", file=sys.stderr)
        return 2
    base = args.base_url.rstrip("/")

    code, status = call(f"{base}/api/status")
    if code != 200 or status.get("status") != "ok" or status.get("network") not in (None, "testnet"):
        return fail("Faucet is not ready (or not testnet); no request was made.", status)

    if key:
        # An API key replaces the proof of work and the per-IP limits.
        body: dict[str, Any] = {"address": address}
        if args.amount is not None:
            body["amount"] = args.amount
        code, result = call(f"{base}/api/core-faucet", body, key)
        return report(code, result)

    if args.amount is not None:
        refusal = unkeyed_amount_refusal(args.amount, status)
        if refusal:
            print(refusal, file=sys.stderr)
            return 2

    if not status.get("capEndpoint"):
        return fail("Faucet advertises no proof-of-work endpoint; use the web UI.", status)
    # Solve only for the faucet itself. Behind `wrangler dev` it advertises an
    # https URL for an http host, so fall back to its fixed soft-tier path.
    advertised, own = urlsplit(status["capEndpoint"]), urlsplit(base)
    if (advertised.scheme, advertised.netloc) == (own.scheme, own.netloc):
        cap = status["capEndpoint"].rstrip("/") + "/"
    else:
        cap = f"{base}/cap/v1/"

    code, challenge = call(f"{cap}challenge", {})
    try:
        shape, token = challenge["challenge"], str(challenge["token"])
        c, s, d = int(shape["c"]), int(shape["s"]), int(shape["d"])
    except (KeyError, TypeError, ValueError):
        return fail("Could not fetch a proof-of-work challenge.", challenge)
    if c * 16**d > MAX_WORK:
        return fail(f"Challenge c={c} d={d} is heavier than the soft tier; refusing.")

    started = time.monotonic()
    solutions = solve(token, c, s, d)
    print(f"Solved {c}x{d}-hex proof of work in {time.monotonic() - started:.1f}s", file=sys.stderr)

    code, redeemed = call(f"{cap}redeem", {"token": token, "solutions": solutions})
    if code != 200 or not redeemed.get("success") or not redeemed.get("token"):
        return fail("Proof of work was not accepted.", redeemed)

    body = {"address": address, "capToken": redeemed["token"]}
    if args.amount is not None:
        body["amount"] = args.amount
    code, result = call(f"{base}/api/core-faucet", body)
    return report(code, result)


def valid_amount(amount: float) -> bool:
    """Match the faucet's own amount check, so a bad value costs no proof of work."""
    return math.isfinite(amount) and amount >= 0.001 and round(amount, 8) == amount


def status_amount_limit(status: dict[str, Any], name: str) -> float | None:
    """Read a numeric amount limit from the faucet's status response."""
    limits = status.get("amountLimits")
    value = limits.get(name) if isinstance(limits, dict) else None
    return value if isinstance(value, (int, float)) and math.isfinite(value) else None


def unkeyed_amount_refusal(amount: float, status: dict[str, Any]) -> str | None:
    """Explain which browser credential an unkeyed amount would require."""
    pow_limit = status_amount_limit(status, "turnstileAbove")
    if pow_limit is None or amount <= pow_limit:
        return None

    public_max = status_amount_limit(status, "publicMax")
    if public_max is not None and amount <= public_max:
        return (
            f"--amount {amount:g} exceeds the proof-of-work ceiling of {pow_limit:g} tDASH; "
            "use the browser with Turnstile or configure an API key "
            "(DASH_FAUCET_KEY or ~/.config/dash-faucet/api-key)."
        )
    return (
        f"--amount {amount:g} needs a dash.org sign-in or a code; use the browser "
        "or configure an API key (DASH_FAUCET_KEY or ~/.config/dash-faucet/api-key)."
    )


def report(code: int, result: dict[str, Any]) -> int:
    print(json.dumps(result, indent=2))
    if code == 200:
        if result.get("replay"):
            print("Replay: this address was already paid today. The txid is that earlier "
                  "payment; no new tDASH was sent.", file=sys.stderr)
        return 0
    if code == 0 or (code == 503 and "could not be confirmed" in json.dumps(result)):
        print("Outcome unknown: the payout may still have been broadcast. Check the address "
              "on Insight and do not retry until it is clear nothing arrived. Never switch "
              "addresses to retry.", file=sys.stderr)
        return 1
    if field(result, "requiresTurnstile"):
        print("This amount requires Turnstile; use the browser or configure an API key. "
              "Not retrying.", file=sys.stderr)
        return 1
    if field(result, "requiresSignIn"):
        print("This amount requires a dash.org sign-in or a code; use the browser or "
              "configure an API key. Not retrying.", file=sys.stderr)
        return 1
    retry = field(result, "retryAfter")
    hint = f" Retry after {retry}s." if retry else ""
    if field(result, "requiresHardCaptcha"):
        hint += " A higher limit needs the hard challenge in the web UI."
    print(f"Faucet returned HTTP {code}; not retrying.{hint}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
