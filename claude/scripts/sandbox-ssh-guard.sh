#!/usr/bin/env bash
# PreToolUse/Bash guard: SSH cannot work inside the Claude Code sandbox.
# The sandbox network layer only proxies HTTP/HTTPS, so any ssh connection dies
# with "ssh_dispatch_run_fatal: Connection to UNKNOWN port 65535: Broken pipe".
# Rather than let Claude burn a turn on that failure and then guess at causes,
# block the call and tell it to re-run with dangerouslyDisableSandbox: true.
#
# sandbox.excludedCommands is the documented fix but does not work today
# (anthropics/claude-code#10767, #10524, #53012), hence this hook.
set -u

input=$(cat)
cmd=$(printf '%s' "$input" | jq -r '.tool_input.command // empty')
[ -n "$cmd" ] || exit 0

# Already running outside the sandbox: nothing to do.
printf '%s' "$input" | jq -e '.tool_input.dangerouslyDisableSandbox == true' >/dev/null 2>&1 && exit 0

# Only match at command position: start of line, after a shell separator, or
# after a shell keyword, skipping env assignments and common wrappers.
lead='(^|[;&|(){}`])[[:space:]]*((do|then|else|exec|command|nohup|sudo|nice|time)[[:space:]]+|[A-Za-z_][A-Za-z0-9_]*=[^[:space:]]*[[:space:]]+|timeout[[:space:]]+[0-9]+[smhd]?[[:space:]]+)*'
end='([[:space:];&|)]|$)'
# git global options that may sit between `git` and the subcommand.
gitopt='([[:space:]]+(-C[[:space:]]+[^[:space:]]+|-c[[:space:]]+[^[:space:]]+|-[^[:space:]]+))*'

matches() { printf '%s' "$cmd" | grep -Eq "$1"; }

reason=""
if matches "${lead}(ssh|scp|sftp|ssh-keyscan|ssh-copy-id)${end}"; then
  reason="ssh/scp/sftp"
elif matches "${lead}rsync${end}"; then
  reason="rsync"
elif ! matches 'https?://' && { \
       matches "${lead}git${gitopt}[[:space:]]+(fetch|pull|push|clone|ls-remote)${end}" || \
       matches "${lead}git${gitopt}[[:space:]]+remote[[:space:]]+(update|prune)${end}" || \
       matches "${lead}git${gitopt}[[:space:]]+submodule[[:space:]]+(update|sync|foreach)${end}"; }; then
  reason="git network operation (remote may be ssh)"
fi

[ -n "$reason" ] || exit 0

cat >&2 <<MSG
Blocked: $reason cannot reach the network inside the sandbox — ssh gets killed
with "Connection to UNKNOWN port 65535: Broken pipe". Re-run this exact command
with dangerouslyDisableSandbox: true. Do not rewrite it as an https/gh fallback
just to stay sandboxed, and do not report this as a network or auth failure.
MSG
exit 2
