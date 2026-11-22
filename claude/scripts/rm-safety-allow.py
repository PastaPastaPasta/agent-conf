#!/usr/bin/env python3
"""PermissionRequest hook (Bash, Monitor): approve Claude Code's rm safety-check
prompts when the command is plain scratch housekeeping.

In bypassPermissions mode the only Bash prompts left are the built-in rm checks
("Dangerous rm operation ...", "This shell -c script runs rm ...") and explicit
ask rules. The hook input carries permission_mode but not the prompt's reason,
so the hook approves a command only when it can show that it has at least one
delete (rm, rmdir, unlink, shred, find -delete/-exec rm, git clean, including in
-c scripts, trap and heredoc scripts) and that every delete hits a safe target:

  - absolute paths below /work/scratch, /work/tmp, /tmp, /var/tmp or $TMPDIR,
    with a literal first segment below the root;
  - relative paths, from a session cwd inside a repo, worktree or scratch dir
    (or a scratch dir the command cd'd into), that don't remove or empty ~,
    ~/workspace, a repo directly in it, or anything above, or touch .git;
  - globs such as dir/* after a cd into scratch, and bare * or . only when that
    cd is certain to have happened (&& chain, set -e, or `|| exit`);
  - variables assigned earlier in the same command, unconditionally, to such a
    path, to $(mktemp ...), or by a for loop over literal names or paths.

Paths that already exist are resolved, so a symlink or mount can't lead a
target or cd out of scratch (or out of the cwd, for relative targets), and a
delete must come before any command that could plant a symlink on its path.

The command itself must stay inside a small grammar: literal command names from
an allowlist (data tools, interpreters, a few build tools with plain arguments,
scripts by path, sh/bash -c with a literal script), no $( ) other than a bare
mktemp, no arithmetic, eval, source, functions or aliases, and writes only into
scratch or the repo.

A delete it can't prove safe is denied with instructions for rewriting it, so
an unattended agent gets a message and keeps going instead of waiting on a
prompt nobody will answer (pasta, 2026-11-01). Only a command with no delete
in it at all (an explicit ask rule, say) prints nothing and keeps its prompt.
"""
import fnmatch
import json
import os
import re
import sys

SCRATCH_ROOTS = ("/work/scratch", "/work/tmp", "/tmp", "/var/tmp")
DELETERS = {"rm", "rmdir", "unlink", "shred"}
SHELLS = {"sh", "bash", "dash"}
KEYWORDS = {"!", "{", "}", "if", "then", "elif", "else", "fi", "while", "until", "do", "done", "time",
            "for", "select", "case", "function", "coproc"}
# Programs whose arguments are inert data: they never run an argument as a command.
DATA = {"echo", "printf", "cat", "ls", "head", "tail", "wc", "tr", "cut", "grep", "egrep", "fgrep", "test",
        "[", "true", "false", ":", "sleep", "date", "basename", "dirname", "realpath", "readlink", "stat", "df",
        "du", "diff", "cmp", "comm", "which", "type", "pwd", "sha256sum", "sha1sum", "md5sum", "file", "nproc",
        "uname", "seq", "mkdir", "touch", "chmod", "nl", "column", "paste", "fold", "rev", "od", "base64",
        "tac", "jq", "wait", "exit", "return", "mktemp"}
# Interpreters of other languages: their code isn't shell, so the rm checks don't apply to it either.
INTERPRETERS = {"python", "python3", "node", "ruby", "perl"}
# git, only to clean, and options of it that run a command.
GIT_SUBCOMMANDS = {"clean"}
GIT_OPTIONS = ("--ext-diff", "--textconv", "--open-files-in-pager", "-O", "--exec", "--upload-pack")
# Environment variables a command may pass on: lowercase shell variables (no tool reads those, bar
# npm_config_*), and a few uppercase ones no allowed program takes code or options from.
ENV_NAMES = {"LC_ALL", "LANG", "TZ", "NO_COLOR", "TERM"}
# find (bfs, in Claude Code's shell) primaries: name -> arguments it takes. Anything else is refused,
# since bfs also takes start paths after the expression.
FIND_PRIMARIES = {
    "-name": 1, "-iname": 1, "-path": 1, "-ipath": 1, "-wholename": 1, "-regex": 1, "-iregex": 1, "-type": 1,
    "-xtype": 1, "-mtime": 1, "-mmin": 1, "-atime": 1, "-amin": 1, "-ctime": 1, "-cmin": 1, "-newer": 1,
    "-size": 1, "-maxdepth": 1, "-mindepth": 1, "-user": 1, "-group": 1, "-perm": 1, "-links": 1,
    "-regextype": 1, "-printf": 1, "-empty": 0, "-print": 0, "-print0": 0, "-prune": 0, "-delete": 0,
    "-xdev": 0, "-mount": 0, "-depth": 0, "-true": 0, "-false": 0, "-quit": 0, "-not": 0, "!": 0, "(": 0,
    ")": 0, "-o": 0, "-or": 0, "-a": 0, "-and": 0, ",": 0, "-follow": 0,
}
BUILTINS = {"cd", "pushd", "popd", "set", "export", "declare", "typeset", "readonly", "unset", "trap", "[["}
ALLOWED = DATA | INTERPRETERS | DELETERS | SHELLS | BUILTINS | {"find", "git"}
# Commands that can't create a symlink or mount, or write a file except through a redirect.
SIMPLE = DATA | DELETERS | BUILTINS | {"find"}
SYSTEM_BIN = {"/bin", "/usr/bin", "/sbin", "/usr/sbin"}
# Variables that make bash run or find code, or change how it splits words and resolves cd.
SPECIAL_VARS = {"IFS", "CDPATH", "PATH", "PS0", "PS1", "PS2", "PS3", "PS4", "PROMPT_COMMAND", "ENV", "SHELLOPTS",
                "BASHOPTS", "GLOBIGNORE", "HISTFILE", "HOME"}
SHELL_OPTIONS = {"errexit", "nounset", "pipefail", "xtrace"}
# Variables bash sets or changes itself (cd sets OLDPWD, every command sets _ ...): never tracked.
BASH_VARS = {"BASH", "BASHPID", "COMP_WORDBREAKS", "DIRSTACK", "EPOCHREALTIME", "EPOCHSECONDS", "EUID", "GROUPS",
             "HISTCMD", "HOSTNAME", "HOSTTYPE", "LINENO", "MACHTYPE", "OLDPWD", "OPTARG", "OPTERR", "OPTIND",
             "OSTYPE", "PIPESTATUS", "PPID", "PWD", "RANDOM", "REPLY", "SECONDS", "SHELL", "SHLVL", "SRANDOM", "TERM",
             "UID", "_", "COPROC", "MAPFILE", "FUNCNAME", "COLUMNS", "LINES", "MAIL", "MAILPATH", "MAILCHECK"}
BASH_VAR_PREFIXES = ("BASH_", "COMP_", "READLINE_", "HIST", "LD_")

# Markers inside resolved text. Commands containing \x00-\x03 are rejected up front.
UNKNOWN = "\x01"      # a value we can't know: unknown variable, $( ) output
QUOTED_GLOB = "\x02"  # a quoted * ? [ { that the shell won't expand
SAFESEG = "\x03"      # one plain file name, from a for loop over literal names
TMPROOT = "\x00T"     # the inherited $TMPDIR
MKTEMP = "\x00M"      # a fresh, certainly non-empty $(mktemp ...) path
MKTEMP_WEAK = "\x00W"  # $(mktemp ...) that may have failed and left the variable empty
SAFEPATH = "\x00P"    # a for loop over literal scratch paths
SESSION = ""          # cwd entry: the session's own working directory (None = unknown)

OPERATORS = ("&&", "||", ";;", "|&", "&>>", "<<<", "<<-", "<<", ">>", "&>", ">&", "<&", "<>", ">|",
             ";", "&", "|", "<", ">", "\n")
REDIRECTS = {"&>>", "<<<", ">>", "&>", ">&", "<&", "<>", ">|", "<", ">"}
INPUT_REDIRECTS = {"<", "<&", "<>"}
OUTPUT_REDIRECTS = {">", ">>", "&>", "&>>", ">|", ">&", "<>"}
DEVICES = {"/dev/null", "/dev/stdout", "/dev/stderr"}
LIST_ENDS = {";", "\n", "&", "||", ";;", None}
STATEMENT_ENDS = {";", "\n", None}
PIPES = {"|", "|&"}
META = set(" \t\n;&|()<>")
ASSIGN = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)(\[[^\]]*\])?(\+?)=")
IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
INTEGER = re.compile(r"-?[0-9]+")
SIMPLE_VAR = re.compile(r"[A-Za-z_][A-Za-z0-9_]*|[0-9@*#?$!-]")
PARAM = re.compile(r"(#?)([A-Za-z_][A-Za-z0-9_]*|[0-9@*#?$!-])(\[(?:[0-9]+|@|\*)\])?(:?[-?+][^}]*)?")
PLAIN_NAME = re.compile(r"\[\[?|[^\s\x00-\x03{},*?\[\]'\"$`\\=;&|<>()]+")
# A word with nothing a program could take as shell code: no spaces, quotes, $, `, ;, braces, ~ ...
PLAIN_WORD = re.compile(r"[^\s\x00-\x03'\"$`\;&|<>(){}!#~]+")
SEGMENT = re.compile(r"[A-Za-z0-9_+@%:-][A-Za-z0-9_.+@%:-]*")
# A delete named in text: as data it would still have drawn the prompt.
HIDDEN_DELETE = re.compile(r"(?:^|[\s;&|(){},`'\"!=:])(?:[^\s;&|,{}]*/)?(?:rm|rmdir|unlink|shred)(?=$|[\s;&|)},])"
                           r"|(?:^|\s)-delete\b|\bgit\b[^;&|\n]*\bclean\b")

# wrapper -> (flags, options taking an argument, options that change directory, takes VAR=value words,
#             clears the environment). Any other option is refused.
WRAPPERS = {
    "sudo": ({"-n", "-E", "-H", "-k", "--non-interactive", "--preserve-env"},
             {"-u", "-g", "-D", "--user", "--group", "--chdir"}, {"-D", "--chdir"}, True, True),
    "env": ({"-i", "-", "--ignore-environment"}, {"-C", "--chdir"}, {"-C", "--chdir"}, True,
            False),
    "systemd-run": ({"--user", "--same-dir", "-d", "--collect", "-G", "-q", "--quiet", "--wait", "-P", "--pipe",
                     "--scope", "--no-block"},
                    {"-u", "--unit", "--description", "--working-directory", "--nice"},
                    {"--working-directory"}, False, True),
    "nice": (set(), {"-n", "--adjustment"}, set(), False, False),
    "ionice": (set(), {"-c", "-n", "--class", "--classdata"}, set(), False, False),
    "timeout": ({"--foreground", "-v", "--verbose", "--preserve-status"}, {"-s", "-k", "--signal", "--kill-after"},
                set(), False, False),
    "nohup": (set(), set(), set(), False, False),
}
SYNC_SYSTEMD_RUN = {"--wait", "-P", "--pipe", "--scope"}
# Names the grammar has rules for, or that run their arguments. A file run by path under one of these names
# (./rm, a copy of /usr/bin/rm) gets none of those rules, so it is never taken for a plain repo script.
MODELED_NAMES = ALLOWED | set(WRAPPERS) | {"command", "builtin", "exec", "eval", "source", "xargs"}


class Unsafe(Exception):
    """Not provably safe: leave the prompt alone."""


# ---------------------------------------------------------------- lexer
# A word is a list of parts: ("lit", text, quoted), ("var", name, quoted) (name "" = unknown),
# ("sub", items, quoted) for $( ), backticks and <( ), ("arr", items, False) for a=( ).
# Items are ("W", parts, end), ("OP", op), ("G", items) for ( ), ["HD", body, quoted].

class Lexer:
    def __init__(self, text):
        self.s = text

    def parse(self):
        items, _ = self.lex(0, None)
        return items

    def lex(self, i, closer):
        s, items, heredocs = self.s, [], []
        while i < len(s):
            c = s[i]
            if c in " \t":
                i += 1
            elif s.startswith("\\\n", i):
                i += 2
            elif c == "#":
                j = s.find("\n", i)
                i = len(s) if j < 0 else j
            elif c == closer:
                return items, i + 1
            elif c == ")":
                raise Unsafe("unbalanced )")
            elif c == "(":
                if s.startswith("((", i):
                    raise Unsafe("(( )) arithmetic command")
                sub, j = self.lex(i + 1, ")")
                if items and items[-1][0] == "W" and items[-1][2] == i and s[i - 1] == "=":
                    items[-1][1].append(("arr", sub, False))
                else:
                    items.append(("G", sub))
                i = j
            elif c in "<>" and s.startswith("(", i + 1):
                parts, i = self.word(i)
                items.append(("W", parts, i))
            else:
                op = next((o for o in OPERATORS if s.startswith(o, i)), None)
                if op is None:
                    parts, i = self.word(i)
                    if not (len(parts) == 1 and parts[0][0] == "lit" and not parts[0][2]
                            and parts[0][1].isdigit() and s[i:i + 1] in ("<", ">")):
                        items.append(("W", parts, i))  # (a bare fd number before a redirect is dropped)
                    continue
                i += len(op)
                if op in ("<<", "<<-"):
                    while i < len(s) and s[i] in " \t":
                        i += 1
                    parts, i = self.word(i)
                    if any(p[0] != "lit" for p in parts):
                        raise Unsafe("heredoc delimiter with expansion")
                    item = ["HD", "", any(p[2] for p in parts)]
                    heredocs.append((item, "".join(p[1] for p in parts), op == "<<-"))
                    items.append(item)
                else:
                    items.append(("OP", op))
                    if op == "\n" and heredocs:
                        i = self.heredoc_bodies(i, heredocs)
                        heredocs = []
        if closer:
            raise Unsafe("unterminated group")
        return items, i

    def heredoc_bodies(self, i, heredocs):
        s = self.s
        for item, delim, strip_tabs in heredocs:
            body = []
            while i < len(s):
                j = s.find("\n", i)
                j = len(s) if j < 0 else j
                line, i = s[i:j], j + 1
                if (line.lstrip("\t") if strip_tabs else line) == delim:
                    break
                if not item[2] and line.endswith("\\"):
                    raise Unsafe("heredoc line joined to the next")  # bash may then see the delimiter elsewhere
                body.append(line)
            item[1] = "\n".join(body)
        return min(i, len(s))

    def word(self, i):
        s, parts = self.s, []
        if s[i] in "<>":  # process substitution <( ) or >( )
            sub, i = self.lex(i + 2, ")")
            parts.append(("sub", sub, False))
        while i < len(s) and s[i] not in META:
            c = s[i]
            if c == "\\":
                if not s.startswith("\n", i + 1):
                    parts.append(("lit", s[i + 1:i + 2], True))
                i += 2
            elif c == "'":
                j = s.find("'", i + 1)
                if j < 0:
                    raise Unsafe("unterminated '")
                parts.append(("lit", s[i + 1:j], True))
                i = j + 1
            elif c == '"':
                i = self.dquote(i + 1, parts)
            elif c in "$`":
                i = self.dollar(i, parts, False)
            elif parts and parts[-1][0] == "lit" and not parts[-1][2]:
                parts[-1] = ("lit", parts[-1][1] + c, False)
                i += 1
            else:
                parts.append(("lit", c, False))
                i += 1
        return parts, i

    def dquote(self, i, parts):
        s = self.s
        parts.append(("lit", "", True))
        while True:
            if i >= len(s):
                raise Unsafe('unterminated "')
            c = s[i]
            if c == '"':
                return i + 1
            if c == "\\" and s[i + 1:i + 2] in ("$", "`", '"', "\\", "\n"):
                if s[i + 1] != "\n":
                    parts.append(("lit", s[i + 1], True))
                i += 2
            elif c in "$`":
                i = self.dollar(i, parts, True)
            else:
                parts.append(("lit", c, True))
                i += 1

    def expansions(self):
        """The $( ), backticks and variables in an unquoted heredoc body."""
        s, parts, i = self.s, [], 0
        while i < len(s):
            if s[i] == "\\":
                i += 2
            elif s[i] in "$`":
                i = self.dollar(i, parts, True)
            else:
                i += 1
        return parts

    def dollar(self, i, parts, quoted):
        s = self.s
        if s[i] == "`":
            j, buf = i + 1, []
            while True:
                if j >= len(s):
                    raise Unsafe("unterminated `")
                if s[j] == "\\" and j + 1 < len(s):
                    buf.append(s[j + 1] if s[j + 1] in "$`\\" else s[j:j + 2])
                    j += 2
                elif s[j] == "`":
                    break
                else:
                    buf.append(s[j])
                    j += 1
            parts.append(("sub", Lexer("".join(buf)).parse(), quoted))
            return j + 1
        if s.startswith(("$((", "$["), i):
            raise Unsafe("arithmetic")  # its variables' values are evaluated as expressions, $( ) included
        if s.startswith("$(", i):
            sub, j = self.lex(i + 2, ")")
            parts.append(("sub", sub, quoted))
            return j
        if s.startswith("${", i):
            j = s.find("}", i)
            body = s[i + 2:j] if j > 0 else ""
            m = PARAM.fullmatch(body)
            if not m or any(c in body for c in "'\"\\$`{="):
                raise Unsafe("parameter expansion")  # ${x:=y}, ${!x}, ${a[$i]}, quoting inside: not modeled
            hash_, name, index, op = m.groups()
            if name == "TMPDIR" and op in (":-/tmp", "-/tmp", ":-/var/tmp", "-/var/tmp"):
                op = None
            plain = not hash_ and not index and (not op or op.lstrip(":").startswith("?"))
            parts.append(("var", name if plain else "", quoted))
            return j + 1
        if s.startswith(("$'", '$"'), i) and not quoted:
            raise Unsafe("$'...' quoting")
        m = SIMPLE_VAR.match(s, i + 1)
        if m:
            parts.append(("var", m.group(0), quoted))
            return m.end()
        parts.append(("lit", "$", quoted))
        return i + 1


def lit(word):
    """The word's text if it has no expansions, else None."""
    if word is None or any(p[0] != "lit" for p in word):
        return None
    return "".join(p[1] for p in word)


def tracked(name):
    """A variable whose value only the command's own assignments set."""
    return name not in SPECIAL_VARS | BASH_VARS and not name.startswith(BASH_VAR_PREFIXES)


def keyword(word):
    """A reserved word: only unquoted. bash runs "fi" or \\then as ordinary commands."""
    return len(word) == 1 and word[0][0] == "lit" and not word[0][2] and word[0][1] in KEYWORDS


def basename(name):
    return name.rsplit("/", 1)[-1] if name else name


def has_glob(text):
    return any(c in text for c in "*?[")


def under(path, root):
    return path == root or path.startswith(root.rstrip("/") + "/")


def tmpdir():
    """$TMPDIR as the hook sees it, if it is itself a scratch dir."""
    value = os.path.normpath(os.environ.get("TMPDIR") or "x")
    return value if any(under(value, r) for r in SCRATCH_ROOTS) else None


# ---------------------------------------------------------------- analysis

class Scope:
    def __init__(self, vars=None, exported=(), cwds=frozenset({SESSION})):
        self.vars = dict(vars or {})
        self.exported = set(exported)
        self.cwds = cwds              # every cwd the shell may be in at this point
        self.allexport = self.in_condition = self.elif_frame = False
        self.braces = []              # per open { group: whether it opened a frame
        self.frames = []              # (cwds, vars) where an if, loop or conditional { } body opened
        self.list_cwds = None         # cwds to fall back to when the and-or list ends
        self.list_vars = {}           # name -> value before a conditional assignment in this list
        self.list_mktemp = set()      # names whose mktemp result is certain only within this list

    def copy(self, cwds=None):
        new = Scope(self.vars, self.exported, self.cwds if cwds is None else cwds)
        new.allexport = self.allexport
        return new


class Unit:
    def __init__(self):
        self.words, self.redirs, self.heredocs, self.group = [], [], [], None

    def empty(self):
        return not (self.words or self.redirs or self.heredocs or self.group is not None)

    def stdin_sources(self):
        return len(self.heredocs) + sum(op == "<<<" or op in INPUT_REDIRECTS for op, _ in self.redirs)


def assigns_fd(unit):
    """{var}> and {var}<<E store the new file descriptor's number in var."""
    if unit.words and re.fullmatch(r"\{\w+\}", lit(unit.words[-1]) or ""):
        raise Unsafe("{var} redirect assigns a variable")


def units(items):
    out, cur, k = [], Unit(), 0
    while k < len(items):
        item = items[k]
        if item[0] == "OP":
            if item[1] in REDIRECTS:
                if k + 1 >= len(items) or items[k + 1][0] != "W":
                    raise Unsafe("redirect without target")
                assigns_fd(cur)
                cur.redirs.append((item[1], items[k + 1][1]))
                k += 2
                continue
            out.append((cur, item[1]))
            cur = Unit()
        elif item[0] == "HD":
            assigns_fd(cur)
            cur.heredocs.append((item[1], item[2]))
        elif item[0] == "W":
            cur.words.append(item[1])
        elif cur.words:
            raise Unsafe("function definition")
        else:
            cur.group = item[1]
        k += 1
    out.append((cur, None))
    return [(u, conn) for u, conn in out if not u.empty()]


class Analysis:
    def __init__(self, session_cwd=None):
        self.session_cwd = session_cwd
        self.assignments = {}       # name -> every value an assignment gave it
        self.used_vars = set()
        self.cwd_relied = False
        self.cwd_unstable = False   # a cd inside a loop body
        self.loop_depth = self.trap_depth = self.async_depth = 0
        self.deletes = 0
        self.complex_seen = False   # a command ran that may create symlinks, mounts or files
        self.complex_now = []       # the command being analyzed is one (it counts once it has run)
        self.content_written = False  # a redirect, interpreter or script may have written any file
        self.names_unsafe = False   # mkdir/touch made names a glob could pass to a program as options
        self.missing_in_loop = self.late_delete = self.runs_in_loop = False
        self.async_had_delete = self.async_deletes = False

    def finish(self):
        if not self.deletes:
            raise Unsafe("no delete operation")  # nothing for this hook to vouch for
        if self.cwd_unstable and self.cwd_relied:
            raise Unsafe("cd inside a loop")
        if any(len(self.assignments.get(n, ())) > 1 for n in self.used_vars):
            raise Unsafe("variable assigned more than once")
        if (self.missing_in_loop or self.late_delete) and self.complex_seen:
            raise Unsafe("a loop or trap deletes where another command may plant a symlink")
        if self.runs_in_loop and self.content_written:
            raise Unsafe("a loop runs a program or script the command may write")

    def saw(self, name):
        if name not in SIMPLE | SHELLS:
            self.complex_now.append(name)
        if self.complex_now and self.async_deletes:
            raise Unsafe("may plant a symlink while a background delete runs")

    def leave_async(self):
        self.async_depth -= 1
        if not self.async_depth and self.async_had_delete:
            self.async_deletes, self.async_had_delete = True, False

    def run_file(self, path, args, scope, cwds):
        """The command runs a script from the repo or a scratch dir by relative path: refuse if an earlier
        part may have written it, if it leads elsewhere (a link to /usr/bin/rm, say), or if its name is one
        the grammar checks (./rm: a copy of rm would delete targets no check has seen). A leading ~ is a
        home dir, not the cwd: ~bin/gnurm is /bin/gnurm."""
        if basename(path.rstrip("/")).lower() in MODELED_NAMES or path.startswith("~"):
            raise Unsafe("runs a file named like a checked command, or from a home dir: " + path)
        if self.content_written or self.complex_seen or ".." in path.split("/") or None in cwds:
            raise Unsafe("runs a file the command may have written, or from an unknown cwd")
        for c in cwds:
            base = c or self.session_cwd
            if not base or (c == SESSION and not self.workspace_cwd(base)) or base.startswith("\x00") \
                    or self.escapes(base + "/" + path, [base], True):
                raise Unsafe("script outside a repo or scratch dir: " + path)
        self.plain_args(args, scope)
        self.runs_in_loop |= self.loop_depth > 0
        self.complex_now.append(path)
        self.content_written = True

    # -- values

    def resolve(self, word, scope, raw=False, track=True, split=False):
        """The word's value: unknown parts become UNKNOWN; with raw, quoting is kept as typed.
        Variables read with track are ones a safety decision depends on. With split, an unquoted
        variable is treated the way the shell will: whitespace splits it, globs in it are live."""
        out = []
        for kind, val, quoted in word:
            if kind == "lit":
                out.append(val if raw else "".join(QUOTED_GLOB if quoted and c in "*?[{" else c for c in val))
            elif kind == "var" and val in scope.vars and tracked(val):
                if track:
                    self.used_vars.add(val)
                value = scope.vars[val]
                if split and not quoted:
                    value = UNKNOWN if any(c.isspace() for c in value) else value.replace(QUOTED_GLOB, "*")
                out.append(value)
            elif kind == "var" and val == "TMPDIR":
                out.append(TMPROOT)
            else:
                out.append(UNKNOWN)
        return "".join(out)

    def assign(self, scope, name, value, export=False):
        if not tracked(name):
            raise Unsafe("assigns " + name)
        scope.vars[name] = value
        self.assignments.setdefault(name, set()).add(value)
        if export or scope.allexport:
            self.environment_name(name)
            scope.exported.add(name)

    def value_of(self, parts, scope, plain=True):
        """An assignment's value. Only a plain NAME=$(mktemp ...) gets the certain MKTEMP marker."""
        if any(kind == "lit" and ("$(" in val or "`" in val) for kind, val, _ in parts):
            raise Unsafe("a value that bash may later run as code")  # PS4, arithmetic, subscripts
        subs = [p for p in parts if not (p[0] == "lit" and p[1] == "")]
        if len(subs) == 1 and subs[0][0] == "sub" and self.is_mktemp(subs[0][1]):
            return MKTEMP if plain else MKTEMP_WEAK
        return self.resolve(parts, scope)

    def is_mktemp(self, items):
        """$( ) that is a single literal mktemp command, which prints a fresh path or nothing."""
        seq = units(items)
        unit = seq[0][0] if len(seq) == 1 else None
        if not unit or unit.redirs or unit.heredocs or unit.group is not None or not unit.words:
            return False
        texts = [lit(w) for w in unit.words]
        if None in texts or texts[0] != "mktemp":
            return False
        k = 1
        while k < len(texts):
            t = texts[k]
            if t == "-p":
                k += 1
            elif t not in ("-d", "-q", "-t", "--directory", "--quiet") and t[:1] == "-" \
                    and not t.startswith(("--tmpdir=", "--suffix=")):
                return False
            k += 1
        return True

    def split_assignment(self, word):
        if not word or word[0][0] != "lit" or word[0][2]:
            return None
        m = ASSIGN.match(word[0][1])
        if not m:
            return None
        if m.group(2):
            raise Unsafe("array element assignment")  # the subscript is evaluated as arithmetic
        rest = word[0][1][m.end():]
        return m.group(1), m.group(3) == "+", ([("lit", rest, False)] if rest else []) + word[1:]

    # -- frames: if/loop bodies and and-or lists may not run

    def open_frame(self, scope):
        scope.frames.append((scope.cwds, dict(scope.vars)))

    def close_frame(self, scope):
        if not scope.frames:
            raise Unsafe("unbalanced fi/done/}")
        cwds, before = scope.frames.pop()
        scope.cwds |= cwds
        for name in set(before) | set(scope.vars):
            if before.get(name) != scope.vars.get(name):
                scope.vars[name] = UNKNOWN

    def end_list(self, scope):
        if scope.list_cwds is not None:
            scope.cwds, scope.list_cwds = scope.cwds | scope.list_cwds, None
        for name, before in scope.list_vars.items():
            if scope.vars.get(name) != before:
                scope.vars[name] = UNKNOWN
        for name in scope.list_mktemp:
            if scope.vars.get(name) == MKTEMP:
                scope.vars[name] = MKTEMP_WEAK
        scope.list_vars, scope.list_mktemp = {}, set()

    def certain(self, prev_conn, conn, nxt, cond=False):
        """Whether a failing command here stops everything after it in this scope. Not under if/while
        or ! (which turns a failure into success)."""
        if cond or prev_conn in ("&&", "||"):
            return False
        # (Not set -e: Claude Code runs the command as `... && eval '<command>' && ...`, where bash ignores it.)
        return conn == "||" and nxt[0] == "exit" and nxt[1] in STATEMENT_ENDS

    # -- targets

    def classify(self, text):
        """'abs', 'rel', 'relglob' (dir/*) or 'cwdglob' (*, ., *.log); raises if never safe."""
        segs = text.split("/")
        if "\x00" in text[1:] or UNKNOWN in text or "{" in text or ".git" in segs \
                or any(".." in s or (s[:1] == "." and has_glob(s)) for s in segs):
            raise Unsafe(text)  # (.* can reach . and ..)
        if text.startswith((MKTEMP, SAFEPATH)) or text == MKTEMP_WEAK:
            if text[2:] and not text[2:].startswith("/"):
                raise Unsafe(text)
            return "abs"
        if text.startswith(TMPROOT):
            if not tmpdir():
                raise Unsafe("TMPDIR is not a scratch dir here")
            rest = text[2:]
        elif text.startswith("/"):
            root = next((r for r in SCRATCH_ROOTS if under(text, r)), None)
            if root is None:
                raise Unsafe(text)
            rest = text[len(root):]
        else:
            if not text or text[0] in ("~", "\x00"):
                raise Unsafe(text)
            segs = [s for s in text.split("/") if s not in ("", ".")]
            if not segs or has_glob(segs[0]):
                return "cwdglob"
            return "relglob" if has_glob(text) else "rel"
        segs = [s for s in rest.split("/") if s not in ("", ".")]
        if (rest and not rest.startswith("/")) or not segs or has_glob(segs[0]):
            raise Unsafe(text)
        return "abs"

    def check_target(self, text, cwds, follow_last=False):
        kind = self.classify(text)
        self.note_delete(text, kind, follow_last)
        if kind == "abs":
            if self.escapes(text, SCRATCH_ROOTS, follow_last):
                raise Unsafe("symlink out of scratch: " + text)
            return
        self.cwd_relied = True
        if None in cwds:
            raise Unsafe("unknown cwd")
        if kind == "relglob" and cwds == {SESSION}:
            raise Unsafe("glob without a cd into scratch")
        if kind == "cwdglob" and SESSION in cwds:
            raise Unsafe("bare glob without a certain cd into scratch")
        for c in cwds:
            base = c or self.session_cwd
            if not base or (c == SESSION and not self.workspace_cwd(base)):
                raise Unsafe("relative target from a session cwd outside a repo or scratch")
            path = base + "/" + text
            if self.escapes(path, [base], follow_last) or self.protected(path):
                raise Unsafe("relative target reaches a protected dir: " + path)

    def note_delete(self, text, kind, follow_last):
        """A delete must run before anything that may plant a symlink on its path, unless it goes through
        none: a mktemp path itself, or a direct child of a scratch root (rm doesn't follow the last link)."""
        self.deletes += 1
        direct = text in (MKTEMP, MKTEMP_WEAK)
        if kind == "abs" and not (follow_last or text.endswith("/") or has_glob(text)
                                  or text.startswith((MKTEMP, SAFEPATH))):
            parent = os.path.dirname(os.path.normpath(text.replace(TMPROOT, tmpdir() or UNKNOWN, 1)))
            direct = parent in SCRATCH_ROOTS or parent == tmpdir()
        if direct:
            return
        if self.complex_seen:
            raise Unsafe("a delete after a command that may have planted a symlink on its path")
        self.late_delete |= bool(self.loop_depth or self.trap_depth)
        self.async_had_delete |= bool(self.async_depth)

    def workspace_cwd(self, cwd):
        """A session cwd relative deletes may start from: inside a repo, a worktree or scratch."""
        home = os.path.expanduser("~")
        for p in {os.path.normpath(cwd), os.path.realpath(cwd)}:
            if ".git" in p.split("/"):
                return False
            below = [p[len(r):].count("/") for r in (home + "/workspace", home + "/.t3/worktrees/x")
                     + SCRATCH_ROOTS if under(p, r) and p != r]
            if not below and not under(p, home + "/.t3/worktrees/") or \
                    (under(p, home + "/.t3/worktrees") and p.count("/") - (home + "/.t3/worktrees").count("/") < 2):
                return False
        return True

    def protected(self, path):
        """Whether deleting path, or emptying the dir its glob is in, hits ~, ~/workspace,
        a repo or worktree directly in them, a scratch root, anything above, or .git."""
        if path.startswith("\x00"):
            return False  # a mktemp or for-loop scratch dir
        segs = path.split("/")
        cut = next((k for k, s in enumerate(segs) if has_glob(s) or QUOTED_GLOB in s or SAFESEG in s), len(segs))
        home = os.path.expanduser("~")
        parents = [home, home + "/workspace", home + "/.t3/worktrees"]
        for p in {os.path.normpath("/".join(segs[:cut]) or "/"), os.path.realpath("/".join(segs[:cut]) or "/")}:
            if p.count("/") <= 1 or ".git" in p.split("/") or os.path.dirname(p) in parents \
                    or any(under(q, p) for q in parents + list(SCRATCH_ROOTS)):
                return True
        return False

    def escapes(self, path, bases, follow_last=False):
        """Whether the part of path that rm or cd goes through leaves every base directory: through
        a symlink or mount that exists now, or through a missing dir an earlier command may create
        as one."""
        def expand(p):
            if p.startswith(TMPROOT) and tmpdir():
                p = tmpdir() + p[len(TMPROOT):]
            return None if "\x00" in p else os.path.normpath(p or "/")

        segs = path.split("/")
        cut = next((k for k, s in enumerate(segs) if has_glob(s) or QUOTED_GLOB in s or SAFESEG in s), None)
        follow = follow_last or cut is not None or path.endswith("/")
        through = expand("/".join(segs[:cut]) if follow else os.path.dirname(path))
        roots = [r for r in map(expand, bases) if r]
        if through is None or not roots:
            return False  # a fresh mktemp dir or a for-loop path checked when assigned
        missing = False
        while not os.path.exists(through):
            through, missing = os.path.dirname(through), True
        if missing:
            if self.complex_seen:
                return True  # an earlier command may have made a symlink there
            self.missing_in_loop |= self.loop_depth > 0
        root = next((r for r in roots if under(through, r)), None)
        if root is None:
            return False  # nothing exists below the base yet
        real = os.path.realpath(through)
        if not any(under(real, os.path.realpath(r)) for r in roots):
            return True
        p = through
        while p != root and len(p) > len(root):  # a bind mount realpath can't see
            if os.path.ismount(p):
                return True
            p = os.path.dirname(p)
        return False

    def cd_result(self, text, cwds):
        """The cwds after `cd text` succeeds; scratch paths are kept, everything else is None."""
        if text is None or text in ("-", MKTEMP_WEAK) or has_glob(text) or QUOTED_GLOB in text:
            return frozenset({None})
        if text.startswith(("/", "\x00")):
            try:
                ok = self.classify(text) == "abs" and not self.escapes(text, SCRATCH_ROOTS, True)
            except Unsafe:
                ok = False
            return frozenset({text.rstrip("/") if ok else None})
        try:  # (CDPATH could send a relative cd anywhere)
            ok = self.classify(text) == "rel" and not os.environ.get("CDPATH")
        except Unsafe:
            ok = False
        joined = {c: c + "/" + text.rstrip("/") for c in cwds if ok and c}
        return frozenset(j if not self.escapes(j, [c], True) else None for c, j in joined.items()) \
            | ({None} if len(joined) < len(cwds) else set())

    # -- walking

    def items(self, items, scope):
        seq = units(items)
        for k, (unit, conn) in enumerate(seq):
            prev_conn = seq[k - 1][1] if k else None
            after = seq[k + 1] if k + 1 < len(seq) else (None, None)
            nxt = (lit(after[0].words[0]) if after[0] and after[0].words else None, after[1])
            background = conn == "&" or conn in PIPES or prev_conn in PIPES  # runs alongside what follows
            self.async_depth += background
            self.walk_subs(unit.words + [w for _, w in unit.redirs])
            writes = [self.redirect(op, w, scope) for op, w in unit.redirs]
            if unit.group is not None:
                self.heredoc_expansions(unit, scope)
                self.items(unit.group, scope.copy())
            else:
                self.command(unit, scope, prev_conn, conn, nxt)
            self.content_written |= any(writes)  # (only after the command: it can't read what they write)
            if background:
                self.leave_async()
            if conn in LIST_ENDS:
                self.end_list(scope)

    def walk_subs(self, words):
        for w in words:
            for kind, val, _ in w:
                if kind == "sub" and not self.is_mktemp(val):
                    raise Unsafe("command substitution")
                if kind == "arr":
                    raise Unsafe("array")  # ([k]=v) subscripts are evaluated as arithmetic

    def redirect(self, op, word, scope):
        """Whether the redirect writes a file: one in scratch, or plain relative in a repo or scratch cwd."""
        text, cwds = self.resolve(word, scope, track=False), scope.cwds
        if op not in OUTPUT_REDIRECTS or text in DEVICES or (op == ">&" and re.fullmatch(r"[0-9]+|-", text)):
            return False
        try:
            kind = self.classify(text)
        except Unsafe:
            kind = None
        if has_glob(text) or kind not in ("abs", "rel") or (kind == "rel" and (
                None in cwds or (SESSION in cwds and not self.workspace_cwd(self.session_cwd or "")))):
            raise Unsafe("writes outside scratch or the repo: " + text)
        bases = {c or self.session_cwd for c in cwds} if kind == "rel" else None
        if self.escapes(text, SCRATCH_ROOTS, True) if kind == "abs" else \
                any(self.escapes(b + "/" + text, [b], True) for b in bases if b and not b.startswith("\x00")):
            raise Unsafe("write through a symlink: " + text)
        return True

    def heredoc_expansions(self, unit, scope):
        """An unquoted heredoc's $( ) and backticks run in this shell, whoever reads the body."""
        for body, quoted in unit.heredocs:
            if not quoted:
                self.walk_subs([Lexer(body).expansions()])

    def stdin_script(self, unit, inner, prev_conn):
        """A shell (or source) reading its script from stdin: it must be one literal heredoc or
        here-string on this very command, which is then analyzed as the script."""
        if prev_conn in PIPES or unit.stdin_sources() != 1 or any(op in INPUT_REDIRECTS for op, _ in unit.redirs):
            raise Unsafe("shell reads a script from a pipe, a file or nowhere")
        for op, word in unit.redirs:
            if op == "<<<":
                if lit(word) is None:
                    raise Unsafe("here-string script with expansions")
                self.items(Lexer(lit(word)).parse(), inner)
        for body, quoted in unit.heredocs:
            if not quoted and any(c in body for c in "$`\\"):
                raise Unsafe("heredoc script with expansions")
            self.items(Lexer(body).parse(), inner)

    def command(self, unit, scope, prev_conn, conn, nxt):
        outer, self.complex_now = self.complex_now, []
        consumer = self.run_command(unit, scope, prev_conn, conn, nxt)
        self.complex_seen |= bool(self.complex_now)
        self.complex_now = outer
        if consumer != "shell":
            self.heredoc_expansions(unit, scope)
        if unit.stdin_sources() and consumer not in ("shell", "data"):
            raise Unsafe("stdin to a program that may run it")

    def run_command(self, unit, scope, prev_conn, conn, nxt):
        """Returns how the command uses stdin: "shell" (already analyzed), "data", or None."""
        words, cond = list(unit.words), False
        while words and keyword(words[0]):
            kw = lit(words[0])
            words = words[1:]
            if kw in ("case", "coproc", "function", "select"):
                raise Unsafe(kw)
            if kw in ("if", "while", "until", "!"):
                scope.in_condition, cond = kw != "!" or scope.in_condition, True
            elif kw == "elif":  # the elif condition and its body may not run
                self.close_frame(scope)
                self.open_frame(scope)
                scope.in_condition = scope.elif_frame = cond = True
            elif kw in ("then", "do", "else"):
                if kw == "else":
                    self.close_frame(scope)
                scope.in_condition = False
                if not (kw == "then" and scope.elif_frame):
                    self.open_frame(scope)
                scope.elif_frame = False
                self.loop_depth += kw == "do"
            elif kw in ("fi", "done"):
                self.close_frame(scope)
                self.loop_depth -= kw == "done"
            elif kw == "{":
                if prev_conn in PIPES:
                    raise Unsafe("{ } in a pipeline")
                scope.braces.append(prev_conn in ("&&", "||"))
                if scope.braces[-1]:
                    self.open_frame(scope)
            elif kw == "}":
                if conn in PIPES or conn == "&" or not scope.braces:
                    raise Unsafe("{ } in a pipeline or background")
                if scope.braces.pop():
                    self.close_frame(scope)
            elif kw == "for":
                self.for_loop(words, scope, prev_conn)
                return "data"

        env = {}
        while words and self.split_assignment(words[0]):
            name, append, value = self.split_assignment(words[0])
            if not tracked(name):
                raise Unsafe("assigns " + name)
            env[name] = (scope.vars.get(name, "") if append else "") + self.value_of(value, scope, plain=False)
            words = words[1:]
        if not words:
            self.assign_all(unit, env, scope, prev_conn, conn, nxt, cond)
            return "data"

        for name in env:
            self.environment_name(name)
        words, cwds, clears_env, wrapper_env, stripped, background = self.strip_wrappers(words, scope)
        env.update(wrapper_env)
        path = lit(words[0]) if words else None
        if not path or not PLAIN_NAME.fullmatch(path) or (has_glob(path) and path not in ("[", "[[")):
            raise Unsafe("command name missing, unusual or from an expansion")
        name, args = basename(path), words[1:]
        if stripped and name in BUILTINS:
            raise Unsafe("builtin under a wrapper")
        self.async_depth += background
        consumer = self.dispatch(path, name, args, unit, scope, cwds if cwds is not None else scope.cwds, env,
                                 clears_env, prev_conn, conn, nxt, cond)
        if background:
            self.leave_async()
        return consumer

    def dispatch(self, path, name, args, unit, scope, cwds, env, clears_env, prev_conn, conn, nxt, cond):
        if "/" in path:
            if not path.startswith("/"):
                if name in ALLOWED | set(WRAPPERS):
                    raise Unsafe("relative path to a recognized command: " + path)
                self.run_file(path, args, scope, cwds)
                return None
            normal = os.path.normpath(path)
            if os.path.dirname(normal) not in os.environ.get("PATH", "").split(":") + list(SYSTEM_BIN) \
                    or normal.startswith("//"):
                raise Unsafe("runs a program by absolute path: " + path)
            name = basename(normal)
        if name not in ALLOWED:
            raise Unsafe("not on the allowlist: " + name)
        self.saw(name)
        if name in ("cd", "pushd", "popd"):
            self.cd(name, args, scope, prev_conn, conn, nxt, cond)
        elif name == "set":
            self.set_options(args, scope, prev_conn, conn)
        elif name in ("export", "declare", "typeset", "readonly", "unset"):
            self.declare(name, args, scope)
        elif name == "[[":
            texts = {lit(a) for a in args}
            if "-v" in texts:
                raise Unsafe("[[ -v evaluates subscripts")
            if {"-eq", "-ne", "-lt", "-le", "-gt", "-ge"} & texts:  # operands are expressions
                for a in args:
                    t = self.resolve(a, scope, track=False)
                    if t not in ("]]", "!", "&&", "||", "-eq", "-ne", "-lt", "-le", "-gt", "-ge") \
                            and not INTEGER.fullmatch(t):
                        raise Unsafe("[[ arithmetic on something other than integers")
        elif name == "trap":
            self.trap(args, scope)
        elif name in DELETERS:
            self.deleter(name, args, cwds, scope)
        elif name == "find":
            self.find(args, cwds, scope)
        elif name in SHELLS:
            return self.shell(args, scope, cwds, env, clears_env, unit, prev_conn)
        elif name == "git":
            self.git(args, cwds, scope, unit, prev_conn)
        else:
            self.data(name, args, unit, scope)
            return "data"
        return None

    def environment_name(self, name):
        """A variable a program inherits: programs take code and options from their environment."""
        if name not in ENV_NAMES and not (re.fullmatch(r"[a-z_][a-z0-9_]*", name) and not name.startswith("npm_")):
            raise Unsafe("environment " + name)

    def declare(self, name, args, scope):
        """export, declare, readonly, unset: plain options and NAME or NAME=value words only. (Not local:
        outside a function it fails and assigns nothing.)"""
        flags = "".join(lit(a)[1:] for a in args if (lit(a) or "").startswith("-"))
        if not set(flags) <= set("xrgv"):
            raise Unsafe(name + " -" + flags)  # -n nameref, -i/-a/-A arithmetic and subscripts, -f ...
        exported = name == "export" or "x" in flags
        for a in args:
            t = lit(a)
            if a[0][2]:
                raise Unsafe(name + " with a quoted argument")  # declare 'x=...' is still an assignment
            parsed = self.split_assignment(a)
            if parsed and name != "unset":
                self.assign(scope, parsed[0], self.value_of(parsed[2], scope, plain=False), exported)
            elif t and IDENT.fullmatch(t):
                if name == "unset":
                    if not tracked(t):
                        raise Unsafe("unset " + t)
                    self.assign(scope, t, UNKNOWN)
                elif exported:
                    self.environment_name(t)
                    scope.exported.add(t)
            elif not (t or "").startswith("-"):
                raise Unsafe(name + " argument")

    def data(self, name, args, unit, scope):
        """Programs that don't run their arguments. Text naming a delete still gets the prompt."""
        texts = [self.resolve(a, scope, track=False) for a in args]
        if (name == "printf" and any(t.startswith("-v") for t in texts)) or (name in ("test", "[") and "-v" in texts) \
                or (name == "wait" and any(t[:1] == "-" and "p" in t for t in texts)):
            raise Unsafe(name + " option that assigns, evaluates or runs")
        if name in ("mkdir", "touch") and ("--" in texts or any(not PLAIN_WORD.fullmatch(t) or "/-" in t
                                                               for t in texts)):
            self.names_unsafe = True
        if name in INTERPRETERS:
            self.content_written = True
            texts += [body for body, _ in unit.heredocs] + [self.resolve(w, scope, track=False)
                                                            for op, w in unit.redirs if op == "<<<"]
        if any(HIDDEN_DELETE.search(t) for t in texts):
            raise Unsafe("names a delete")

    def plain_args(self, args, scope):
        """Arguments of a program that may run one as code: plain, known words that name no delete or shell."""
        texts = []
        for a in args:
            t = self.resolve(a, scope, track=False)
            if not PLAIN_WORD.fullmatch(t) or HIDDEN_DELETE.search(t) or basename(t) in SHELLS:
                raise Unsafe("argument a program may run: " + t)
            if has_glob(t) and (self.content_written or self.names_unsafe or any(
                    fnmatch.fnmatchcase(d, basename(t)) for d in DELETERS | SHELLS)):
                raise Unsafe("glob argument that may expand to options or a deleter: " + t)
            texts.append(t)
        return texts

    def assign_all(self, unit, env, scope, prev_conn, conn, nxt, cond):
        in_subshell = conn == "&" or conn in PIPES or prev_conn in PIPES
        for name, value in env.items():
            if in_subshell:
                value = UNKNOWN
            if prev_conn in ("&&", "||"):
                scope.list_vars.setdefault(name, scope.vars.get(name))
            plain = self.value_of(self.split_assignment(next(w for w in unit.words
                                                             if (self.split_assignment(w) or [None])[0] == name))[2],
                                  scope) if value == MKTEMP_WEAK else value
            if plain == MKTEMP and not in_subshell:  # mktemp can fail and leave the variable empty
                if conn == "&&" and prev_conn not in ("&&", "||") and not cond:
                    scope.list_mktemp.add(name)
                    value = MKTEMP
                elif self.certain(prev_conn, conn, nxt, cond):
                    value = MKTEMP
            self.assign(scope, name, value)

    def for_loop(self, words, scope, prev_conn):
        name = lit(words[0]) if words else None
        if not name or not IDENT.fullmatch(name):
            raise Unsafe("for loop")
        values = [lit(w) for w in words[2:]] if len(words) > 2 and lit(words[1]) == "in" else [None]
        if values and all(v and SEGMENT.fullmatch(v) and ".." not in v for v in values):
            value = SAFESEG
        else:
            try:
                ok = values and all(v and self.classify(v) == "abs" and not has_glob(v)
                                    and not self.escapes(v, SCRATCH_ROOTS, True) for v in values)
            except Unsafe:
                ok = False
            value = SAFEPATH if ok else UNKNOWN
        if prev_conn in ("&&", "||"):
            scope.list_vars.setdefault(name, scope.vars.get(name))
        self.assign(scope, name, value)

    def trap(self, args, scope):
        args = args[1:] if args and lit(args[0]) == "--" else args
        script = lit(args[0]) if args else None
        if not args or script in ("-p", "-l"):
            return
        if script is None or script.startswith("-"):
            raise Unsafe("trap with expansions or options")
        if not args[1:] or any(lit(a) not in ("EXIT", "0") for a in args[1:]):
            raise Unsafe("trap on something other than EXIT")  # DEBUG runs before every command
        self.trap_depth += 1  # runs at exit, from anywhere
        self.items(Lexer(script).parse(), scope.copy(cwds=frozenset({None})))
        self.trap_depth -= 1

    def set_options(self, args, scope, prev_conn, conn):
        """set -a counts only where it certainly runs; turning it off always counts."""
        certain = prev_conn not in ("&&", "||") and prev_conn not in PIPES and conn not in PIPES and conn != "&" \
            and not (scope.frames or scope.braces or scope.in_condition)
        i = 0
        while i < len(args):
            t = lit(args[i])
            if not t or t in ("-", "--") or t[0] not in "-+":
                break
            on, flags = t[0] == "-", t[1:]
            if flags.endswith("o"):
                i += 1
                opt = lit(args[i]) if i < len(args) else None
                if opt not in SHELL_OPTIONS | {"allexport"}:
                    raise Unsafe("set -o " + str(opt))
                flags = flags[:-1] + {"errexit": "e", "allexport": "a"}.get(opt, "")
            if not set(flags) <= set("euxva"):
                raise Unsafe("set " + t)
            if "a" in flags and (certain or not on):
                scope.allexport = on
            i += 1

    def strip_wrappers(self, words, scope):
        cwds, clears_env, env, stripped, background = None, False, {}, set(), False
        while words and lit(words[0]) in WRAPPERS:
            name = lit(words[0])
            flags, takes_arg, chdir, takes_assign, clears = WRAPPERS[name]
            clears_env |= clears
            stripped.add(name)
            same_dir, sync, i = False, False, 1
            while i < len(words):
                t = lit(words[i])
                if t is None:
                    raise Unsafe(name + " argument from an expansion")
                if t == "--":
                    i += 1
                    break
                parsed = self.split_assignment(words[i]) if takes_assign else None
                if parsed:
                    self.environment_name(parsed[0])
                    env[parsed[0]] = self.value_of(parsed[2], scope, plain=False)
                    i += 1
                    continue
                if not t.startswith("-") or (t == "-" and t not in flags):
                    break
                opt, eq, val = t.partition("=")
                if t in flags:
                    clears_env |= name == "env"
                    same_dir |= t in ("-d", "--same-dir", "--scope")
                    sync |= t in SYNC_SYSTEMD_RUN
                    i += 1
                    continue
                attached = len(t) > 2 and t[:2] in takes_arg and not t.startswith("--")
                if opt not in takes_arg and not attached:
                    raise Unsafe(name + " option " + t)
                value = t[2:] if attached else val if eq else (lit(words[i + 1]) if i + 1 < len(words) else None)
                if value is None or not PLAIN_WORD.fullmatch(value):
                    raise Unsafe(name + " option value")
                if (t[:2] if attached else opt) in chdir:
                    cwds = self.cd_result(value, cwds if cwds is not None else scope.cwds)
                i += 1 if (attached or eq) else 2
            if name == "timeout":
                i += 1  # the duration
            if name == "systemd-run":
                if not same_dir and cwds is None:
                    cwds = frozenset({None})  # a user unit starts in $HOME
                background |= not sync  # the unit runs on after systemd-run returns
            words = words[i:]
        return words, cwds, clears_env, env, stripped, background

    def cd(self, name, args, scope, prev_conn, conn, nxt, cond):
        if self.loop_depth > 0:
            self.cwd_unstable = True
        if conn == "&" or conn in PIPES or prev_conn in PIPES:
            return  # runs in a subshell
        i = 0
        while name == "cd" and i < len(args) and re.fullmatch(r"-[LPe@]+", lit(args[i]) or ""):
            i += 1
        i += name == "cd" and i < len(args) and lit(args[i]) == "--"
        target = args[i] if i < len(args) else None
        text = self.resolve(target, scope, split=True) if target else None
        if name == "popd" or (name == "pushd" and (lit(target) or "-")[:1] in "+-"):
            text = None  # pushd/popd stack rotation: wherever that leads
        new = self.cd_result(text, scope.cwds)
        if prev_conn in ("&&", "||"):
            scope.list_cwds = (scope.list_cwds or frozenset()) | scope.cwds
        if conn == "&&" and prev_conn != "||" and not cond:  # (a || cd x && b runs b when a succeeds)
            scope.list_cwds = (scope.list_cwds or frozenset()) | scope.cwds
            scope.cwds = new
        elif self.certain(prev_conn, conn, nxt, cond):
            scope.cwds = new
        else:
            scope.cwds = scope.cwds | new

    def deleter(self, name, args, cwds, scope):
        takes_arg = {"-n", "-s", "--iterations", "--size", "--random-source"} if name == "shred" else set()
        options_done, skip = False, False
        for w in args:
            t = lit(w)
            if skip:
                skip = False
            elif not options_done and t and t.startswith("-") and t != "-":
                options_done = t == "--"
                skip = t in takes_arg
            else:  # shred overwrites through a final symlink
                self.check_target(self.resolve(w, scope, split=True), cwds, follow_last=name == "shred")

    def find(self, args, cwds, scope):
        i, follow = 0, False
        while i < len(args) and (lit(args[i]) in ("-H", "-L", "-P", "-D") or (lit(args[i]) or "").startswith("-O")):
            follow |= lit(args[i]) in ("-H", "-L")
            i += 2 if lit(args[i]) == "-D" else 1
        i += i < len(args) and lit(args[i]) == "--"
        paths = []
        while i < len(args) and (lit(args[i]) or "x")[:1] not in ("-", "(", "!", ")", ","):
            paths.append(args[i])
            i += 1
        deletes, expr, j = False, args[i:], 0
        while j < len(expr):
            t = lit(expr[j])
            follow |= t == "-follow"
            if t in FIND_PRIMARIES:
                j += FIND_PRIMARIES[t]
            elif t not in ("-exec", "-execdir", "-ok", "-okdir"):
                raise Unsafe("find expression word: " + str(t))  # bfs takes start paths here too
            if t == "-delete":
                deletes = True
            elif t in ("-exec", "-execdir", "-ok", "-okdir"):
                cmd = lit(expr[j + 1]) if j + 1 < len(expr) else None
                if cmd not in DELETERS | DATA - {"mkdir", "touch"}:
                    raise Unsafe("find -exec " + str(cmd))  # (a literal name: not {} or a path)
                j += 1
                cmd_args = []
                while j + 1 < len(expr) and lit(expr[j + 1]) not in (";", "+"):
                    j += 1
                    if lit(expr[j]) != "{}":
                        cmd_args.append(expr[j])
                j += 1  # the ; or +
                if cmd in DELETERS:
                    deletes = True
                    self.deleter(cmd, cmd_args, cwds, scope)
            j += 1
        if deletes and follow:
            raise Unsafe("find follows symlinks while deleting")
        if deletes:
            for p in paths or [[("lit", ".", False)]]:
                self.check_target(self.resolve(p, scope, split=True), cwds)

    def git(self, args, cwds, scope, unit, prev_conn):
        """git runs hooks and config from the repo, which is trusted, but not code the command may have written."""
        if self.content_written or prev_conn in PIPES or unit.stdin_sources():
            raise Unsafe("git after the command wrote files, or reading stdin")
        self.runs_in_loop |= self.loop_depth > 0
        texts = self.plain_args(args, scope)
        i = 0
        while i < len(texts) and texts[i].startswith("-"):
            if texts[i] == "-C" and i + 1 < len(texts):
                cwds = self.cd_result(texts[i + 1], cwds)
                i += 2
            elif texts[i] in ("--no-pager", "--no-optional-locks", "-P"):
                i += 1
            else:
                raise Unsafe("git option " + texts[i])  # -c, --git-dir, --exec-path ...
        sub, rest = (texts[i] if i < len(texts) else None), texts[i + 1:]
        if sub not in GIT_SUBCOMMANDS:
            raise Unsafe("git subcommand " + str(sub))
        if any(o == t or t.startswith(o + "=") or (len(o) == 2 and t.startswith(o))
               for t in rest for o in GIT_OPTIONS):
            raise Unsafe("git option that runs a command")
        if any(k.startswith("GIT_") for k in scope.exported) or os.environ.get("GIT_DIR") \
                or os.environ.get("GIT_WORK_TREE"):
            raise Unsafe("git with GIT_* in the environment")
        paths, dry, force, options_done, skip = [], False, 0, False, False
        for w, t in zip(args[i + 1:], rest):
            if skip:
                skip = False
            elif not options_done and t.startswith("--"):
                options_done = t == "--"
                dry |= t == "--dry-run"
                force += t == "--force"
                skip = t == "--exclude"
            elif not options_done and t.startswith("-") and len(t) > 1:
                for k, ch in enumerate(t[1:]):
                    if ch == "e":  # -e takes the rest of the cluster, or the next word
                        skip = k == len(t) - 2
                        break
                    dry |= ch == "n"
                    force += ch == "f"
            else:
                paths.append(w)
        if dry:
            return
        if force > 1:
            raise Unsafe("git clean -ff removes nested repositories")
        for p in paths or [[("lit", ".", False)]]:
            text = self.resolve(p, scope, split=True)
            if text.startswith(":"):
                raise Unsafe("pathspec magic")
            self.check_target(text, cwds)

    def inner_scope(self, scope, cwds, env, clears_env):
        """The scope of a child shell: exported variables only, unless the wrapper cleared them."""
        vars = {} if clears_env else {k: v for k, v in scope.vars.items() if k in scope.exported}
        if clears_env:
            vars["TMPDIR"] = UNKNOWN
        elif "TMPDIR" in scope.vars:
            vars["TMPDIR"] = scope.vars["TMPDIR"]
        vars.update(env)
        return Scope(vars, vars, cwds)

    def shell(self, args, scope, cwds, env, clears_env, unit, prev_conn):
        has_c = reads_stdin = False
        i = 0
        while i < len(args):
            t = lit(args[i])
            if t in ("-", "--"):
                i += 1
                break
            if not t or t[0] not in "-+":
                break
            flags = t[1:]
            if flags.endswith("o"):  # -o NAME, -euo NAME
                i += 1
                if (lit(args[i]) if i < len(args) else None) not in SHELL_OPTIONS:
                    raise Unsafe("shell -o option")
                flags = flags[:-1]
            if t.startswith("--") or not set(flags) <= set("ceuxs"):
                raise Unsafe("shell option " + t)  # --rcfile, -i, -l, +O ...
            has_c |= "c" in flags
            reads_stdin |= "s" in flags
            i += 1
        inner = self.inner_scope(scope, cwds, env, clears_env)
        if has_c:
            if i < len(args):
                self.script(args[i], scope, inner)
            return "data"
        path = lit(args[i]) if i < len(args) else ""
        if path is None:
            raise Unsafe("script path from an expansion")
        if not path or reads_stdin:
            self.stdin_script(unit, inner, prev_conn)
            return "shell"
        if path.startswith("/"):
            raise Unsafe("shell runs a script by absolute path")
        if "/" not in path:  # bash x looks for x on PATH when the cwd has none
            raise Unsafe("shell script name without a directory: " + path)
        self.run_file(path, args[i + 1:], scope, cwds)
        return None

    def script(self, word, outer, inner):
        """Run the word as shell code in scope `inner`."""
        text = self.resolve(word, outer, raw=True)
        if UNKNOWN in text or not text.strip():
            raise Unsafe("script with unknown text")  # an unknown value could hold ; or a newline
        # Spliced values are code to the inner shell, so their quoted globs are live again.
        self.items(Lexer(text.replace(QUOTED_GLOB, "*")).parse(), inner)


def safe(command, session_cwd=None):
    if not command.strip() or any(c in command for c in "\x00\x01\x02\x03"):
        return False
    analysis = Analysis(session_cwd)
    try:
        analysis.items(Lexer(command).parse(), Scope())
        analysis.finish()
    except (Unsafe, RecursionError):
        return False
    return True


# Any word that may be a delete, matched loosely on the raw text: a false match only turns an rm-check
# prompt that would never be answered into a deny.
MAY_DELETE = re.compile(r"(?<![\w.+-])(?:rm|rmdir|unlink|shred)(?![\w.+-])|(?<!\S)-delete(?!\S)"
                        r"|\bgit\b[^\n;&|]*\bclean\b")
DENY_MESSAGE = """\
rm-safety hook: Claude Code flagged this delete as possibly dangerous, and approval prompts are off for \
unattended agents, so it was refused instead. Rewrite it so the target is obvious, then retry:
- Guard every variable in a path: rm -rf "${dir:?}/${name:?}", not $dir/$name or "$dir"/*.
- Prefer literal paths: an absolute path, or one relative to the cwd. Expand loops into explicit paths.
- Keep it a plain top-level rm: not inside sh -c, eval, $( ), xargs, trap or a heredoc. Run the delete as \
its own Bash call, after any cd.
- For scratch, use T=$(mktemp -d) and later rm -rf "${T:?}".
- Never target ~, ~/workspace, a repo root, .git or anything above the cwd.
If the rewritten command is refused again, skip the delete and say so in your report. Don't work around \
the check."""


def decide(data):
    """The hook's output, or None to leave the prompt alone."""
    if not isinstance(data, dict) or data.get("hook_event_name") != "PermissionRequest" \
            or data.get("tool_name") not in ("Bash", "Monitor") or data.get("permission_mode") != "bypassPermissions":
        return None
    tool_input, cwd = data.get("tool_input"), data.get("cwd")
    command = tool_input.get("command") if isinstance(tool_input, dict) else None
    if not isinstance(command, str):
        return None
    try:
        ok = safe(command, cwd if isinstance(cwd, str) and cwd.startswith("/") else None)
    except Exception:
        ok = False
    if ok:
        decision = {"behavior": "allow"}
    elif MAY_DELETE.search(command):
        decision = {"behavior": "deny", "message": DENY_MESSAGE}
    else:
        return None
    return {"hookSpecificOutput": {"hookEventName": "PermissionRequest", "decision": decision}}


def main():
    try:
        out = decide(json.load(sys.stdin))
    except Exception:
        return  # unreadable input: the normal prompt appears
    if out is not None:
        print(json.dumps(out))


if __name__ == "__main__":
    main()
