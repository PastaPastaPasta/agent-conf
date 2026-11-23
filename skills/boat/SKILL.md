---
name: boat
description: Spin up short-lived Ubuntu cloud sandboxes on boat.dev via the `boat` CLI when local compute is insufficient or under heavy load. Always prefer local machines first; overflow to boat.dev for heavy or burst compute such as fuzzing, sanitizer sweeps, large parallel builds, or isolated Linux environments.
---

# Boat.dev Cloud Sandboxes

Use `boat` (https://boat.dev/dashboard?tab=sandboxes) to spin up short-lived Ubuntu virtual machines in the cloud **only when local compute is insufficient or saturated**.

## Compute policy: local first, cloud overflow

**Always prefer local compute.** Do not spin up a cloud sandbox for routine edits, builds, or test runs when the local machine (or another reachable box in the local fleet) has headroom.

Check local load, memory, and disk first:

```bash
uptime
nproc 2>/dev/null || sysctl -n hw.ncpu
free -h 2>/dev/null || vm_stat
df -h .
# On strixbox, also check the container memory cap:
cat /sys/fs/cgroup/memory.max 2>/dev/null || true
```

Local fleet reference (verify live state before deciding):

| Box | OS / CPU / RAM | Typical constraint |
| --- | --- | --- |
| `laptop` | macOS arm64, 14 cores, 48 GB | Interactive workstation; macOS/iOS work |
| `studio` | macOS arm64, 16 cores, 64 GB | Shared with CI runners, Xcode builds, and disk/CPU pressure |
| `agentbox` | Ubuntu x86_64 VM, 48 vCPU, 172 GiB | Often runs at high load (50–190) from concurrent threads; `/tmp` is RAM-quotaed |
| `strixbox` | Ubuntu x86_64 container, 28 Zen 5 CPUs | Hard 32 GiB RAM ceiling (may drop further during `gpulab` SFT runs) and low CPU weight |

**Use Boat.dev when:**
- Local machines are at or near load/memory capacity and adding heavy work would starve active threads or trigger OOM kills (e.g., `agentbox` heavily loaded, `strixbox` RAM-capped during SFT runs, `studio` under build pressure).
- The task needs bursty, heavy, or parallel Linux compute: **fuzzing** (libFuzzer, AFL++, `cargo-fuzz`), multi-hour soak/stress runs, ASan/UBSan/TSan sweeps, large parallel test shards, or clean-room builds.
- The task needs an isolated root Ubuntu VM with Docker, a public IPv4 / temporary HTTPS URL (`boat host`), or an isolated disposable environment for untrusted code or inputs.

**Do NOT use Boat.dev when:**
- Local compute has enough free CPU, RAM, and disk for the job.
- The job requires macOS, Xcode, iOS Simulator, or Apple Silicon (Boat sandboxes are Ubuntu Linux).
- The task needs a permanent long-lived server (keep Boat boxes short-lived and tear them down promptly).

## Preflight

The `boat` binary lives at `~/.local/bin/boat` (symlinked to `~/.ascii/bin/boat`). Before creating a sandbox, check auth, plan/wallet limits, and existing sandboxes:

```bash
boat status --check
boat limits --all
boat list --all
```

- If `boat limits --all` reports that creation is blocked (for example `subscription_required`, trial limits, no wallet funds, or exhausted start limits), stop and tell the user rather than retrying.
- The Boat wallet tops itself up automatically, so a low or falling balance is not a reason to stop, hold back runs, set a spending floor, or ask the user to add funds. Act only when `boat limits --all` actually reports creation blocked.
- Check `boat list --all` first so you do not spawn duplicates or miss an already-prepared sandbox you can `boat resume`.

## Machine sizes and billing

Billed per second while running; stopped sandboxes stop compute billing and retain their disk snapshot for at least 14 days:

| `--type` | vCPU | RAM | Disk | Rate | Notes |
| --- | --- | --- | --- | --- | --- |
| `small` | 2 | 4 GB | 51 GB | $0.018/h | Light isolation / repros |
| `default` | 4 | 8 GB | 51 GB | $0.036/h | General builds / tests |
| `large` | 8 | 16 GB | 111 GB | $0.072/h | Paid plan; heavy builds / fuzzing |
| `xlarge` | 16 | 32 GB | 251 GB | $0.20/h | $100+ plan; heavy parallel fuzzing / C++ & Rust builds |

Pick the smallest size that completes the workload cleanly without thrashing.

## Short-lived workflows

Always pass explicit sandbox IDs (`bx_...`) in scripts and agent commands. Do not rely on the `current` alias, which requires an interactive shell function and does not carry across subshells.

### 1. One-shot self-cleaning job (preferred when no files need to be copied back)

`boat run` creates a sandbox, pushes a local directory into `/home/user/<dir>`, streams stdout/stderr, prints duration and cost, and deletes the sandbox on exit:

```bash
boat run --type large --push . --timeout 1800 --no-env -- make -j8 check
```

Add `--from <saved-snapshot>` to start from a pre-warmed environment. Pass `--keep` only if you need up to 15 minutes after exit to inspect or pull files.

### 2. Multi-step burst job (fuzzing, iterative runs, artifact retrieval)

Create with an explicit `--ttl` (auto-stop defaults to 1 hour; avoid `--no-auto-stop` for burst compute). Add `--no-env` whenever running fuzzers or untrusted code:

```bash
SANDBOX_ID="$(boat new --type large --ttl 3600 --no-env --name "fuzz-<task>" --json \
  | jq -r 'select(.event == "ready") | .id')"
```

Upload code or corpora and run commands (`boat exec` is faster than `boat ssh`; default timeout is 30 s, max 600 s sync, `0` = unlimited streaming):

```bash
boat scp --recursive ./repo "$SANDBOX_ID":/home/user/repo
boat exec "$SANDBOX_ID" --cwd repo --timeout 600 --stream -- cargo build --release
```

For long-running fuzzers or soak tests, run detached so network hiccups or shell timeouts do not kill the job:

```bash
boat exec "$SANDBOX_ID" --cwd repo --detach -- ./fuzz-target -max_total_time=1800 corpus/
boat exec "$SANDBOX_ID" --status <pid>
boat exec "$SANDBOX_ID" --attach <pid>
boat exec "$SANDBOX_ID" --kill <pid>
```

Auto-stop is **not** an idle timer: `boat exec` and SSH do not push it back. If a job legitimately needs more time, reset the remaining window explicitly:

```bash
boat extend "$SANDBOX_ID" --hours 2
```

Retrieve crash inputs, logs, or artifacts before teardown:

```bash
boat scp --recursive "$SANDBOX_ID":/home/user/repo/artifacts ./artifacts
```

Tear down immediately when finished:

```bash
# Disposable burst run (preferred): delete VM and snapshots
boat delete "$SANDBOX_ID" --yes

# Only if you will resume or fork this exact disk within 14 days:
boat stop "$SANDBOX_ID"
```

Verify nothing was left running:

```bash
boat list
```

### 3. Parallel fan-out (parallel fuzzing / sharded tests)

Prepare dependencies and build once in one sandbox, save a snapshot (10 saved snapshots included per $20 plan; extras cost $0.056/day), then fan out within `boat limits --all`:

```bash
boat stop "$SANDBOX_ID"
boat snapshot "$SANDBOX_ID" fuzz-base
boat new --from fuzz-base --type large --ttl 3600 --no-env --count 4 --json
```

Delete every worker sandbox (`boat delete <id> --yes`) and remove temporary saved snapshots (`boat snapshot rm fuzz-base`) once the run completes.

## Security and authentication

- Pass `--no-env` when fuzzing untrusted inputs or running third-party code; this strips account secrets and the in-sandbox API key.
- Do not copy `~/.secrets/*`, private SSH keys, or personal credentials into a Boat sandbox unless the task explicitly requires them.
- Never print, log, or commit API keys or Boat's `config.json` (`~/.config/ascii/boat/config.json` on Linux, `~/Library/Application Support/ascii/boat/config.json` on macOS).
- If `boat status --check` reports signed out:
  - On cluster boxes (`studio`, `agentbox`, `strixbox`), re-authenticate from the shared `agent-secrets` store:
    ```bash
    boat login --key-stdin < ~/.secrets/boat/api-key
    ```
  - On `laptop`, authenticate with `boat login` or `boat login --key-stdin` using a key from `https://boat.dev/dashboard?tab=api-keys`.

For full CLI/API/SDK details, fetch `https://docs.boat.dev/llms.txt` or `https://docs.boat.dev/cli-reference.md`.
