---
name: run-ios-simulator
description: Build, install, launch, and verify iOS apps in Apple Simulator from exact Git revisions or worktrees. Use when running an iOS app, preparing a simulator, comparing before/after revisions, preserving a simulator wallet/fixture, debugging a launch crash, or capturing simulator evidence.
---

# Run an iOS app in Simulator

Use `scripts/build-launch.sh` for the deterministic build/install/launch path. Read the script's `--help` before the first use in an unfamiliar repository.

## Invariants

- Resolve and record the full source revision before building.
- For before/after comparisons, use the exact PR base and full PR head in separate worktrees and separate DerivedData directories.
- Clone one configured simulator fixture so both revisions receive identical application data, locale, network, and settings.
- Build for the concrete simulator UDID, not a generic destination.
- Keep simulator code signing enabled. Never pass `CODE_SIGNING_ALLOWED=NO` for a runnable build: it strips entitlements and can make frameworks such as CloudKit abort at launch even when compilation succeeds.
- Never exclude a runtime-required plist or resource merely to make `xcodebuild` green. Supply missing private resources locally before building and confirm they are inside the final app bundle.
- Treat `xcodebuild` success as compilation evidence only. Completion requires install success, a live process after the stabilization delay, and an inspected screenshot.
- Preserve user source changes. Start from a clean worktree. The launcher saves and reverses tracked mutations made by build phases, retaining an audit patch in DerivedData; it fails rather than guessing if the tree cannot be restored exactly.

## Workflow

1. Resolve provenance and cleanliness:

   ```bash
   git rev-parse HEAD
   git status --short --branch
   ```

2. Resolve or create the simulator. For a comparison, shut down the source fixture and clone it twice:

   ```bash
   xcrun simctl shutdown <fixture-udid>
   xcrun simctl clone <fixture-udid> "Feature Before"
   xcrun simctl clone <fixture-udid> "Feature After"
   ```

   Do not erase or delete an existing simulator unless explicitly authorized.

3. Find required local-only resources before building. Inspect project references and a known-working app or worktree. Do not print secret contents.

   If the worktree already has correct ignored resources or symlinks, omit `--resource-dir`. The launcher never overwrites an existing resource with different content.

4. Run the script once per revision. Use distinct `--derived-data` and `--screenshot` paths. Pass a known-working app bundle or resource directory with `--resource-dir`, and the source-relative destination directory with `--resource-target-dir`.

5. Open and inspect every screenshot at original resolution. Confirm the intended app is foregrounded and no crash, onboarding reset, stale binary, or unrelated prompt invalidates the result.

6. For before/after evidence, record the revision, simulator UDID/name, fixture source, app bundle identifier, build log, screenshot, and any injected local-only resources. Do not claim behavior from filename or build success alone.

## DashWallet example

DashWallet requires local service plists and CloudKit entitlements at launch. Copy the six `*-Info.plist` resources from a known-working `dashpay.app` into `DashWallet/` through the script, and allow Xcode's normal simulator signing:

```bash
scripts/build-launch.sh \
  --workspace DashWallet.xcworkspace \
  --scheme dashpay \
  --device <simulator-udid> \
  --bundle-id org.dashfoundation.dash \
  --derived-data /tmp/dashwallet-build-<revision> \
  --resource-dir <known-working-dashpay.app> \
  --resource-target-dir DashWallet \
  --resource-glob '*-Info.plist' \
  --screenshot /tmp/dashwallet-<revision>.png
```

(Cursor: `~/.cursor/skills/...`.)

If CocoaPods are absent, run the repository's supported dependency setup first. Copying Pods from another worktree is acceptable only when `Podfile.lock` matches and `Pods/Manifest.lock` is verified.

## Crash diagnosis

If launch liveness fails, inspect the script's crash excerpt, then query the simulator and host reports:

```bash
xcrun simctl spawn <udid> log show --last 10m --style compact \
  --predicate 'process == "<executable>"'
find ~/Library/Logs/DiagnosticReports -maxdepth 1 -type f \
  -iname '<executable>*.ips' -mmin -15 -print
```

Common distinctions:

- Missing `GoogleService-Info.plist` causing `FirebaseApp.configure()` to abort: runtime resource failure.
- CloudKit `EXC_BREAKPOINT`/`SIGTRAP` in setup code after building with signing disabled: missing entitlement caused by an invalid build procedure.
- PID exits after a successful `simctl launch`: launch failed; do not describe the simulator as ready.

## Handoff

Report simulator names and UDIDs, exact revisions, bundle identifier, build and launch status, screenshot paths, and any local-only resources injected. Leave the requested simulator(s) booted with the app foregrounded. Confirm all source worktrees are clean.
