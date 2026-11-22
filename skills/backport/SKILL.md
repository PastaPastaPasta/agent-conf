---
name: backport
description: Backport specific Bitcoin Core PRs into Dash Core from a local checkout, for a developer who wants a particular area or set of backports done sooner than the automated backport pipeline would get to them. Covers checking what's already done, using the pipeline's prerequisite map, pulling in the prerequisites and follow-ups the set needs, preferring upstream fixes over Dash patches, commit conventions, a local build-and-diff check, and filing. Use when asked to backport, port or "bring over" upstream PRs, or to finish a partial backport.
---

# Backport

This is for a developer who wants to push a specific area forward (a subsystem, a build-system change, a fix and its follow-ups) instead of waiting for the automated pipeline. It is lighter than the pipeline: use judgement, build on your own platform, and let the PR's CI cover the rest.

Read Dash's `AGENTS.md` ("Backport Work" and "Upstream features Dash never adopts") first. The goal is a branch where each upstream PR is one faithful commit and every difference from upstream is explained.

## Before you start

- **Is it already done or in flight?**
  - Search develop for `bitcoin#N`, `bitcoin/bitcoin#N` or `Merge #N:`. A trailing `(#M)` is the Dash PR number, and `gui#N` is a separate number space.
  - Search open PRs: `gh pr list -R dashpay/dash -S "bitcoin#N" --state all`.
  - Check whether the pipeline's map (below) shows it in a batch.
  - Partial backports count as done.
- **Is it meant for now?** Deprecations and feature removals usually wait for the next Dash major release.
- **What follows it upstream?** Check:
  - the PR's "Fixes" and "Follow-up to" links;
  - `git log bitcoin/master --grep "#N"`;
  - later upstream changes to the same lines: `git log -S'<line>' bitcoin/master -- <file>`;
  - Dash `TODO`s that name upstream PRs.

  Fast-followers often belong in the same series.

Pickaxe and prerequisite searches need full history and a `bitcoin/master` ref; a shallow clone gives wrong answers.

## Prerequisites: start from the pipeline's map

The automated pipeline publishes the prerequisite map it has already computed at `https://thepastaclaw.github.io/backport-status/data/map.json`. You can browse it at `https://thepastaclaw.github.io/backport-status/#map/<N>`.

- **What's in it:**
  - `nodes`: each tracked upstream PR, with `status`, `reason`, `merge`, `already_on_develop` and its `batch`.
  - `edges`: `{from, to, kind, evidence}`, meaning `from` needs `to`.
  - `base`: the develop commit the map was computed against.
- **Edge kinds:**
  - `file`: `to` created a file the change touches;
  - `context`: removed lines Dash never had;
  - `doc`: a release note for `to`;
  - `note`: named in the tracker's notes;
  - `build`: found from a compiler error;
  - `adapt`: a hunk an earlier backport attempt deferred to `to`;
  - `review`: raised in review of an earlier attempt.

A node's `batch.dash_pr` is the Dash PR carrying it. If the file has an `error` field instead of nodes, the export failed; skip it.

To list everything your set needs:

```bash
curl -s https://thepastaclaw.github.io/backport-status/data/map.json -o map.json
python3 - map.json 30043 31130 <<'EOF'
import json, sys
m = json.load(open(sys.argv[1])); want = [int(a) for a in sys.argv[2:]]
nodes = {n["number"]: n for n in m["nodes"]}; need = {}
for e in m["edges"]: need.setdefault(e["from"], []).append(e)
seen, stack = set(), list(want)
while stack:
    n = stack.pop()
    if n in seen: continue
    seen.add(n); node = nodes.get(n, {})
    print(n, node.get("status", "untracked"), node.get("title", ""))
    for e in need.get(n, []):
        print(f"   needs {e['to']} [{e['kind']}] {e['evidence']}"); stack.append(e["to"])
print("map base", m["base"])
EOF
```

The map is a head start, not the answer:
- If it can't be fetched, skip it and probe directly.
- It is only as fresh as `base`.
- It covers only the versions the pipeline tracks. A PR with no node or no edges just hasn't been probed.
- Where the tree disagrees with the map, trust the tree.

For anything the map doesn't cover, a dry `git cherry-pick -m1 --no-commit <merge>` (then `--abort`) shows where to look. Prerequisites usually show up as one of these:
- a file Dash never had;
- removed context lines Dash never had (`git log -S'<line>' <merge>^1`);
- an identifier or header Dash lacks;
- a `doc/release-notes-M.md` in the diff, meaning bitcoin#M is owed.

These don't count as prerequisites:
- files Dash deliberately deleted;
- PRs already on develop, even if their lines have drifted since.

**Pull in what the set needs to land whole.** That's part of the job.
- Take the smallest set that gets there.
- Skip a prerequisite when the hunk needing it is honestly not applicable to Dash.
- List each prerequisite you added in the PR body, with what it supplies.
- If the chain grows far past what was asked, check in before carrying on.

Order commits by dependency (upstream merge order within a PR). If B needs A's mechanism, A goes in first, in the same PR or an earlier one.

## Upstream first, Dash patch last

Before writing a Dash-only fix (a workaround, guard, flag or build tweak), look for a later upstream PR that already fixes it, and backport that instead. If there isn't one, check with whoever asked before diverging. Hand-rolled workarounds for problems upstream already solved are the most common reason a backport series gets sent back.

## Making the commits

- **One commit per upstream PR.** Use `git cherry-pick -m1 -x <merge>` with the upstream merge subject verbatim (`Merge bitcoin/bitcoin#N: …`). Tooling reads these subjects to know what's already backported.
- **Resolve conflicts against Dash's code.**
  - Never delete Dash features (masternodes, LLMQ, governance, …) to make a hunk apply.
  - Don't invent helpers.
- **Carry the change to Dash's own counterparts.** This is the most common thing reviewers catch:
  - Dash-only sibling files and CI jobs;
  - `scripted-diff:` scripts, re-run on the Dash tree;
  - Dash constants (`COIN` amounts, version numbers, datadir `.dashcore`);
  - code the change makes dead.
- **Explain differences in the commit body:**
  - `Dash adaptations:` what you changed and why.
  - `Not applicable to Dash:` permanent omissions, such as features Dash never adopts, MSVC/vcpkg, and Bitcoin-only CI. These don't make a backport partial.
  - `Omitted (partial backport):` only for something deferred to a named `bitcoin#M`, with the subject prefixed `partial `. Landing M first is usually better.
- **Keep every commit building.** Fold fixes into the commit that needs them instead of stacking fix-up commits at the tip.

## Checking it locally

- **Build on your platform** with warnings as errors, and run the unit and functional tests the change touches. That is enough before pushing. The PR's CI covers the other platforms and configurations; if it fails somewhere you can't build, read the logs and fix from there.
- **Compare each commit with upstream.** Every difference should be one you explained:

  ```bash
  diff <(git diff <merge>^1 <merge> -- <file>) <(git diff <sha>^ <sha> -- <file>)
  ```

  Clean picks deserve a glance too, since they can still carry a Bitcoin-only constant.
- **"Same as upstream" isn't the end of it.** If something looks wrong upstream too, check whether upstream fixed it later.

## Filing

- **PR title:** `backport: bitcoin#A, bitcoin#B (partial), …`.
- **PR body:** each upstream PR with its adaptations, what was omitted and why, and the prerequisites you added.
- **Review against upstream:** the `backport-pr-codereview` skill checks each hunk once the PR is pushed.
- **After rewriting history,** make sure the commit bodies and the PR body still match the commits.
- **Side findings** (a needed bump, a missing prerequisite) become an issue or a follow-up, not just a line in the report.

## Report

Give one line per upstream PR:
- landed whole;
- partial, and what it's waiting on;
- not applicable, and why;
- blocked, and on what.

Then list the prerequisites you added and any Dash-only commits, with the reason for each.
