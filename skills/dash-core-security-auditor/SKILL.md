---
name: dash-core-security-auditor
description: Audit Dash Core security-critical code with emphasis on consensus safety, LLMQ and BLS logic, ChainLocks, InstantSend, special transactions, deterministic masternode state, sporks, governance, CoinJoin, and reorg or persistence edge cases. Use when reviewing changes in src/validation.cpp, src/consensus, src/llmq, src/bls, src/chainlock, src/instantsend, src/evo, src/masternode, src/governance, src/coinjoin, or related tests, especially for consensus split risk, invalid state acceptance, replay paths, malformed input handling, denial of service, and state-corruption bugs.
---

# Dash Core Security Auditor

## Overview

Audit Dash Core with a consensus-first mindset. Prioritize real exploitability, consensus divergence, invalid-state acceptance, and peer-triggerable failure modes over style or speculative concerns.

## Gather Context

- Identify the invariant first: consensus agreement, quorum authenticity, lock safety, deterministic masternode state, credit pool correctness, or replay resistance.
- Inspect the real diff and surrounding code, not only final file snapshots.
- Map activation heights, sporks, cache dependencies, and reorg or restart behavior before judging correctness.

## Prioritize These Surfaces

- Review `src/validation.cpp` and `src/consensus/*` for mempool vs block-validation divergence, activation-boundary drift, and reorg rollback issues.
- Review `src/llmq/*` and `src/bls/*` for quorum selection, DKG, recovered signatures, aggregation, batch verification, and expensive peer-triggered work.
- Review `src/chainlock/*` and `src/instantsend/*` for conflicting lock handling, replay protection, stale-state use, and retroactive or reorg-sensitive behavior.
- Review `src/evo/*` for special transaction parsing, deterministic masternode transitions, coinbase payload rules, asset locks, credit pool accounting, and EvoDB consistency.
- Review `src/governance/*`, `src/masternode/*`, `src/spork.*`, and `src/coinjoin/*` for malformed message handling, threshold or authorization mistakes, persistence bugs, and denial-of-service vectors.

## Run the Attack Checklist

- Compare accept, connect, disconnect, and restart paths for inconsistent rule enforcement.
- Test malformed, truncated, duplicate, and alternate-encoding inputs.
- Check whether identifiers are bound tightly enough to chain, height, quorum type, quorum hash, and message purpose.
- Look for replay paths across quorums, heights, or legacy and upgraded code paths.
- Look for cache or DB states that can survive a crash or reorg in an impossible configuration.
- Look for resource-exhaustion paths from repeated verification, retries, unbounded collections, or expensive cryptographic work.
- Look for race conditions and TOCTOU bugs around chain tip, quorum state, mempool state, and async verification.

## Prove the Issue

- Prefer unit tests in `src/test/*.cpp` for deterministic parser, state-transition, and consensus-adjacent regressions.
- Prefer functional tests in `test/functional/*.py` for multi-node, spork, quorum, ChainLocks, InstantSend, and reorg scenarios.
- Prefer fuzz targets in `src/test/fuzz/*` when the issue is parser or message-surface oriented.
- If a full reproducer is not feasible, explain the exact blocker and provide the narrowest defensible claim.

## Output Contract

1. List findings in severity order with exact file references and the broken invariant.
2. Explain the technical path from input to failure, including why existing checks do not stop it.
3. Describe a realistic attack or failure scenario.
4. Recommend a fix that preserves consensus safety and avoids new divergence.
5. Call out missing tests, assumptions, and residual risk if no issue is proven.

## Guardrails

- Report only issues you can defend technically.
- Treat consensus split risk and invalid-state acceptance as highest severity.
- Favor concrete proof over intuition.
- Distinguish confirmed vulnerabilities from hardening suggestions.
