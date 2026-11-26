---
name: dash-functional-tests
description: Run Dash Core Python functional tests (test_runner.py or individual test/functional/*.py) with datadirs on a RAM disk. Use whenever running Dash functional tests locally or troubleshooting local functional-test timeouts and parallel flakes.
---

# Dash Core functional tests on a RAM disk

Always run Dash functional tests through the helper below instead of calling `test_runner.py` directly. It puts every test datadir on a RAM disk, then runs `test_runner.py` with your arguments.

## Why

On macOS, dashd forces a drive-cache flush (`F_FULLFSYNC`) from block files, LevelDB and the SQLite wallet. The SSD manages only about 400–500 of those per second across all processes. While one is in flight, every write that grows a file on the same volume waits, and that includes each unbuffered `debug.log` line. Every thread that logs then queues behind the logger's lock. The result is RPC timeouts, missed `assert_debug_log` deadlines and failed shutdowns while the CPU sits mostly idle.

Measured on pasta's laptop (M4 Pro), full suite at `-j32`:

| datadirs | wall time | failures |
|---|---|---|
| SSD | 817 s | 30 |
| 4 GB RAM disk | 169 s | 0 (peak usage 1.6 GB) |

## Run

From a Dash Core source dir or build dir, using the `python3` that has `dash_hash`. The helper runs `test_runner.py` with the same interpreter. It must run outside the agent sandbox: creating a RAM disk needs `hdiutil`/`diskutil`, and on macOS the volume lives under `/Volumes`.

```bash
H=<this-skill-dir>/scripts/dash_test_ramdisk.py   # next to this SKILL.md

python3 $H run -j32                                                  # full suite
python3 $H run -j8 wallet_basic.py "rpc_rawtransaction.py --legacy-wallet"
python3 $H run --nocleanup --tracerpc --loglevel=DEBUG feature_block.py
```

`test_runner.py` passes only `--long` options on to the tests. A bare argument such as `-l` is taken as a test name and skipped with "not found".

For one test run directly, point `TMPDIR` at the RAM disk, and stop if the helper fails. Otherwise `TMPDIR` is empty and the test silently runs on the SSD:

```bash
D="$(python3 -I $H path)" && TMPDIR="$D" test/functional/wallet_basic.py --descriptors
```

- **macOS:** there is only ever one RAM disk per machine. The helper reuses any mounted `/Volumes/dashtest*` RAM disk; only if none exists does it create a 4 GB APFS one at `/Volumes/dashtest-$USER`. If the existing disk isn't writable, the helper falls back to the temp dir instead of creating a second disk. Never create one yourself with `hdiutil`; if `status` reports more than one, `detach` the extras. The helper refuses a non-RAM volume at `/Volumes/dashtest-$USER`.
- **Linux:** it uses `/dev/shm/dash-func-tests-$USER` (tmpfs). This hasn't been benchmarked on Linux. systemd-logind's `RemoveIPC=yes` wipes a user's `/dev/shm` files when their last login session ends, so a run started from an ssh session that then logs out can lose its datadirs.
- **No usable RAM disk** (sandboxed session, attach failed, `/dev/shm` missing or tiny as in Docker): the helper prints a WARNING and runs on the default temp dir. Say so in your report, and use a lower `-j` with `--timeout-factor=2`.
- If you pass your own `--tmpdirprefix`/`-t`, the helper leaves it alone.

## Parallelism

With datadirs on a RAM disk the limit becomes CPU and RAM rather than disk. `-j32` passed cleanly on the 14-core laptop even with other heavy work running. On shared machines, follow that host's load rules first. On the Mac Studio that means at most about `-j2`, niced (`nice -n 15`) and behind its shared heavy-job lock; see the mac-studio-load-limit memory.

## Space and cleanup

- A `-j32` run of the default suite peaks at about 1.6 GB. Free space is checked only when a run starts, so two big runs from different agents can still fill the 4 GB disk mid-run.
- `--extended` needs more: `feature_pruning.py` alone uses about 4 GB. `DASH_TEST_RAMDISK_MB` only takes effect when the disk is created. So `detach` first, then run with `DASH_TEST_RAMDISK_MB=8192` or more.
- Passing tests delete their datadirs. Failed ones (and `--nocleanup` runs) stay on the RAM disk so you can inspect them. Delete your own once you're done.
- `python3 $H status` lists leftover test dirs, which ones are in use, and free space. Delete only dirs you created.
- If free space is below 2 GB (`DASH_TEST_RAMDISK_MIN_FREE_MB`), the helper first deletes test dirs older than 12 h that no running process uses. If it's still short, it stops with an error rather than letting tests fail with ENOSPC.
- Leave the RAM disk mounted: other agents may be using it. `python3 $H detach` unmounts every dashtest RAM disk no process is using. Detaching frees the RAM and discards everything on it.

## When a test still fails

Rerun it alone through the helper before calling it real. If it passes alone but fails in the parallel run, look for a deadline that depends on load (a short `assert_debug_log` timeout, or one huge `generate` RPC call) rather than a bug in the change under test.
