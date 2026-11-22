#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "Usage: $0 <branch-name>" >&2
  exit 1
fi

branch_name="$1"
repo_root="$(git rev-parse --show-toplevel)"
worktree_path="${repo_root}/worktrees/${branch_name}"

if git show-ref --verify --quiet "refs/heads/${branch_name}"; then
  echo "Branch already exists: ${branch_name}" >&2
  exit 1
fi

if [[ -e "${worktree_path}" ]]; then
  echo "Worktree path already exists: ${worktree_path}" >&2
  exit 1
fi

mkdir -p "${repo_root}/worktrees"
git worktree add -b "${branch_name}" "${worktree_path}" HEAD >&2

echo "${worktree_path}"
