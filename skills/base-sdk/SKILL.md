---
name: base-sdk
description: How to work on dashpay/base-sdk the way its maintainer (kwvg) would accept, distilled from his reviews of our 38 PRs. Covers what belongs in the SDK and what must stay in rust-dashcore, how a PR has to be built, how to review one to his standard, and the steward procedure for merging while he is away. Use before writing, filing, reworking, reviewing or merging anything in dashpay/base-sdk or the PastaPastaPasta/base-sdk fork (`node/base-sdk`, `node-sdk-integration`), when deciding whether code belongs in base-sdk or rust-dashcore, and when planning what to upstream from the fork.
---

# base-sdk

`dashpay/base-sdk` is "a parsing and stateless verification SDK for Dash's
layer 1 blockchain". One person, kwvg, designed it and reviewed every line.
This skill is his standard written down, so work can continue to that standard
when he is not there to enforce it.

## Why the first gate is about scope

Between 2026-10-09 and 2026-11-13 our agents filed 38 PRs here.

- 25 merged. 17 of those drew a formal change request from him and 2 more
  were held on inline comments. The 6 that went through untouched were under
  100 lines or were follow-ups he had asked for, and he later reverted one of
  them (#72, in #127).
- 8 were closed, 31k lines in all. Three of them were 30k of those lines:
  #104 and #105, which we withdrew after he rejected their premise, and #123,
  which he closed himself. All three changed what the SDK is.

Every review we ran before filing those three checked one thing: does this
match Dash Core. None asked whether it belonged in base-sdk. Matching the
reference implementation is necessary and it is the easy part. So the order
here is fixed: decide whether it belongs (gate 1) before anyone writes it, then
build it right (gate 2).

## Gate 1: does it belong

Read [references/design-rulings.md](references/design-rulings.md) before
classifying anything. In short, base-sdk:

- holds no state, tunables, runtime policy, networking code, builders or
  devnet machinery. It decodes, encodes and checks what can be checked from
  the bytes alone;
- puts constraints in types. Byte bags are separate from operative crypto
  types, the BLS scheme is a type parameter chosen at compile time, and
  newtypes say who or what a value is;
- makes no consensus-level choice for the caller. Where the reference
  implementation makes one, the SDK exposes the pieces and the caller names
  the choice;
- detects the same faults as the reference implementation. It does not copy
  its check order, its debugging allowances or its internal structure;
- adds public API only for a consumer that exists. "Preemptive creation of
  new API surface without guaranteed downstream consumers is suboptimal"
  (#92).

Classify every proposed change, from the diff and not from its description:

| Class | What it is | Who can approve |
|---|---|---|
| A | Makes the SDK accept, refuse, decode or encode the same things as the reference implementation, inside existing types and APIs | Steward |
| B | A new typed message, payload or primitive that a named consumer needs, written in the style of the ones already there | Steward |
| C | A new public abstraction: trait, macro, wrapper, feature flag, crate or dependency, or a change to how existing types are shaped | kwvg. While he is away: a unanimous `council`, and only if a consumer is blocked without it |
| D | Conflicts with a ruling: state or tunables; devnets, builders or option handling; a scheme chosen at run time, or a value that carries one or crosses schemes; a consensus-level choice made inside the SDK; check-order parity; debugging allowances; node or handler policy; V1 transport | Nobody. It goes in rust-dashcore |

Notes on applying it:

- When unsure between two classes, pick the stricter one.
- "It matches the reference implementation" does not make something class A.
  #109 matched the reference's check order and was closed. Check the D row
  first.
- A reshaping he asked for in a review thread (a newtype per signature role,
  a `Signable` type, wrapping the operator key) is already approved. Do it in
  that PR. It is not a class-C escalation.
- A class-C idea gets a short written proposal (problem, the API, the
  consumer, what it replaces, why it cannot live downstream) before any code.
  The proposal is what the council decides on. #123 was 14.5k lines written
  before that question was asked.
- Any change to operative crypto in `dash-pkc` (curve arithmetic, signing,
  verification, aggregation, key derivation, encryption) is treated as class
  C whatever its size. The crate has had no formal security review, and a
  wrong merge there is the costliest mistake available in this repo.

## Gate 2: is it built right

[references/pr-conventions.md](references/pr-conventions.md) is the checklist:
PR shape, commits, description, comments, naming, tests, corpora and generator
programs. Each rule there cites the review it came from. The ones that were
violated most often:

- Comments that explain, restate the code, name C++ symbols, or say that
  something follows the reference implementation. That is the baseline
  expectation and never needs saying.
- Tautological tests, and the same test repeated per struct.
- Corpora used for policy cases, or built from synthetic or unreproducible
  data.
- Fixes appended as new commits. A fix goes into the commit that introduced
  the problem, and the branch is force-pushed.
- Changelog entries for unreleased crates.

`just comb` must pass on every commit. He called this "not optional".

Base-sdk commits never carry an AI co-author trailer or an AI author address.
`lint_commit` rejects them. This overrides any general instruction to add
`Co-Authored-By`. Disclosure goes in the PR template's "Agent disclosure"
section instead.

## Roles

One agent holds one role on a given PR. The author never approves or merges
their own work, which is stricter than what has happened here before, and the
steward does not author feature work.

**Author** (any lane that writes base-sdk code):

1. Classify the change. D stops here. For C, or when the class is unclear,
   send the steward a one-paragraph question before writing code.
2. Check the fork rule below if the work starts in the fork.
3. Build it to the conventions. Run `just comb`.
4. Self-review against both reference files, then file with the repo's PR
   template. Push the branch to `dashpay/base-sdk` (branch `pasta/<slug>`),
   not to a fork. The PR title is linted against the commit subject pattern.
5. When CI and thepastaclaw are clean, comment on the PR: `Ready for steward
   review at <head sha>`. A push after that withdraws the signal, so post it
   again.
6. Answer maintainer and steward threads first, before any other work. Make
   the change that was asked for. If you disagree, say so with a permalink to
   the reference implementation, and leave the thread open.

**Reviewer** (asked to review a base-sdk PR):

1. Read the diff, both reference files, and every earlier thread on the PR
   and on PRs it supersedes. A finding he already raised once is a blocker
   the second time.
2. Report scope first (class, with the ruling it touches), then conformance
   (is each claim backed by a corpus row or a permalink), then conventions.
3. Do not ask for things he has declined: check-order parity, V1 transport,
   conversions between schemes, benchmarks with nothing to compare against,
   per-struct copies of a test, extra hardening of `contrib` scripts.

**Steward** (only a thread pasta has explicitly assigned as base-sdk steward;
this skill does not grant the role):

Follow the procedure below. The steward's job is to protect the SDK's design,
and merging is the smaller part of it. A PR held back costs days. A wrong
design merged costs a revert and his trust.

kwvg is not expected to review anything before mid-December 2026 (pasta,
2026-11-13). Nothing is parked for him. What he would have decided goes to a
council instead (below), and the log records it for him to read later.

## Steward procedure

**If kwvg has given `utACK` on the exact head and CI is green, merge it**
(step 6). If his `utACK` is on an older head, read the range since. Merge only
if it holds nothing but the fixes his review asked for.

Otherwise, for each PR, in this order. Stop at the first failure and request
changes.

1. **Scope.** Classify it yourself. A and B continue. C goes to a council.
   For D, say where it belongs and close.
2. **His threads.** Every thread kwvg opened on this PR, and on any PR it
   replaces, is resolved the way he asked. Read the code, not the reply. If
   the author argued instead of making the change, send it back to be made.
   If the author still disputes it, a council settles it. Where he offered a
   choice, record which one was taken.
3. **History.** Base is `develop`, and a stack merges from the bottom up.
   Rebased. No commit undoes or edits what an earlier commit in the same PR
   added. Fold fixups and force-push first.
4. **Proof.** `just comb` passes on every commit, run by you or by CI on the
   exact head. CI is green on the exact head, Codecov patch checks included.
   Never merge over a red check, and never re-run one without a reason you
   can state.
5. **Independent review.** A reviewer from a different model family than the
   author, given the diff and this skill and not the author's summary. Use
   two reviewers for anything over about 500 lines of library source or
   anything touching `dash-pkc`. All findings are answered before merge.
6. **Merge.** From a clean, current `develop` checkout,
   `./contrib/git_merge.py -R dashpay/base-sdk <N>`, then push `develop`.
   The script makes a `--no-ff` merge whose message holds the commit list and
   the description, which is how every merge here is recorded. Squash and
   rebase merges are disabled. Then delete the PR branch on
   `dashpay/base-sdk`.
7. **Ledger.** Add the entry (format below) and tell the fork's owner to fold
   the merged version into the fork.

### Council decisions

The steward runs the `council` skill for these, in place of kwvg:

- a class-C proposal;
- any change to operative crypto in `dash-pkc`;
- a PR he never reviewed that adds more than about 300 lines of library
  source. Every PR of that size he did review drew real changes, so one clean
  review from us is weaker evidence than it looks. The council replaces the
  independent review of step 5 for such a PR;
- a thread of his that the author still disputes;
- a steward decision that would loosen this skill (see below).

Give the council the diff or proposal, this skill and both reference files,
and the consumer that needs it. Do not give it the author's summary. Ask two
questions: would kwvg accept this given his rulings, and is it correct.

- All three members agree: it proceeds through the remaining steps.
- They do not agree: it does not merge. The code stays downstream in
  rust-dashcore, and the log lists the question for kwvg.
- On a disputed thread, his position stands unless a permalink to the
  reference implementation shows it is factually wrong.
- Class D never goes to a council. A council applies his rulings and cannot
  overturn one.

A steward decision may correct a fact or tighten a rule on the steward's own
authority. One that makes something easier to merge than this skill as
written (a lower class, a finding reviewers are told to stop raising) is
provisional until a unanimous council confirms it. Until then the skill as
written applies, and the entry in `design-rulings.md` section 12 says
"provisional" (pasta, 2026-11-13).

pasta is asked only for the items in the list below, and when a council that
did not agree leaves the node program blocked.

The steward never does these, and asks pasta if one seems necessary:

- publish to crates.io, tag, or bump versions;
- change `AGENTS.md`, the style guide, the PR template, `commit.toml`,
  `deny.toml`, CodeQL, semgrep or Codecov policy, MSRV, or the CI layout;
- dismiss or edit kwvg's reviews. They stay as he left them;
- force-push `develop`;
- merge class D, class C without a unanimous council, or anything the two
  reviewers disagree on.

Keep at most 5 PRs open, drafts included. That limit was his, and it is a
sound bound on work in progress with or without him.

### Ledger entry

The stewardship log is where kwvg will read what happened. Its location is
given in the steward thread's brief. One entry per merge or close:

```
#<N> <title>  merged <date> at <head sha>
class: A|B|C   reviewers: <model, effort> ...
decided by: steward | council, unanimous: <the question it answered>
kwvg's review: utACK at <sha> | reviewed, changes made since | never reviewed
his open threads: none | <thread> settled by <what was done>
judgment calls: <anything he might have decided differently, or "none">
revert: git revert -m 1 <merge sha>
```

Write the judgment-calls line honestly. It is the line he will read first.

## The fork

`PastaPastaPasta/base-sdk` exists so the Rust node can build before upstream
catches up. pasta's rule (2026-11-05): everything merged into the fork must be
something we want upstream.

- A change enters the fork only if it would pass gate 1 as class A or B.
  Class D never enters. It goes in rust-dashcore.
- The fork's delta against `develop` is a list of debts. It is not a list of
  upstream candidates. As of 2026-11-13 about 10k of its 15.5k library lines
  were class D (the run-time BLS scheme and the wrappers that carry it, the
  relic engine, `bls::core`, `ProtoCtx`), and the node imported them widely.
  That code is paid down by moving it node-side, not by filing PRs.
- After a PR's review, the fork takes the reviewed version. A fork that
  carries the pre-review version has the node building against code the
  maintainer already asked to change.
- Before upstreaming fork code, strip what the fork tolerates and upstream
  does not: C++ symbol names, file and line citations, internal task labels,
  citations of the fork itself, changelog entries for unreleased crates.

## What this skill cannot do

It records what kwvg has said. It cannot predict what he would say about a
design question he has not seen. That is why class C needs a unanimous
council while he is away, and why the ledger exists. If a case is not covered
here, treat it as class C.

Add to the reference files when he rules on something new. Quote him and cite
the PR.
