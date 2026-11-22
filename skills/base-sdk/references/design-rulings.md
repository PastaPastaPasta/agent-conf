# Design rulings

What kwvg has ruled about the shape and scope of base-sdk. Each entry gives the
rule, his words, the PR, and what to do instead. PR numbers are
`dashpay/base-sdk`. Quoted text is his review comments, verbatim, unless the
entry says it is from `AGENTS.md`, a README or a PR title.

## Contents

1. Stateless: no state, tunables or runtime policy
2. Codec only: no transport state, BIP324 only
3. Byte bags and operative types; the scheme is a type
4. Consensus-level choices belong to the caller
5. Crate boundaries
6. Conformance means the same faults
7. Types carry meaning
8. One mechanism, extended
9. The Bitcoin-inherited parts follow rust-bitcoin
10. What counts as evidence
11. Where rejected work goes
12. Steward and council decisions

## 1. Stateless: no state, tunables or runtime policy

The SDK has no chain, no disk, no clock and no configuration. A parameter
belongs only if it is consensus, network identity or wire format.

- #100, on `prune_after_height`, `min_blocks_to_keep`,
  `assumed_blockchain_size_gb`, `default_consistency_checks`,
  `is_mockable_chain`: "This is runtime policy specific to Dash Core, it makes
  no sense in a Base SDK context." "Base SDK is stateless", "we don't have
  runtime consistency checks because we don't have a state", "there is no live
  chain to mock", "we have no state to prune".
- #100, on the stack behind it: "worrying in how many stateful elements and
  tuning parameters are being introduced far outside the SDK's scope".
- #104 (ChainSetup, devnet tables, per-release params; closed): "The premise
  of this PR is contentious at best and a complete reshaping of the SDK's
  purpose at worst. Most of this PR adds stateful functions that are better
  positioned for rust-dashcore." "Devnets are created on the spot and are
  entirely built on tunables, they are far outside of scope of a stateless
  SDK."
- #104, on difficulty tunables: "Tunables for the difficulty retargeting algo
  are not stateless ... those are policy decisions over consensus, not
  baseline consensus rules."
- #105 (chain-params options; closed): "The whole premise of having a builder
  doesn't fit the SDK."

Instead: mainnet, testnet and regtest as fixed parameter sets. Devnets,
option handling, pruning, sizing hints and anything a node operator can set
live in rust-dashcore.

## 2. Codec only: no transport state, BIP324 only

`AGENTS.md`: "No networking code in any crate. The SDK provides encoding,
decoding, and data types only."

- V1 transport is out, twice. #67: "Do not evaluate v1 transport conditions,
  `p2p_core` will only ever support BIP324 (v2 transport)." #119: "we do not
  support v1 transport ... Dash's consensus guarantees depend on interactive
  proofs over the P2P network, so unlike Bitcoin, we have far greater
  incentive to move away from an opportunistic to a mandatory model. And that
  means explicitly omitting P2Pv1 from greenfield projects, including here."
- The codec has no per-peer or version-aware receive path. Where a limit
  depends on the negotiated version, decode bounds by the largest value any
  version allows and export the per-version limit for the peer layer. This
  is the design we proposed on #67 (`Headers2::max_count`) and he merged. It
  is not a quote of his.

Instead: handler policy, per-peer context, protocol-version negotiation and
anything like `ProtoCtx` or `decode_with_policy` stay in the node.

## 3. Byte bags and operative types; the scheme is a type

`dash-pkc` has two kinds of type. Byte bags (`BlsPkBytes`, `BlsSigBytes`)
carry bytes and can be parsed with no crypto dependency. Operative types
(`BlsPublicKey<S>`) do arithmetic, and `S` is the scheme, fixed at compile
time. Nothing converts one scheme's operative value into another's. Reading
a byte bag into an operative type of a named scheme is the sanctioned path
(`TryFrom<BlsPkBytes> for BlsPublicKey<S>`).

- #123 (a scheme picked at run time, and wrappers that carry it; closed by
  him): "This PR
  effectively undoes the whole thesis of `dash-pkc`, it introduces state
  (runtime-dependent behaviour), gets rid of the boundary between the two
  schemes (byte bags versus operative types) by essentially allowing
  'casting' between schemes at the operative level. Absolutely not."
- His own #61 moved the other way. Its title: "drop scheme parameters from
  BLS byte bags".
- #120: "we deliberately distinguish between legacy and basic scheme as
  having distinct encoding and distinct operations".
- Lazy evaluation of bytes is not the problem. #120: "We already do
  lazy-evaluation of bytes and allow encoding transforms, work on that was
  even approved (see base-sdk#101)". What is refused is a value whose
  behaviour depends on a scheme chosen at run time, or that lets one scheme's
  operative value stand in for the other's.

Instead: a caller that learns the scheme at run time (from a ProTx version,
say) branches in its own code and calls the typed read for that scheme. A
value that remembers a run-time scheme is a node-side type built on the byte
bag.

This is the ruling we broke most expensively. Reviewers must not ask for
conversions from one scheme's operative type to the other's.

## 4. Consensus-level choices belong to the caller

- #120 (BLS-IES keyed from a chosen encoding): "the decision to hybridise
  legacy keys under basic encoding for combined basic-schemed BLS-IES is a
  consensus-level decision, not something that rests here." "You can expose
  APIs to permit such constructions but you cannot do the construction here."
- Same PR: "Drop the original as-self-scheme functions, so the library's
  position is that it will not assume that participants all use the same
  scheme and requires it to be specified by the caller."
- Same PR: "Drop references to a default route, the default contract right
  next to an override is a potential footgun."

Instead: one explicit form where the caller names the choice (`_as::<T>`). No
default beside it. Test both directions.

## 5. Crate boundaries

- Crypto validity is `dash-pkc`'s. #88, on an operator-key check with
  off-curve and off-subgroup cases in `dash-primitives`: "this looks like
  cryptographic policy being smuggled into consensus code ... This is
  `dash-pkc` territory." He had the change split off until `dash-pkc` could
  represent the cases (#101), and it came back as #129.
- #129, when those tests reappeared in primitives: "`dash-primitives` isn't
  the place for bespoke cryptographic checks, especially since it's expressed
  through whatever `dash-pkc` exposes in its public API."
- #121: a high-S test "is better suited as a test in `dash_pkc::ecdsa` ...
  testing that the library can tell what a high-S signature is a better proof
  than testing that every transaction's high-S check does what it says".
- #114: range tests in primitives were "effectively duplicating 'what is a
  non-routable address' tests done in `types::AddrV2`".
- Generic codec helpers go to `dash-types`: `encoded_size` (#73), `impl_vec!`
  (#119, "This should be in `dash-types`, the same mechanism can be used in
  `dash-primitives`"), the crate-wide `Sealed` (#86).
- `dash-params` depends on nothing above it, and holds facts fixed at genesis
  or by a hard fork.

Test a property once, in the crate that owns it. Consumers test only their
own mapping onto it.

## 6. Conformance means the same faults

- Not the same order. #109 (closed): "we have to ensure that we detect the
  same faults as the reference impl, there is no guarantee, implicit or
  explicit that it will always be in the same order ... we cannot contort our
  implementation architecture (`Checkable` delegates to other `Checkable`s for
  inner types, heavy type system emphasis for propagated correctness checks)
  to match something brittle (order of checks)."
- Not its debugging allowances. #110, on local addresses that regtest
  permits: "Refuse it on every network, the regtest exemption should be
  treated as an allowance made to aid debugging in the reference
  implementation, not something an embedded program is expected to mirror,
  downstream consumers can react to the rejection done by the SDK and opt to
  ignore it."
- Unknown versions round-trip and fail validation. #87: "unsupported versions
  are considered invalid constructions in Dash Core, we try to preserve round
  trips if we don't recognise something but it has to be treated as invalid
  for all validation purposes, blob of bytes treatment is just there to avoid
  a potential outdated base SDK crate from trying to force a future version's
  payload through the existing struct."
- Decode what the wire permits, refuse in `Checkable`. #110: "we cannot refuse
  it at the serialization level but must make sure `Checkable` sees it as an
  invalid construction."
- serde and CBOR are first class. #110: "serde/ciborium is considered a
  first-class serialisation method so round-trippability matters. The few
  cases we've had to break round tripping fidelity was due to it having
  consensus-splitting consequences."
- The SDK may bound more tightly than the reference implementation where the
  reference is unbounded (his #71 bounds IES recipients).
- Bounded reads are the default. On #57 he inverted our API so that `decode`
  is the range-checked read and `decode_unbounded` is the named opt-out.
- The codec is not where validity lives. His #24: "it is presumed that we
  will always emit valid data while decodable assumes hostile byte input, so
  constraining must be done either at the type level (i.e. a bounded vector)
  or checks (`Checkable`) or inherent functions that perform these checks,
  they will not be done in the codec"

## 7. Types carry meaning

- Newtypes say who or what. #88, on a shared `CompactSig`: "Purpose of
  defining signatures separately is to encode who or what the signature is
  about, `CompactSig` undoes that." Share the implementation in one array
  type and wrap it in a newtype per role.
- Versions are enums. #88: `CbCommitmentVersion` as "an enum backed by `u16`,
  see `make_num!`, same idea as `ProTxVersion`", with an `Unknown` arm so any
  value decodes and the check refuses it.
- A field that recurs with its own rule becomes a struct with an inherent
  check. #129: wrap the operator key as was done for signatures, "make
  version-based `is_valid` checks an inherent function".
- Use the trait system. #121: a sign hash becomes a type with `Signable`.
  "Avoid parallel methods that skip the codec trait system outright (or
  worse, use them partially, leading to inconsistent usage patterns)."
- Amounts are `bitcoin_units::SignedAmount`, not `i64` (#88).
- The accepted version of a payload is an associated `CURRENT_VERSION`, not a
  module constant (#88).

## 8. One mechanism, extended

- Do not add a helper for a corner case. #86, on `opt_str_u64`: "don't want
  this encourage serde helpers for corner case, would prefer if existing
  helpers are leveraged/extended."
- A limit lives where it is enforced. #119, on a `limits.rs` of constants:
  "Anti-pattern, place the limit where the limit is exercised ... leaving
  unexercised constants means it's best left out of this PR or (and this is
  what I'd prefer), we start using them now and enforce them using the
  `dash_types`-based macros that support bounded-operations."
- No API ahead of its consumer. His #92: "preemptive creation of new API
  surface without guaranteed downstream consumers is suboptimal."
- A PR does what its title says. His #71 and #92, declining wider changes:
  "Not within the scope of this pull request".
- Macros before hand-written codecs. `dash_types::codec::take` "is discouraged
  as a low-level operation unless you have an overwhelming justification"
  (#67).
- Derived counts are computed, not tracked by hand. #67: "Calculate this off
  the table count."
- Sizes come from `size_of` or the codec, not summed literals (#88).
- Modules split by subsystem, not by kind of message. #74: "Split on a
  subsystem axis rather than a type axis" (`coinjoin.rs`, `quorum_sigs.rs`,
  `blocks.rs`, not `control.rs`).

## 9. The Bitcoin-inherited parts follow rust-bitcoin

- #122, on BIP37 and BIP157 messages: keep "our impl as close to
  `bitcoin-p2p-messages`" as possible, and choose between deferring for that
  crate or "aligning with upstream semantics and TODO'ing a substitution".
- BIP324 tests may use `rust-bitcoin/bip324` (#67).
- rust-bitcoin crates come from crates.io releases and must not desync (#39,
  #127).

Before typing a message Bitcoin also has, read how rust-bitcoin types it.

## 10. What counts as evidence

A claim that the SDK matches the reference implementation is an assertion of
consensus conformance. The evidence has to stand on something other than our
own code.

- The anchor is someone else's implementation. #101, on a Python
  reimplementation used to generate vectors: "Reference code cannot include
  your own parallel implementation, it has to be someone else's implementation
  as an anchor." And on driving relic directly: "reimplementation, even with
  the correct library backing it, puts us in the same place as the Python
  impl." Generator programs link the pinned reference implementation's own
  library. Patching or forward-declaring a private function is allowed.
- Transactions and blocks are real. #88: "We don't allow synthetic corpora
  for transactions and blocks, please fetch real transactions, from mainnet or
  testnet." A regtest block hash is not a citation: "Cannot be reproduced
  without test seed". Where a feature is not live on any public network,
  regtest vectors may sit inline in the test with a `TODO(pasta)` to replace
  them once mainnet has them.
- Chain facts come from established RPCs. #84 and #104: a Python script over
  `getblockheader`, `getdeploymentinfo`, `quorum list`, not "a dump script
  that needs to be injected in a live client". #107: "We are validating chain
  facts, which is the more constraining factor than it coming from the
  reference implementation."
- No snapshot per release. #104: "Most material facts are defined at genesis
  or after a hard fork, so checkpointing various releases doesn't give us
  greater insight than the dump from the most latest release."
- No benchmark without a comparator. #86: "Why are we benchmarking this? Is
  there an equivalent benchmark in Dash Core or `rust-dashcore` to compare
  against?"
- Nothing cites our fork. #88: "No citing forks. Either it should be
  upstreamed in a prior commit or inlined within this commit."
- Baseline first. #101: land the method that regenerates the existing corpora
  before the change that depends on new ones, "to establish baseline
  credibility".

## 11. Where rejected work goes

| Rejected here | Lives in |
|---|---|
| Devnets, chain setup, option handling, pruning and sizing parameters | rust-dashcore (devnets are already in `dash-spv`) |
| Run-time BLS scheme and the wrappers and values that carry it | rust-dashcore, built on `dash-pkc` byte bags and typed reads |
| Core-style sign, verify, aggregate and batch-verify front ends, DKG workers | rust-dashcore |
| Per-peer protocol context, handler policy, V1 framing | rust-dashcore's P2P layer |
| Check-order parity and reject-reason ordering | The node, if it needs them |
| Regtest and debugging exemptions | The consumer, which may ignore the SDK's refusal |

## 12. Steward and council decisions

These are not kwvg's rulings. They were made while he is away, each is dated,
and he may reverse any of them. Never quote one as his. An entry marked
"provisional" would loosen the skill and has no force until a unanimous
council confirms it; until then the stricter reading applies.

- 2026-11-13, steward. Section 3 says nothing converts one scheme's operative
  value into another's. That needs a qualifier: `develop` has an explicit,
  typed `to_scheme::<T>()` on `BlsPublicKey`, `BlsSignature`, `BlsSecretKey`
  and `BlsIesBlob`. Calling it is fine. What #123 refused is a scheme chosen
  at run time and a value that crosses schemes without the caller naming it.
- 2026-11-13, steward. The fork's V1 framing (`V1Header`, `V1FrameError`,
  `encode_v1`, `checksum`, `is_valid_v1`) is class D under section 2, not C.
- 2026-11-13, steward. A bound belongs in the codec when the reference
  enforces it while reading: a limited vector in a serializer, or at the read
  itself in the handler (`filterload` and `filteradd` on #122). A limit the
  reference checks after the read is the caller's. The SDK may still bound a
  count the reference leaves unbounded (#119), but the description must call
  it the SDK's bound and must not claim the reference reads it that way.
- 2026-11-16, council, unanimous (round 3; Opus 5.5, Fable 5.2, Muse
  Wonder full). `IsdLock`'s input bound (#128) is the reference's. Its
  constant and doc cite the reference. Below is the steward's correction
  that follows from it.
- 2026-11-16, steward, correcting the 2026-11-13 entry on read bounds. Its example was wrong:
  the `isdlock` input count on #128 is not unbounded in the reference. The
  value is the reference's (`InstantSendLock::MAX_INPUTS`, `lock.h`), and
  its handler refuses an oversized lock straight after reading it
  (`net_instantsend.cpp`), as with `filteradd`. So it is a bound at the read
  in the handler. The description cites the reference and does not call it
  the SDK's own. Before calling any bound the SDK's own, look for a check in
  the handler straight after the read, not only for later validity checks.
- 2026-11-14, council, unanimous (round 2; Fable 5.2, Opus 5.5, GPT 6.1
  Sol). Where a rust-bitcoin type refuses bytes the reference accepts (its
  closed `BloomFlags`, #122), the reference wins. Section 6 outranks
  section 9. The type is an open `enum_map!` enum with an `Unknown` arm and
  `impl_num!`, as `RevocationReason` is, with upstream's variant names and
  values. `Unknown` gets no `Checkable` fault when the reference treats no
  value as invalid. No masking accessor until a consumer needs one (#92).
- 2026-11-13, steward, provisional. Check-table rows that pin which error
  is reported first (`case::x_before_y`) are on `develop` in many modules,
  merged by kwvg (#88, #114). Whether new ones are wanted is undecided, and
  it is a question for him in the stewardship log. Until a council or he
  says otherwise, the strict reading of #109 applies: a PR adds no new row
  whose only purpose is to pin the order of two checks, and a reviewer flags
  one. Rows already on `develop` are left alone.
- 2026-11-13, steward. A dependency a crate gains only to compute something
  its own macros already do is refused in favour of the macros
  (`bitcoin_hashes` in `dash-p2p-core`, #128).
- 2026-11-14, council, unanimous (round 2; same members). `bitcoin-units`
  as a direct dependency of `dash-p2p-core`, for `start_height: BlockHeight`
  in the BIP157 requests (#122), is accepted. The ground is kwvg's own
  request: his #122 review links his earlier `compact_filters.rs` (228e54ce),
  which has the same field, codec lines and direct dependency, removed only
  when the messages were stubbed (ad44e5d1). The table's "consumer is
  blocked" test is not met on a strict reading, since `u32` reads the same
  bytes; this is a judgment call listed for him in the log. It covers this
  crate and this type only. Any other new dependency is still class C.
- 2026-11-16, steward. A class-C proposal whose own text says the consumer
  can carry the code is not sent to a council: no consumer is blocked. The
  BIP152 short-ID computation (`ShortIdKeys`, SipHash via `bitcoin_hashes`
  in `dash-p2p-core`) stays in the node and is a question for kwvg in the
  log. The #122 exception rested on his own earlier code; there was none here.
- 2026-11-13, open defect, listed for kwvg in the stewardship log.
  `Signable::verify` on `ProUpServTx` and `ProUpRevTx` takes the BLS scheme
  from the payload version. The reference verifies under the scheme active at
  the block, so legacy-encoded payloads mined after v19 are refused. Do not
  build on that rule, and do not change it without a class-C proposal.
  This is about operator signatures only. The operator key is a separate
  rule: the reference reads it under the payload version (`providertx.h`,
  the key's version wrapper), so a version-based `OperatorKey::is_valid`
  (#129, asked for by kwvg) is correct and does not rest on the defect
  (steward, 2026-11-14, after a reviewer read it as class D).

