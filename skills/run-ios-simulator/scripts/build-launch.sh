#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: build-launch.sh --scheme NAME --device UDID --bundle-id ID --derived-data PATH
       (--workspace PATH | --project PATH)
       [--configuration NAME] [--resource-dir PATH --resource-target-dir RELPATH]
       [--resource-glob GLOB] [--screenshot PATH] [--build-log PATH]
       [--stabilize-seconds N] [--no-open]

Builds for one concrete iOS Simulator with normal Xcode signing, installs the app,
launches it, verifies the PID remains alive, and captures a screenshot.

Private resources may be injected from --resource-dir into the source-relative
--resource-target-dir for the build. Only previously missing files are copied, and
they are removed on exit. Existing destination files are never overwritten.
EOF
}

workspace=""
project=""
scheme=""
device=""
bundle_id=""
derived_data=""
configuration="Debug"
resource_dir=""
resource_target_dir=""
resource_glob="*-Info.plist"
screenshot=""
build_log=""
stabilize_seconds=5
open_simulator=1

while (($#)); do
  case "$1" in
    --workspace) workspace=${2:?}; shift 2 ;;
    --project) project=${2:?}; shift 2 ;;
    --scheme) scheme=${2:?}; shift 2 ;;
    --device) device=${2:?}; shift 2 ;;
    --bundle-id) bundle_id=${2:?}; shift 2 ;;
    --derived-data) derived_data=${2:?}; shift 2 ;;
    --configuration) configuration=${2:?}; shift 2 ;;
    --resource-dir) resource_dir=${2:?}; shift 2 ;;
    --resource-target-dir) resource_target_dir=${2:?}; shift 2 ;;
    --resource-glob) resource_glob=${2:?}; shift 2 ;;
    --screenshot) screenshot=${2:?}; shift 2 ;;
    --build-log) build_log=${2:?}; shift 2 ;;
    --stabilize-seconds) stabilize_seconds=${2:?}; shift 2 ;;
    --no-open) open_simulator=0; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

[[ -n "$scheme" && -n "$device" && -n "$bundle_id" && -n "$derived_data" ]] || {
  usage >&2
  exit 2
}
if [[ -n "$workspace" && -n "$project" ]] || [[ -z "$workspace" && -z "$project" ]]; then
  echo "Pass exactly one of --workspace or --project." >&2
  exit 2
fi
if [[ -n "$resource_dir" || -n "$resource_target_dir" ]]; then
  [[ -n "$resource_dir" && -n "$resource_target_dir" ]] || {
    echo "--resource-dir and --resource-target-dir must be used together." >&2
    exit 2
  }
fi

repo_root=$(pwd -P)
revision="not-a-git-worktree"
status_before=""
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  revision=$(git rev-parse HEAD)
  status_before=$(git status --porcelain=v1)
  if [[ -n "$status_before" ]]; then
    echo "Refusing to build a dirty worktree:" >&2
    printf '%s\n' "$status_before" >&2
    exit 1
  fi
fi

source_arg=(-project "$project")
[[ -n "$workspace" ]] && source_arg=(-workspace "$workspace")

if ! xcrun simctl list devices available | grep -Fq "$device"; then
  echo "Simulator UDID is not available: $device" >&2
  exit 1
fi

injected=()
injected_count=0
cleanup() {
  local path
  if ((injected_count > 0)); then
    for path in "${injected[@]}"; do
      rm -f "$path"
    done
  fi
}
trap cleanup EXIT

if [[ -n "$resource_dir" ]]; then
  [[ -d "$resource_dir" ]] || { echo "Resource directory not found: $resource_dir" >&2; exit 1; }
  target_dir="$repo_root/$resource_target_dir"
  [[ -d "$target_dir" ]] || { echo "Resource target directory not found: $target_dir" >&2; exit 1; }

  while IFS= read -r source_file; do
    destination="$target_dir/$(basename "$source_file")"
    if [[ -e "$destination" ]]; then
      if ! cmp -s "$source_file" "$destination"; then
        echo "Refusing to overwrite existing resource: $destination" >&2
        exit 1
      fi
      continue
    fi
    cp "$source_file" "$destination"
    injected+=("$destination")
    ((injected_count += 1))
  done < <(find "$resource_dir" -maxdepth 1 -type f -name "$resource_glob" -print | sort)

  if ((injected_count == 0)); then
    echo "Warning: no missing resources matched $resource_glob in $resource_dir" >&2
  fi
fi

mkdir -p "$derived_data"
[[ -n "$build_log" ]] || build_log="$derived_data/build.log"
[[ -n "$screenshot" ]] || screenshot="$derived_data/launch.png"
mkdir -p "$(dirname "$build_log")" "$(dirname "$screenshot")"

echo "Revision: $revision"
echo "Simulator: $device"
echo "Building scheme: $scheme"

set +e
xcodebuild "${source_arg[@]}" \
  -scheme "$scheme" \
  -configuration "$configuration" \
  -destination "platform=iOS Simulator,id=$device" \
  -derivedDataPath "$derived_data" \
  COMPILER_INDEX_STORE_ENABLE=NO \
  build 2>&1 | tee "$build_log"
build_status=${PIPESTATUS[0]}
set -e
((build_status == 0)) || { echo "xcodebuild failed; see $build_log" >&2; exit "$build_status"; }

app_path=""
while IFS= read -r candidate; do
  candidate_id=$(/usr/libexec/PlistBuddy -c 'Print :CFBundleIdentifier' "$candidate/Info.plist" 2>/dev/null || true)
  if [[ "$candidate_id" == "$bundle_id" ]]; then
    app_path=$candidate
    break
  fi
done < <(find "$derived_data/Build/Products" -type d -name '*.app' -print | sort)

[[ -n "$app_path" ]] || { echo "No built .app matched bundle identifier $bundle_id" >&2; exit 1; }
codesign --verify --deep --strict "$app_path"

if [[ -n "$resource_dir" ]]; then
  while IFS= read -r source_file; do
    [[ -f "$app_path/$(basename "$source_file")" ]] || {
      echo "Required runtime resource missing from app: $(basename "$source_file")" >&2
      exit 1
    }
  done < <(find "$resource_dir" -maxdepth 1 -type f -name "$resource_glob" -print | sort)
fi

xcrun simctl boot "$device" >/dev/null 2>&1 || true
xcrun simctl bootstatus "$device" -b
xcrun simctl terminate "$device" "$bundle_id" >/dev/null 2>&1 || true
xcrun simctl install "$device" "$app_path"

launch_output=$(xcrun simctl launch --terminate-running-process "$device" "$bundle_id")
printf '%s\n' "$launch_output"
pid=${launch_output##*: }
[[ "$pid" =~ ^[0-9]+$ ]] || { echo "Could not parse launch PID." >&2; exit 1; }

sleep "$stabilize_seconds"
if ! xcrun simctl spawn "$device" launchctl procinfo "$pid" >/dev/null 2>&1; then
  echo "App exited during the ${stabilize_seconds}s launch-stability window (PID $pid)." >&2
  echo "Recent app log:" >&2
  executable=$(/usr/libexec/PlistBuddy -c 'Print :CFBundleExecutable' "$app_path/Info.plist")
  xcrun simctl spawn "$device" log show --last 5m --style compact \
    --predicate "process == '$executable'" 2>/dev/null | tail -120 >&2 || true
  exit 1
fi

xcrun simctl io "$device" screenshot "$screenshot"
((open_simulator == 0)) || open -a Simulator --args -CurrentDeviceUDID "$device"

cleanup
injected=()
injected_count=0
trap - EXIT

if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  status_after=$(git status --porcelain=v1)
  if [[ "$status_after" != "$status_before" ]]; then
    mutation_patch="$derived_data/build-script-mutations.patch"
    git diff --binary -- . > "$mutation_patch"
    if [[ -s "$mutation_patch" ]]; then
      git apply -R --whitespace=nowarn "$mutation_patch"
    fi

    status_restored=$(git status --porcelain=v1)
    if [[ "$status_restored" != "$status_before" ]]; then
      echo "Build scripts left source mutations that could not be restored safely:" >&2
      git status --short >&2
      echo "Tracked mutation patch: $mutation_patch" >&2
      exit 1
    fi
    echo "Restored tracked build-script mutations; audit patch: $mutation_patch"
  fi
fi

echo "READY"
echo "revision=$revision"
echo "device=$device"
echo "bundle_id=$bundle_id"
echo "app_path=$app_path"
echo "pid=$pid"
echo "build_log=$build_log"
echo "screenshot=$screenshot"
