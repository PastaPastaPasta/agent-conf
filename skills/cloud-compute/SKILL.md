---
name: cloud-compute
description: Choose between local compute, Boat.dev sandboxes, and DigitalOcean droplets, and run short-lived Linux cloud jobs safely. Use before CPU-, memory-, or disk-heavy work when checking local headroom, when a local host is saturated or RAM-constrained, for burst Linux compute (fuzzing, sanitizers, heavy builds, Docker/Playwright), for reproducible benchmarks, or when a job exceeds local or Boat.dev limits.
---

# Cloud Compute (Local vs. Boat.dev vs. DigitalOcean)

Be mindful and respectful of local resource limits. **Local compute comes first when the host has headroom** — overflow to cloud compute whenever the host is bottlenecked, or when the workload needs reproducible benchmark hardware or a bigger/isolated Linux VM.

## 1. Check local headroom first

Run a quick metrics check before starting CPU-, memory-, or disk-heavy work (full builds, big test suites, fuzzers, Docker/Playwright, benchmarks):

```bash
uptime
nproc 2>/dev/null || sysctl -n hw.ncpu
free -h 2>/dev/null || vm_stat
df -h .
# Linux: sustained disk I/O wait (%wa) and container memory ceiling
vmstat 1 2 2>/dev/null | tail -1 || true
cat /sys/fs/cgroup/memory.current /sys/fs/cgroup/memory.max 2>/dev/null || true
```

Treat the local host as **bottlenecked** when any of these hold:

- **CPU:** 15-minute load average > `1.0 × nproc` (or 5-minute load > `1.5 × nproc`).
- **Disk I/O:** sustained `iowait` (`wa` in `vmstat`) ≥ 20%, or heavy macOS swap activity.
- **Memory:** under ~25% of host RAM (or cgroup `memory.max`) available, or the job's peak working set won't fit safely alongside active threads.
- **Disk space:** tight free space on the working volume.

Local fleet reference (always trust live metrics over this table):

| Box | OS / CPU / RAM | Typical constraint |
| --- | --- | --- |
| `laptop` | macOS arm64, 14 cores, 48 GB | Interactive workstation; macOS/iOS work |
| `studio` | macOS arm64, 16 cores, 64 GB | Shared with CI runners, Xcode builds, and disk/CPU pressure |
| `agentbox` | Ubuntu x86_64 VM, 48 vCPU, 200 GiB | Often runs at high load (50–190) from concurrent threads; `/tmp` is RAM-quotaed |
| `strixbox` | Ubuntu x86_64 container, 28 Zen 5 CPUs | Shared RAM with GPU/host (`memory.max` cgroup cap, may drop during GPU runs); low CPU weight |

## 2. Pick the right target

| Target | Use it for | Do NOT use it for |
| --- | --- | --- |
| **Local host** | Routine edits, fast incremental compiles, targeted tests/linters, macOS/Xcode/iOS Simulator, local GPU work — whenever headroom is healthy. | Heavy jobs when the host is already bottlenecked; reproducible wall-clock/disk benchmarks on noisy shared boxes. |
| **Boat.dev** (`boat` CLI) | **Default for short-lived burst/overflow Linux compute where exact wall-clock timing doesn't matter:** fuzzing, sanitizer/soak sweeps, large parallel builds/test suites, Docker/Playwright e2e, isolated untrusted VMs. Fast boot, cheap (`$0.018–$0.072/h`), auto-expiring `--ttl`. | Reproducible wall-clock or disk benchmarks (timing is noisy); jobs needing >8 vCPU or >16 GB RAM on the Standard plan; macOS/iOS; long-lived servers. |
| **DigitalOcean droplet** (`doctl`) | **1. Reproducible benchmarks** (short-lived dedicated-CPU Premium NVMe droplets).<br>**2. Heavy Linux jobs exceeding Boat's `large` (8 vCPU / 16 GB) ceiling** (e.g. 16 vCPU / 32 GB builds or test runs).<br>**3. Always-on / public services** (only with explicit user approval). | Routine burst builds/fuzzers that fit on Boat.dev (droplets boot slower, cost more, and need manual SSH-key and teardown hygiene). |

---

## 3. Boat.dev workflow (`boat` CLI)

### Preflight

The `boat` binary lives at `~/.local/bin/boat` (symlinked to `~/.ascii/bin/boat`). Always check auth, limits, and existing sandboxes first:

```bash
boat status --check
boat limits --all
boat list --all
```

- If `boat limits --all` reports creation is blocked (`subscription_required`, exhausted limits, etc.), stop and tell the user rather than retrying.
- The Boat wallet tops itself up automatically — a low or falling balance is not a reason to stop or hold back runs. Act only when `boat limits --all` actually reports creation blocked.
- Check `boat list --all` first so you don't spawn duplicates or miss a sandbox you can `boat resume`.

### Sizes and billing

Billed per second while running. A stopped sandbox stops compute billing but keeps its disk and snapshot, and still counts as a sandbox on the account until someone runs `boat delete`:

| `--type` | vCPU | RAM | Disk | Rate | Notes |
| --- | --- | --- | --- | --- | --- |
| `small` | 2 | 4 GB | 51 GB | $0.018/h | Light isolation / repros |
| `default` | 4 | 8 GB | 51 GB | $0.036/h | General builds / tests |
| `large` | 8 | 16 GB | 111 GB | $0.072/h | **Max on Standard ($20/mo) plan**; heavy builds / fuzzing / Docker |
| `xlarge` | 16 | 32 GB | 251 GB | $0.20/h | Requires $100+ plan (if unavailable, use a DO droplet) |

Pick the smallest size that completes the workload cleanly without thrashing. Always pass explicit sandbox IDs (`bx_...`); do not rely on the `current` alias.

### One-shot self-cleaning job (preferred when no artifacts are needed back)

```bash
boat run --type large --push . --timeout 1800 --no-env -- make -j8 check
```

Add `--from <saved-snapshot>` for a pre-warmed environment. Pass `--keep` only if you need up to 15 minutes after exit to pull files.

### Multi-step burst job (fuzzing, iterative runs, artifact retrieval)

Create with an explicit `--ttl` (auto-stop defaults to 1 hour; avoid `--no-auto-stop`). The TTL only caps runaway compute: when it fires the box is **stopped, not deleted**, and you still owe the teardown below. Pass `--no-env` whenever running fuzzers or untrusted code:

```bash
SANDBOX_ID="$(boat new --type large --ttl 3600 --no-env --name "work-<task>" --json \
  | jq -r 'select(.event == "ready") | .id')"
```

Upload code and run commands (`boat exec` is faster than `boat ssh`; default timeout 30 s, max 600 s sync, `0` = unlimited streaming):

```bash
boat scp --recursive ./repo "$SANDBOX_ID":/home/user/repo
boat exec "$SANDBOX_ID" --cwd repo --timeout 600 --stream -- cargo build --release
```

For long-running fuzzers or soak tests, run detached so network hiccups don't kill the job:

```bash
boat exec "$SANDBOX_ID" --cwd repo --detach -- ./fuzz-target -max_total_time=1800 corpus/
boat exec "$SANDBOX_ID" --status <pid>
boat exec "$SANDBOX_ID" --attach <pid>
boat exec "$SANDBOX_ID" --kill <pid>
```

Auto-stop is **not** an idle timer (`boat exec`/SSH do not push it back). Extend explicitly if needed:

```bash
boat extend "$SANDBOX_ID" --hours 2
```

Pull artifacts and tear down immediately when finished:

```bash
boat scp --recursive "$SANDBOX_ID":/home/user/repo/artifacts ./artifacts
boat delete "$SANDBOX_ID" --yes
for i in 1 2 3 4 5 6; do boat list --all --json | jq -e --arg id "$SANDBOX_ID" 'all(.sandboxes[]; .id != $id)' >/dev/null && break; sleep 10; done
```

### Teardown rule

- Teardown is done only when `boat delete <id> --yes` succeeded **and** `boat list --all` no longer shows the ID (deletion is asynchronous, so allow up to a minute). Report it as done only after both.
- **Auto-stop is not cleanup.** A stopped box (TTL fired, `boat stop`) keeps its disk and snapshot, and Boat's 14-day retention cannot be relied on to delete it (boxes have been seen lingering). Stopping is only for a box you will `boat resume` or `boat fork` soon.
- Plain `boat list` shows running boxes only, so it hides stopped ones. Always verify with `boat list --all`.
- `boat run` deletes its sandbox when the command exits, so it needs no teardown; prefer it whenever you don't need the box afterwards. With `--keep`, delete the box yourself once you have pulled files.
- To keep an environment past the job, save a named snapshot (`boat snapshot <id> <name>`), then delete the box. A named snapshot survives `boat delete`.
- A periodic reaper deletes boxes stopped for over 48 hours unless they are allowlisted. It is a backstop, not your teardown.

### Parallel fan-out

Build once, save a snapshot (10 snapshots included per $20 plan; extras $0.056/day), fan out within `boat limits --all`, then delete workers and temporary snapshots (`boat snapshot rm <name>`):

```bash
boat stop "$SANDBOX_ID"
boat snapshot "$SANDBOX_ID" work-base
boat new --from work-base --type large --ttl 3600 --no-env --count 4 --json
```

### Boat auth & security

- Pass `--no-env` for fuzzers or untrusted code so account secrets aren't injected into the sandbox.
- Do not copy `~/.secrets/*`, private SSH keys, or personal credentials into a sandbox unless the task explicitly needs them.
- Never print, log, or commit API keys or Boat's `config.json`.
- If `boat status --check` reports signed out on cluster boxes, re-auth via `boat login --key-stdin < ~/.secrets/boat/api-key` (or `boat login` on laptop).
- Full CLI docs: `https://docs.boat.dev/llms.txt` or `https://docs.boat.dev/cli-reference.md`.

---

## 4. DigitalOcean droplet workflow (`doctl`)

Check the `fleet` skill (`services/cloud.md`) for exact `doctl` contexts, account guardrails, and existing infrastructure before creating or touching any droplet.

### Guardrails

- **Always pass `--context <name>` explicitly** (`doctl --context default` is often unconfigured).
- **Never touch droplets or firewalls you did not create** (especially production or `owner:infra` / `management:terraform` droplets).
- **Name and tag every temporary droplet** so it is obviously owned and disposable (e.g. `--tag-names "management:agent,owner:pasta,project:<proj>"`).
- **Capture and delete by exact ID**, never by name/wildcard. Clean up both the droplet and any temporary SSH key you uploaded to DO.

### Choosing a size

- **Reproducible benchmarks (wall-clock / disk timing):** use **dedicated-CPU Premium NVMe** sizes (`c-8-intel`, `g-8vcpu-32gb-intel`, `so-4vcpu-32gb-intel`, `so-8vcpu-64gb-intel`). Avoid shared-CPU (`s-*`) droplets and avoid putting measured paths on attached network block volumes.
- **Heavy non-timing builds/tests (>16 GB RAM):** general/CPU-optimized sizes sized to fit the job (`c-16`, `g-8vcpu-32gb`, `s-8vcpu-16gb`, etc.).

### Short-lived droplet lifecycle

```bash
# 1. Create a throwaway SSH key for this run and register it
ssh-keygen -t ed25519 -N "" -f /tmp/do-run-key -C "ephemeral-run"
KEY_ID="$(doctl --context <ctx> compute ssh-key import "ephemeral-<task>" \
  --public-key-file /tmp/do-run-key.pub --format ID --no-header)"

# 2. Create droplet and capture its numeric ID cleanly (--format ID --no-header strips progress noise)
DROPLET_ID="$(doctl --context <ctx> compute droplet create "<proj>-<task>" \
  --region nyc3 --image ubuntu-24-04-x64 --size c-8-intel \
  --ssh-keys "$KEY_ID" --tag-names "management:agent,owner:pasta,project:<proj>" \
  --wait --format ID --no-header)"
IP="$(doctl --context <ctx> compute droplet get "$DROPLET_ID" --format PublicIPv4 --no-header)"

# 3. Wait for cloud-init; for benchmarks, stop background apt timers and keep the box quiet during measurement
ssh -i /tmp/do-run-key -o StrictHostKeyChecking=accept-new "root@$IP" \
  'cloud-init status --wait && systemctl stop apt-daily.timer apt-daily-upgrade.timer unattended-upgrades 2>/dev/null || true'
```

### Benchmark hygiene on droplets

- Upload every input before measurement starts and avoid touching the droplet while timed runs execute.
- Alternate baseline and candidate runs on the same droplet (and drop page cache between runs when measuring cold I/O) so host jitter doesn't skew comparisons.
- Record the droplet size, CPU model (`lscpu`), kernel, and a quick `fdatasync`/disk baseline alongside results.
- Note: if launching detached scripts via `systemd-run --unit`, export `HOME=/root USER=root` explicitly (systemd units may lack `HOME`).

### Mandatory teardown

Delete both the droplet and the temporary SSH key immediately after pulling results, then verify they are gone:

```bash
doctl --context <ctx> compute droplet delete "$DROPLET_ID" --force
doctl --context <ctx> compute ssh-key delete "$KEY_ID" --force
rm -f /tmp/do-run-key /tmp/do-run-key.pub
doctl --context <ctx> compute droplet list --tag-name "project:<proj>" --format ID,Name,Status
```
