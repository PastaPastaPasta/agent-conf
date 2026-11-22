#!/usr/bin/env python3
"""Generate a working compile_commands.json for a Dash Core checkout or worktree.

The build system's own compile_commands.json has broken include flags, and git
worktrees never get one at all. Both make clangd fall back to guessed flags, so
agents see a wall of "'boost/...' file not found" noise that has nothing to do
with the code they are editing.

This rewrites the main checkout's database for a target directory:

  * -I<depends-prefix>          -> -I<depends-prefix>/include   (boost, Qt, libevent)
  * -I/include, -I/include/Qt*  -> dropped (empty CMake var expanded to garbage)
  * -I<main>/src                -> -I<target>/src, with <main>/src kept as a
                                   fallback so generated headers such as
                                   config/bitcoin-config.h still resolve in a
                                   worktree that was never ./configure'd
  * -I<main>/depends/...        -> left alone; worktrees have no built depends

Usage:  dash-clangd-db.py [target-dir]      (default: cwd)
"""

import json
import os
import subprocess
import sys

# Include dirs that live in the tree and are not always in the raw database.
IN_TREE_INCLUDES = (
    "src",
    "src/dashbls/include",
    "src/dashbls/depends/relic/include",  # relic_conf.h, pulled in via bls.hpp
    "src/immer",
    "src/secp256k1/include",
    "src/minisketch/include",
    "src/crc32c/include",
    "src/leveldb/include",
    "src/univalue/include",
)


def git(target, *args):
    out = subprocess.run(
        ("git", "-C", target) + args,
        capture_output=True, text=True, check=True,
    )
    return out.stdout.strip()


def resolve_roots(target):
    """Return (target_root, main_root) for a checkout or one of its worktrees."""
    target_root = git(target, "rev-parse", "--show-toplevel")
    common = git(target, "rev-parse", "--path-format=absolute", "--git-common-dir")
    main_root = os.path.dirname(common.rstrip("/"))
    return os.path.realpath(target_root), os.path.realpath(main_root)


def fix_flags(tokens, target_root, main_root):
    out = []
    for tok in tokens:
        if not tok.startswith("-I"):
            out.append(tok)
            continue

        path = tok[2:]

        # Bogus paths from an empty CMake variable: -I/include, -I/include/QtWidgets
        if path == "/include" or path.startswith("/include/"):
            continue

        # depends prefix without /include -- the reason boost never resolves.
        inc = os.path.join(path, "include")
        if os.path.isdir(inc) and not os.path.isdir(os.path.join(path, "boost")):
            out.append("-I" + inc)
            # Qt headers are included unqualified (<QAbstractListModel>), so each
            # module dir has to be on the path in its own right.
            for name in sorted(os.listdir(inc)):
                if name.startswith("Qt") and os.path.isdir(os.path.join(inc, name)):
                    out.append("-I" + os.path.join(inc, name))
            continue

        out.append(tok)

    # Point source includes at the target tree, keeping the main checkout as a
    # fallback for headers that only exist after ./configure (src/config/*).
    prefix = []
    for rel in IN_TREE_INCLUDES:
        for root in (target_root, main_root):
            d = os.path.join(root, rel)
            if os.path.isdir(d) and "-I" + d not in prefix:
                prefix.append("-I" + d)

    # Without this, clientversion.h skips config/bitcoin-config.h entirely and
    # every PACKAGE_* define goes missing. Autotools passes it; the CMake-derived
    # database does not.
    if "-DHAVE_CONFIG_H" not in out:
        prefix.append("-DHAVE_CONFIG_H")

    seen = set(prefix)
    tail = [t for t in out if not (t.startswith("-I") and t in seen)]
    # Keep the compiler first; include dirs go right after it.
    return tail[:1] + prefix + tail[1:]


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    # --auto is for the SessionStart hook: stay silent unless work was done, and
    # never fail in a way that disrupts the session.
    auto = "--auto" in sys.argv

    target = os.path.abspath(args[0] if args else os.getcwd())
    target_root, main_root = resolve_roots(target)

    # Preserve the build system's untouched output so this stays idempotent
    # even when target_root is the main checkout.
    raw = os.path.join(main_root, "compile_commands.json.raw")
    src = os.path.join(main_root, "compile_commands.json")
    if not os.path.exists(raw):
        if not os.path.exists(src):
            msg = (
                f"no compile_commands.json in {main_root}; build it first "
                f"(bear -- make -j8, or cmake -DCMAKE_EXPORT_COMPILE_COMMANDS=ON)"
            )
            if auto:
                return
            sys.exit(msg)
        os.replace(src, raw)

    dest = os.path.join(target_root, "compile_commands.json")
    if auto and os.path.exists(dest) and os.path.getmtime(dest) >= os.path.getmtime(raw):
        return  # already current for this tree

    with open(raw) as fh:
        db = json.load(fh)

    for entry in db:
        entry["directory"] = target_root
        if entry.get("file", "").startswith(main_root + os.sep):
            entry["file"] = target_root + entry["file"][len(main_root):]

        if "arguments" in entry:
            entry["arguments"] = fix_flags(entry["arguments"], target_root, main_root)
        else:
            import shlex

            toks = fix_flags(shlex.split(entry["command"]), target_root, main_root)
            entry["command"] = " ".join(shlex.quote(t) for t in toks)

    with open(dest, "w") as fh:
        json.dump(db, fh, indent=1)

    if auto:
        print(
            f"clangd: generated compile_commands.json for this tree ({len(db)} entries). "
            f"C++ diagnostics resolve boost/Qt/depends headers correctly here, so treat "
            f"them as real findings rather than include-path noise."
        )
    else:
        print(f"wrote {dest} ({len(db)} entries, sources from {target_root})")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # never break a session over IDE plumbing
        if "--auto" not in sys.argv:
            raise
        print(f"clangd db setup skipped: {exc}", file=sys.stderr)
