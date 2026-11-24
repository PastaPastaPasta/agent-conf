---
name: capture-visual-evidence
description: Create trustworthy screenshots and before/after visual evidence for pull requests, UI changes, bug reports, reviews, release notes, and published documentation. Use whenever Claude or Codex must capture, compare, select, annotate, upload, link, or make claims from screenshots, recordings, rendered pages, dialogs, menus, tooltips, or other visible application states—especially when “before” and “after” must represent exact source revisions.
---

# Capture Visual Evidence

Treat every screenshot as evidence for a precise claim. A successful capture command
does not prove the image is correct, useful, or safe to publish.

`file-pr` ("UI proof") says when a PR needs captures and the minimum they must
cover. This skill covers how to make them.

## Establish the claim before capturing

Write a small evidence matrix before launching the application:

| Surface or behavior | Before revision/state | After revision/state | Shared fixture | Expected visible delta |
|---|---|---|---|---|

Inventory every user-visible change. Include overview states and focused states such
as rows, dialogs, menus, tooltips, empty/error states, and filtered results when they
materially explain the change.

Separate visible changes from compatibility guarantees. Do not fabricate a visual
difference for behavior intended to remain unchanged; identify the unchanged state
and cite automated or procedural verification instead.

## Resolve provenance exactly

For a pull request comparison:

1. Resolve the exact target/base commit from PR metadata or repository history.
2. Resolve the exact full PR head being reviewed.
3. Record both full commit hashes before capture.
4. Build and run each revision independently.

“Before” means the product without the PR: normally the exact base revision against
which the PR is evaluated. It does not mean an earlier commit from the PR branch.
Never use an intermediate implementation commit as “before” unless the requested
comparison is explicitly between two PR iterations, and label that fact prominently.

Do not infer provenance from a binary name, old build directory, screenshot filename,
or memory. Verify the source revision that produced each running binary.

If using a synthetic or specially constructed fixture, disclose it. A synthetic pair
must still run against the correct before and after revisions; a fixture cannot turn an
intermediate implementation into a valid pre-PR state.

## Control comparison variables

Use matching copies of the same deterministic data wherever possible. Keep constant:

- wallet, database, chain, seed data, account, and relevant transaction/object IDs;
- application configuration, feature flags, locale, timezone, theme, scale, and window size;
- selected page, search term, sort order, scroll position, and confirmation/state timing.

Record identifiers that let a reviewer verify like-for-like evidence. For transaction
screens, prefer the same exact transaction ID in both images. If a variable cannot be
held constant, disclose it next to the comparison and avoid claims that depend on it.

Prevent stale or shared runtime state from contaminating the pair. Use disposable
datadirs/profiles and separate settings when appropriate. Ensure the “after” run does
not reuse cached UI state produced by “before,” or vice versa.

## Capture useful evidence

Make the reviewer understand the change without reverse-engineering the screenshot.

- Capture enough context to identify the application, page, selected record, and state.
- Add a focused view when an overview makes the relevant text too small.
- Use comparable framing and dimensions for before/after pairs.
- Make exact IDs and changed fields readable, or provide them in the accompanying text.
- Show open menus, hover tooltips, validation messages, and filtered results while they
  are actually visible; do not describe a hidden state as though it were shown.
- Avoid unrelated windows, desktop clutter, notifications, cursor obstruction, stale
  overlays, debug artifacts, and misleading selections.
- Preserve full-resolution files. If an inline image is reduced, also provide a direct
  full-resolution link.
- Prefer a complete overview plus narrowly focused pairs over one cryptic crop.

Do not claim that one field is “the only change” merely because other differences are
not obvious. Make comparative claims only after checking all visible values and known
runtime variables.

## Inspect every final image

Open every final screenshot yourself at original resolution before publishing it. Use
an image-viewing or browser inspection tool; filenames, capture logs, OCR, dimensions,
and checksums are not substitutes for looking at the pixels.

For every image, verify:

- it came from the intended before or after revision;
- it shows the intended application, page, record, and UI state;
- visible transaction/object IDs, dates, amounts, labels, types, and counts are correct;
- the claimed difference is actually visible and the pair is meaningfully comparable;
- no critical content is clipped, obscured, too small, off-screen, or hidden by a popup;
- no secret, personal data, unrelated application, notification, or unsafe path is visible;
- the file is the final version that will be uploaded, not an earlier similarly named capture.

Inspect again after any crop, resize, annotation, recompression, file replacement, or
recapture. A prior inspection does not validate a later output file.

If an image is wrong, ambiguous, or unhelpful, stop and recapture it. Do not rationalize
the mismatch in prose or publish it with a confident caption.

## Choose the evidence host

For pasta's pull requests, publish screenshots, recordings, and their provenance
index to `PastaPastaPasta/dash-ui-artifacts`, with paths scoped to the source repository
and PR (for example, `dashwallet-ios/pr-1115/`). Link the PR to immutable artifact
commit URLs. Keep capture artifacts out of the product's commits.

Do not create evidence-only branches or upload capture artifacts in `dashpay/*` unless
the user explicitly requests that destination. Resolve the artifact repository
separately from the product checkout's `origin`; an existing upstream evidence branch
is not authorization or a hosting convention to copy.

If the user specifies another destination, use it. If the intended host is unavailable,
finish and preserve the evidence locally and report the publication blocker rather
than silently choosing another repository.

## Publish and verify the published artifact

1. Use unambiguous paths such as `comparison/before/...` and `comparison/after/...`.
2. Publish an index stating the exact revisions, shared fixture, exact identifiers, and
   what each pair demonstrates.
3. Pair images directly in the PR or document and label the columns “Before — exact
   base” and “After — full PR head” or equivalent.
4. Hash the local final files before upload when practical.
5. Fetch the public/raw URLs after publication and verify status, content type, size,
   and hashes against the local files.
6. Open the rendered publication page when tooling permits and confirm that images load,
   labels map to the correct files, and the layout remains understandable.
7. Replace or explicitly supersede previously published misleading artifacts and links;
   do not leave two competing “authoritative” comparisons without explanation.

Looking only at the local images is insufficient when the task includes publication.
Looking only at the rendered page is insufficient when it downscales or caches images.
Validate both the source files and the published result.

## Clean up capture machinery

Treat capture-only instrumentation, temporary code, disposable settings, and test data
as scaffolding. Remove them from product worktrees unless they are intentionally part of
the requested change. Stop capture processes, restore modified applications, and verify
the source worktree is clean before handoff.

Do not allow screenshot generation to silently change the implementation being reviewed.

## Correct bad evidence explicitly

When previously published evidence is wrong:

1. State exactly why it was invalid—for example, the “before” image came from an
   intermediate PR commit.
2. Replace it with a newly verified pair.
3. State the exact before and after revisions and shared identifiers.
4. Update the original PR body, comment, or documentation rather than only adding a new
   disconnected correction.
5. Verify the replacement at its published URL.

Do not preserve a false claim to avoid embarrassment. Provenance and reviewer clarity
take priority.

## Completion gate

Do not report screenshot work complete until all applicable statements are true:

- [ ] Every visible change has useful evidence, or is explicitly identified as non-visual.
- [ ] Before and after revision hashes are recorded and correct.
- [ ] The same relevant fixture and identifiers are used, or differences are disclosed.
- [ ] Every final image was opened and inspected at original resolution.
- [ ] Captions describe what is visibly demonstrated without overclaiming.
- [ ] Public URLs were fetched and the uploaded files verified.
- [ ] The rendered comparison was checked when possible.
- [ ] Misleading superseded evidence was replaced or clearly retired.
- [ ] Capture-only changes and processes were removed, and product worktrees are clean.

In the final handoff, summarize the exact provenance, inspection performed, publication
location, verification performed after upload, and any behavior covered by tests rather
than screenshots.
