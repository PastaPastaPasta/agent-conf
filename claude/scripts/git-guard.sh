#!/usr/bin/env bash
# PreToolUse/Bash guard for three git rules from CLAUDE.md / AGENTS.md:
#   1. Never stage everything: blocks `git add -A/--all/-u/.` and
#      `git commit -a/--all`, so agents stage explicit paths only.
#   2. Never disable commit signing: blocks `--no-gpg-sign`, `-c` overrides and
#      `git config` writes of signing keys, and tampering with the GIT_CONFIG_*
#      env vars that inject the agent signing key. Turning signing on is fine.
#   3. dashpay/platform PRs come from dashpay/platform, never a fork (fork PRs
#      skip the Rust/Swift CI jobs): blocks `gh pr create` / `gh api …/pulls`
#      with a PastaPastaPasta head, and `git push` to PastaPastaPasta/platform
#      unless that command carries PLATFORM_FORK_OK=1 (fork-only branches such
#      as git pins). Remotes are judged by URL, since remote names differ
#      between machines. Contributors' forks are left alone (maintainer fixups).
# Used by Claude (settings.json) and Codex (~/.codex/hooks.json); both send
# {tool_input, cwd}. Aimed at shortcuts, not determined evasion (eval,
# variables) — tests in tests/test_git_guard.py.
set -u

# One jq call: first line is the working directory, the rest is the command.
# Claude: tool_input.command (string). Codex: command may be an argv array
# (["bash","-lc",script] or ["git",…]) or exec_command's tool_input.cmd +
# workdir. Other argv (apply_patch bodies) is not shell and is skipped.
parsed=$(jq -r '(.tool_input.workdir // .cwd // ""),
  ((.tool_input | (.command // .cmd // empty) | if type != "array" then .
  elif length >= 3 and (.[0] | test("(^|/)(ba|z|da)?sh$")) and (.[1] | test("^-l?c$")) then .[2]
  elif length > 0 and (.[0] | test("(^|/)(git|gh)$")) then join(" ") else empty end) // "")')
dir=${parsed%%$'\n'*}
cmd=${parsed#"$dir"}
cmd=${cmd#?}
[ -n "$cmd" ] || exit 0
[ -n "$dir" ] || dir=$PWD

# Normalize, then emit one simple command per line:
#  - join backslash continuations;
#  - unquote quoted words without spaces (`-c "commit.gpgsign=false"`);
#  - replace remaining quoted strings (commit messages, heredoc $(cat …) bodies,
#    search patterns) with Q, so their text never looks like flags;
#  - split on ; & | ` $( and newlines.
segs=$(printf '%s' "$cmd" | perl -0777 -pe '
  s/\\\n/ /g;
  s/(["\x27])([^"\x27\s]*)\1/$2/g;
  s/\x27[^\x27]*\x27|"(?:\\.|[^"\\])*"/Q/gs;
  s/[;&|`]|\$\(/\n/g')

# Command position: segment start, optional subshell/substitution openers,
# shell keywords, wrappers, and env assignments.
lead='^[[:space:]]*([$({}`][[:space:]]*)*((if|elif|while|until|do|then|else|exec|command|nohup|sudo|nice|time|env|!)[[:space:]]+|[A-Za-z_][A-Za-z0-9_]*=[^[:space:]]*[[:space:]]+|timeout[[:space:]]+[0-9]+[smhd]?[[:space:]]+)*'
end='([[:space:])]|$)'
# git global options that may sit between `git` and the subcommand.
gitopt='([[:space:]]+(-C[[:space:]]+[^[:space:]]+|-c[[:space:]]+[^[:space:]]+|-[^[:space:]]+))*'
# Other arguments of the same command.
args='([[:space:]]+[^[:space:]]+)*'
# Config keys that control signing, and values that turn it on (allowed).
sigkey='(commit\.gpgsign|tag\.gpgsign|gpg\.[A-Za-z0-9.]+|user\.signingkey)'
enable='(commit|tag)\.gpgsign([[:space:]]+|=)(true|yes|on|1)'
cfgvar='GIT_CONFIG_(COUNT|KEY_[0-9]+|VALUE_[0-9]+|PARAMETERS|GLOBAL)'

staging='staging everything (git add -A/--all/-u/., git commit -a) is not allowed.
Check `git status`, then `git add` the specific files this task changed.'
signing='commits must stay signed with the agent key. Do not pass --no-gpg-sign,
override signing config, or touch the GIT_CONFIG_* env vars. If signing fails,
stop and tell the user instead of working around it.'
fork_pr='dashpay/platform PRs must come from a branch on dashpay/platform itself, never
a fork: fork PRs skip the Rust and Swift CI jobs and look green untested. Push the
branch to the remote whose URL is github.com/dashpay/platform (check `git remote -v`;
remote names differ between machines), then `gh pr create --repo dashpay/platform
--head <branch>`. See the file-pr skill.'
fork_push='this pushes to PastaPastaPasta/platform, a fork. Branches for platform PRs go to
dashpay/platform itself: push to the remote whose URL is github.com/dashpay/platform
(check `git remote -v`; remote names differ between machines). If this branch is
meant to live only on the fork (a git pin, no PR), put PLATFORM_FORK_OK=1 in front
of the command.'

# Rule 3 helpers. $dir is the directory the current segment runs in. URLs may
# be https, scp-style, ssh://…:443 or an ssh host alias (git@github-agent:…).
dashpay_re='github[^[:space:]]*[:/]dashpay/platform(\.git)?/?([[:space:]]|$)'
fork_re='github[^[:space:]]*[:/]pastapastapasta/platform(\.git)?/?([[:space:]]|$)'
gh_re="${lead}([^[:space:]]*/)?(git|gh)([[:space:]]|\$)"
gitd() { git -C "$dir" "$@" 2>/dev/null; }
# Point $dir at a `cd`/`git -C` target, relative to the current $dir.
chdir() { case $1 in /*) dir=$1 ;; '~'*) dir=$HOME${1#\~} ;; *) dir=$dir/$1 ;; esac; }
platform_checkout() { gitd remote -v | grep -Eiq "$dashpay_re"; }
# Push URLs of remote $1 (a name or a URL); empty $1 = where a bare `git push`
# (or `gh pr create` without --head) takes the current branch.
push_urls() {
  local r=${1-} b
  if [ -z "$r" ]; then
    b=$(gitd symbolic-ref -q --short HEAD) || return 0
    r=$(gitd config "branch.$b.pushRemote" || gitd config remote.pushDefault || gitd config "branch.$b.remote" || echo origin)
  fi
  case $r in */* | *:*) echo "$r" ;; *) gitd remote get-url --push --all "$r" ;; esac
}

platform_fork_reason() {
  local tok i a next="" remote="" refs=0 kept=0 repo="" head="" owner
  read -ra tok <<<"$seg"
  for ((i = 0; i < ${#tok[@]}; i++)); do case ${tok[i]} in git | */git | gh | */gh) break ;; esac; done
  [ "$i" -lt "${#tok[@]}" ] || return 0
  if [ "${tok[i]##*/}" = git ]; then
    for ((i++; i < ${#tok[@]}; i++)); do
      case ${tok[i]} in
        -C) i=$((i + 1)); chdir "${tok[i]-}" ;;
        -c) i=$((i + 1)) ;;
        -*) ;;
        *) break ;;
      esac
    done
    [ "${tok[i]-}" = push ] || return 0
    case $seg in *PLATFORM_FORK_OK=1*) return 0 ;; esac
    for a in "${tok[@]:i+1}"; do
      case $next in skip) next=""; continue ;; remote) next=""; remote=$a; continue ;; esac
      case $a in
        -d | --delete | -n | --dry-run) return 0 ;;
        --repo) next=remote ;;
        --repo=*) remote=${a#*=} ;;
        -o | --push-option | --receive-pack | --exec) next=skip ;;
        -*) ;;
        *) if [ -z "$remote" ]; then remote=$a; else refs=$((refs + 1)); case $a in :* | +:*) ;; *) kept=1 ;; esac; fi ;;
      esac
    done
    # Pushing only `:branch` refspecs deletes fork branches, which is cleanup.
    [ $refs -gt 0 ] && [ $kept = 0 ] && return 0
    push_urls "$remote" | grep -Eiq "$fork_re" && echo "$fork_push"
    return 0
  fi
  # gh: `gh pr create|new` and the REST fallback `gh api repos/dashpay/platform/pulls`.
  if [ "${tok[i + 1]-}" = api ]; then
    grep -Eiq 'repos/dashpay/platform/pulls([[:space:]]|$)' <<<"$seg" || return 0
    grep -Eiq '(-X|--method)[[:space:]=]*GET([[:space:]]|$)' <<<"$seg" && return 0  # a lookup, not a create
    owner=$(grep -Eio '(^|[[:space:]=])head=[^:[:space:]]+:' <<<"$seg" | sed -E 's/.*head=//; s/:$//' | head -1)
    [ -n "$owner" ] && ! grep -Eiq '^dashpay$' <<<"$owner" && echo "$fork_pr"
    return 0
  fi
  case "${tok[i + 1]-} ${tok[i + 2]-}" in "pr create" | "pr new") ;; *) return 0 ;; esac
  repo=$(grep -Eo '(^|[[:space:]])GH_REPO=[^[:space:]]+' <<<"$seg" | sed 's/.*=//')
  for ((i += 3; i < ${#tok[@]}; i++)); do
    case ${tok[i]} in
      -R | --repo) i=$((i + 1)); repo=${tok[i]-} ;;
      --repo=*) repo=${tok[i]#*=} ;;
      -H | --head) i=$((i + 1)); head=${tok[i]-} ;;
      -H=* | --head=*) head=${tok[i]#*=} ;;
    esac
  done
  # A quoted head with spaces ("Owner:$(git branch --show-current)") was
  # normalized to Q; take its owner from the raw command.
  [ "$head" = Q ] && head=$(grep -Eo -- "(-H|--head)[= ]+[\"']?[^\"' :]+:" <<<"$cmd" | sed -E "s/^(-H|--head)[= ]+[\"']?//" | head -1)
  repo=$(sed -E 's#^(https?://)?(www\.)?github\.com/##; s#\.git/?$##; s#/$##' <<<"$repo")
  if [ -n "$repo" ]; then grep -Eiq '^dashpay/platform$' <<<"$repo" || return 0
  else platform_checkout || return 0; fi
  case $head in
    *:*) grep -Eiq '^dashpay:' <<<"$head" || echo "$fork_pr" ;;
    "") push_urls "" | grep -Eiq "$fork_re" && echo "$fork_pr" ;;
  esac
  return 0  # a bare --head <branch> names a branch on the base repo, dashpay/platform
}

cd_re='^[[:space:]({]*(cd|pushd)([[:space:]]+([^[:space:]]+))?([[:space:]]|$)'
while IFS= read -r seg; do
  has() { printf '%s' "$seg" | grep -Eiq -e "$1"; }
  reason=""
  # Follow `cd` so rule 3 inspects the checkout the command actually runs in.
  if [[ $seg =~ $cd_re ]]; then
    chdir "${BASH_REMATCH[3]:-$HOME}"
  fi
  if has "${lead}git${gitopt}[[:space:]]+(add|stage)${args}[[:space:]]+(-[A-Za-z]*[Au][A-Za-z]*|--all|--update|\.|\./|:/|\*)${end}" || \
     has "${lead}git${gitopt}[[:space:]]+commit${args}[[:space:]]+(-[A-Za-z]*a[A-Za-z]*|--all)${end}"; then
    reason=$staging
  elif has "${lead}git${args}[[:space:]]+--no-(gpg-)?sign${end}" || \
       { has "${lead}git${args}[[:space:]]+-c[[:space:]]*${sigkey}=" && ! has "-c[[:space:]]*${enable}${end}"; } || \
       { has "${lead}git${gitopt}[[:space:]]+config${args}[[:space:]]+(--unset(-all)?|unset|set|--remove-section|remove-section)${args}[[:space:]]+(${sigkey}|gpg)${end}" && ! has "${enable}${end}"; } || \
       { has "${lead}git${gitopt}[[:space:]]+config${args}[[:space:]]+${sigkey}[[:space:]]+[^<>[:space:]]+${end}" && \
         ! has "${lead}git${gitopt}[[:space:]]+config${args}[[:space:]]+(--get[a-z-]*|get|--list|-l)${end}" && ! has "${enable}${end}"; } || \
       has "${lead}((export|declare|typeset|local|readonly)${args}[[:space:]]+)?${cfgvar}=" || \
       has "${lead}(unset|env)${args}[[:space:]]+(-u[[:space:]]*|--unset=?)?${cfgvar}${end}"; then
    reason=$signing
  elif [[ $seg =~ $gh_re ]]; then
    reason=$(platform_fork_reason)
  fi
  if [ -n "$reason" ]; then printf 'Blocked: %s\n' "$reason" >&2; exit 2; fi
done <<<"$segs"
exit 0
