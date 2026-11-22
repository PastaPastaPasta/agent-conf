# PR conventions

How a base-sdk PR is built. The repo's own `AGENTS.md`, `docs/dev/guide_rust.md`
and `.github/PULL_REQUEST_TEMPLATE.md` come first; read them. This file adds
what kwvg had to say in review because those documents did not stop us. PR
numbers in brackets are where he said it.

His standing instruction to our agents is on #65 (2026-10-15). It ends: "Do
not write tautological tests. Write code in the style of this codebase.
Commits are expected to be bisectable, `just comb` must succeed. This is not
optional."

## Contents

1. PR shape
2. Commits
3. Description
4. Changelog
5. Comments and docs
6. Naming and code
7. Tests
8. Corpora
9. Generator programs and scripts
10. Review etiquette
11. Self-check before filing

## 1. PR shape

- One theme per PR. Do not split a theme across several small PRs. #59, #63,
  #64 and #65 were closed and redone as one PR, #67. "Avoid many small pull
  requests ... pick a theme or a cluster of changes, each pull request should
  attempt to have 6-14 commits." [#65]
- Split when a part stands on something else. He asked for it twice: test
  infrastructure before the change that needs it (#101 became #112 then
  #101), and a check held back until the crate it depends on could express it
  (#88, later #129).
- A change that is small by nature is fine small: a parameter sync, or a
  follow-up he asked for (#102, #108, #125 merged with one or two commits).
- At most 5 open PRs, drafts included. [#65]
- Keep branches rebased on `develop` and free of conflicts with each other.
  When he says rebase, rebase every open PR the same day. [#65, #86, #121]
- Push the branch to `dashpay/base-sdk` as `pasta/<slug>`. After a stacked PR's
  base merges, retarget to `develop`. [#101]
- Delete the branch once the PR merges or closes.

## 2. Commits

- Subject is `namespace%type[(scope)][!]: description`. Namespaces: `sdk`,
  `types`, `num`, `pkc`, `pow`, `params`, `primitives`, `script`, `p2p_core`.
  Types: `build`, `chore`, `ci`, `doc`, `feat`, `fix`, `lint`, `misc`, `perf`,
  `refac`, `test`. Lines at most 73 wide, message at most 5 lines.
  (`maint/commit.toml`)
- No AI author, committer or `Co-authored-by` address. `lint_commit` blocks
  them, Anthropic and OpenAI addresses included.
- Every commit builds, tests and lints on its own. `just comb` runs
  `just test lint fuzz::test` on each commit from `develop` to `HEAD`.
- No churn inside a PR. A commit never edits, renames or removes what an
  earlier commit of the same PR added. A review fix is folded into the commit
  that introduced the problem and the branch is force-pushed. "They must be
  structured to avoid churn within each other while still being individually
  readable." [#65] Example of doing it right: on #74 the module rename went
  into the commit that created the module.
- A move is its own commit, unless the edit is small enough that Git still
  registers the move. [#65]
- A helper for another crate goes in its own commit, before its first user.
  [#73]
- Where there is a changelog commit, it is the tip commit. [#57]
- If a change depends on new test infrastructure, the infrastructure commit
  comes first, so each step is proven on its own. [#101]

## 3. Description

- Use the template's sections and leave out the ones that do not apply.
- Motivation says what is wrong today and what the PR does about it.
  "Describe what the PR does, not what it doesn't." [#57]
- Not long. "PR description is excessively long." [#57] A table of change and
  note, one row per change, has been accepted every time (see #119).
- Citations of the reference implementation go here, as links to the lines at
  a tag or commit, in the manner of #20. They do not go in code. [#57, #65,
  #119]
- "How Has This Been Tested?" is the commands to run, as in #60. It is not a
  paragraph. [#57]
- Breaking Changes holds the wording meant for the changelog. For an
  unreleased crate that is the only place it appears.
- Fill in Agent disclosure: model, version, runner, effort, and what reviewed
  it. Leave the checklist's "I did not use agentic assistance" box unticked,
  as our merged PRs do.
- Do not use the phrase "as the reference implementation does" here either.
  [#124]

## 4. Changelog

- Unreleased crates get no `CHANGELOG.md` entry. Today those are
  `dash-primitives`, `dash-p2p-core` and `dash-script`. The wording goes in
  the PR description. [#121, #126]
- Before 1.0 there is no "Fixed" heading. A fix goes under "Changed". [#101]
- Changes to internal macros need no entry. [#119]

## 5. Comments and docs

`AGENTS.md` is the rule: brief, relevant to the reader or actionable, no
exposition, no history, no colons, no Unicode dashes. What he had to repeat:

- Do not restate the code. "Avoid expository comments, what is self-evident
  from reading the code does not need to be restated, what isn't in the code,
  has no sense in being stated unless it's a placeholder for code that
  eventually shows up, but that would be a TODO flagged to a specific
  contributor." [#121] Also "Overexplaining" [#114], "Extremely wordy" [#88],
  "Second line not needed, first line is enough" [#121].
- Never write that something follows the reference implementation.
  "'this follows the reference implementation' is redundant text, the library
  is supposed to match the reference implementation." [#101] "Stop writing
  'as the reference implementation's transport types it', that's a baseline
  expectation." [#124]
- Say "reference implementation", not "Dash Core". No C++ function or variable
  names, no file and line citations: "they can go stale". [#57, #65, #119]
- No current values in prose. Link the constant: "Do not mention the current
  limit as comments, risks going stale." [#67]
- A struct's doc is a headline. Decoder and encoder facts go on the
  `BaseCodec::decode` and `encode` docs. [#86, #87]
- Do not restate what another function does. "Restating comment of
  `compress`'s inner behaviour creates drift risk." [#86]
- A double hyphen is not a way around the long-dash rule. "Not in the spirit
  of the agent guidance provided." [#88]
- A file's top line is one line. "If it becomes paragraphs, it's no different
  than standard code comments." [#112]
- A README is a summary. Detail goes in the file it describes. No facts that
  churn, such as a pinned hash. Do not describe what has not been done, and
  do not list internal plumbing. [#101, #112]
- A script's docstring says what and why, not how. "'Only established RPCs
  are read' is information for the reviewer, not the reader." [#107]
- Ambiguous phrasing gets rewritten. "'the error decoding the message' can be
  read either way at a glance." [#124]
- A `TODO` names a person: `TODO(pasta)`. [#88, #122]
- No internal task labels, decision numbers or fork references anywhere.

## 6. Naming and code

- Sizes end in `_SIZE` and counts in `_COUNT`. [#67]
- Predicates read `is_canonical_pk`, not `pk_is_canonical`. [#101]
- Prefix a type with its subsystem when it will be imported elsewhere
  (`GovSyncStatusCount`). [#74]
- Module names are the subsystem (`tx_reconcile`). [#74]
- A fixed salt or prefix string is a named constant (`PREFIX_STR`). [#121]
- A one-line wrapper does not need to exist. "Doesn't need its own function."
  [#121]
- Write it plainly. "Clever code golf is hard to read." [#87]
- No `serde(default)` or similar attribute without a stated need. [#88]
- Scheme-specific helpers live with their scheme or in the scheme
  abstraction, not in the other scheme's file. [#101]
- If `thiserror` already produces the string, do not map variants by hand.
  [#73]
- Name things for what they are in general. `check_sptx_except` with a list
  of allowed errors, not `check_sptx_regtest`. [#114]
- A network upgrade with several features is named for the release
  (`CoreV24`), not for one feature. [#88]

## 7. Tests

- No tautological tests. A test that a hardcoded value equals itself, that a
  constructed genesis hashes to the known hash, or that a derived trait works,
  proves nothing. [#58, #84, #104]
- Test a macro once, on a stand-in struct, not at each place it is used.
  "It's effectively a check on `codec_base!` itself." [#126]
- Do not repeat one test per struct. "Same exact tests, different struct."
  [#129] Put the parity test where the shared code lives. [#88]
- Fold a new assertion into the existing corpus test for that type
  (`corpus_<msg>`). [#74]
- A test goes in the module unless its logic needs a separate file under
  `tests/`. [#67, #86]
- Use `rstest` cases for policy tables and `#[fixture]` for shared setup.
  [#86, #88]
- When a helper is replaced, its tests survive in some form. [#86]
- Property tests belong to the crate that owns the property. See
  design-rulings §5.

## 8. Corpora

- A corpus (`pkgs/<crate>/corpus/*.json5`) is for codec equivalence that needs
  the reference implementation: bytes in, value out, bytes back. Policy cases
  are `rstest` tables in Rust. "Please do not use corpora for validating
  policy ... this bloats the corpora and blends synthetic from established
  chain facts." [#87, #88]
- Transactions and blocks are real, from mainnet or testnet, cited by txid or
  block. [#88]
- Each vector has a comment saying what it pins and why it is an edge case.
  [#73]
- The file header holds only provenance and how to regenerate. Field
  descriptions sit above the section they describe. [#73]
- Headers wrap at 80 columns so they read without word wrap. Comments on
  vectors are not wrapped, since JSON5 has no column limit. [#87, #88]
- A claim of alignment should come with corpus rows. For a fix or a new
  consensus type in `dash-primitives` or `dash-p2p-core` he calls updating
  the corpus "ideal. This isn't always necessary but is encouraged". [#65]
- Coverage is enough, not total. "It does not need to achieve perfect
  coverage, just enough coverage." [#84]
- No `.md` files inside `corpus/`.

## 9. Generator programs and scripts

- They live in `pkgs/<crate>/contrib`, excluded from the published crate.
  Utility files go in `contrib/util` and are not mentioned in the README.
  [#101, #112]
- The reference implementation is pinned as a submodule, as `fuzz/pow` pins
  `sphlib`. He suggested it ("It may be advisable") and it is what merged.
  [#101]
- `contrib` is developer tooling and gets lighter treatment than `maint`:
  "tools in `contrib` come with less belt and suspenders checks in the
  interest of reducing code ownership and higher expected churn". A bot's
  hardening request on a `contrib` script can be declined. [his #70, #111]
- Python, not shell, so scripts run on non-POSIX hosts. [#101]
- CMake or Bazel, not Autotools. Patch the build file back in if needed.
  [#112]
- Dependencies go in `contrib/nix/mods/corpora.nix`, named for no single
  feature. Shells compose modules and define nothing themselves. [#112]
- Keep programs small. "Extremely large corpus generation programs are an
  anti-pattern." If a case can be built in Rust, build it there. [#88]
- Fixed inputs are documented `constexpr` constants at the top of the file,
  apart from the logic. Literal arguments carry `/*name=*/` comments. [#112]
- C and C++ comments are Javadoc-style `/** */` with `@` commands. Namespaces
  close with `} // anonymous namespace`. No stray blank lines. [#112]
- A CI job builds the programs and fails if a corpus differs from the
  committed one, weekly and when the files or the dev shell change. [#112]
- The programs stay inside CodeQL's coverage. [#112]

## 10. Review etiquette

- His vocabulary: `utACK <sha>` approves that exact head. "Concept ACK"
  agrees with the idea and still wants the comments resolved. "conditional on
  green CI" means do not merge red. "can be addressed in follow-up" means
  file the follow-up and link it from the thread. A point he calls
  non-blocking but easy is still done in the same PR: "would rather it be
  done here rather than in a follow-up". [#107]
- Answer every thread with what changed and the commit it is in. Apply a
  point everywhere it applies, including in the other open PRs, and say so.
- Do not defer a blocking finding to "the maintainer's call" when the answer
  is knowable from the reference implementation. On #87 that cost a round.
- A finding he raised on one PR is known on all later ones. `KeyEdit` was
  flagged on #88 and came back on #129: "Believe this enum was specifically
  flagged in a prior review."
- He expects thepastaclaw's findings answered too. [#67, #112]
- Reply to him before doing anything else, even if the fix will take hours.
  Say what is done and when the push lands.

- While the steward reviews (from 2026-11-13): its review is a comment
  review headed "Steward review at <sha>", because the account that files our
  PRs cannot request changes on them. Its findings are numbered. Answer by
  number, and treat it as a change request.

## 11. Self-check before filing

Run these over the diff. Each should print nothing, or only lines you can
justify.

```sh
base=$(git merge-base origin/develop HEAD)
added() { git diff "$base" HEAD -- "$@" | grep '^+' | grep -v '^+++'; }

# In comments: C++ names, file citations, "Dash Core", baseline phrasing
added 'pkgs/*/src/*' | grep -E '//' | grep -nE '\.(cpp|h)\b|[A-Z][A-Za-z]+::[A-Z][A-Za-z]+\(|Dash Core|reference implementation (does|types|reads|writes)|as the reference|follows the reference'
# Non-ASCII characters, double dashes, decorative separators
added 'pkgs/*/src/*' | LC_ALL=C grep -nE '[^ -~]| -- |// ?[-=]{4,}'
# Internal labels and fork citations
added . | grep -nE '\b(BS|DEC|BL|CH|EV)-?[0-9]+[a-z]?\b|PastaPastaPasta|node-sdk|node/base-sdk'
# Changelog entries for unreleased crates
git diff --stat "$base" HEAD -- pkgs/primitives/CHANGELOG.md pkgs/p2p_core/CHANGELOG.md pkgs/script/CHANGELOG.md
# Commits that undo or trim earlier commits of the same PR
git log --format='%h %s' "$base"..HEAD | grep -niE 'trim|drop the|revert|fixup|address review|follow.?up'
# Blocked trailers
git log --format='%ae %ce %b' "$base"..HEAD | grep -niE 'anthropic|openai|co-authored-by'
```

Then `just comb`.
