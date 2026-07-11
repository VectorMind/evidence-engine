# Review: Engine Improvements Packet

Date: 2026-07-10
Reviewer: Claude (read-only review of `handoff.md`, `plan.md`, `architecture.md`,
`test.md`; grounding checks against `src/even`)
Verdict: **Sound direction, approve with caveats.** The diagnosis is accurate,
the trust-first sequencing is right, and the plan improves on the handoff in at
least one important place. The caveats below should be resolved or explicitly
accepted before Milestone 0's spec promotion, because several of them touch
decisions that the immutability triggers make irreversible later.

## Grounding Verification

The plan's factual claims about the current implementation were spot-checked
and hold:

- one synthetic paragraph with a 500-character preview per document
  (`src/even/parse.py:634-647`, `_document_preview`);
- `catalog wipe` unlinks the single `catalog.sqlite` file
  (`src/even/catalog.py:117-123`);
- cross-island FTS hits are globally sorted by native score
  (`src/even/fts.py:232`);
- no `journal_mode` pragma is set anywhere in `src/even` (relevant to caveat 2).

The plan is grounded, not aspirational. `test.md` correctly refuses to count
planning checks as implementation proof.

## Where The Plan Improves On The Handoff

Worth recording: the handoff's suggested physical split (§3) placed source
revisions, activities, and evidence occurrences in the **wipeable**
`cache/evidence.sqlite`, with only entity/review rows durable. Under that
split, cache cleanup would destroy the very occurrences that accepted links
pin — the handoff's own P0 acceptance criterion would fail. `plan.md`
(Resolution Summary) caught this and moved the occurrence ledger into durable
state. That is the correct call and the deviation is properly documented as
intentional. However, it creates caveat 1.

## Major Caveats

### 1. "Small immutable evidence ledger" understates state growth

`plan.md` describes the durable ledger as "small" and says "unreviewed/current
working evidence remains rebuildable." But the target data contract puts
`evidence_occurrences` in `state.sqlite`, Milestone 2.3 writes an occurrence
(with **full normalized text**) for every parsed document and media object,
and Milestone 3 multiplies that by every typed object on every page. Ordinary
wipe preserves all of it. Consequences:

- unreviewed occurrences are not "rebuildable" in any practical sense — they
  are permanently retained, because wipe cannot touch them;
- every source edit forks a new revision plus a full set of new occurrences;
  every parser/profile/config change does the same; dedup only collapses
  byte-identical outcomes;
- `state.sqlite` — the store that is supposed to be the small, backupable,
  precious one — becomes the largest artifact in the system, and
  `backup-state` grows with corpus churn, not with reviewed meaning.

The mitigation offered ("add diagnostics before considering garbage
collection") defers the problem past the point where it is cheap. Options, in
order of preference:

1. Define the GC rule now, even if collection ships later: *an occurrence is
   collectible iff it is not referenced by any Layer-4 link and is not the
   current mapping of any logical object.* Add the collectible-row count to
   `catalog status` in Milestone 2, so growth is visible from day one.
2. Alternatively, copy-on-pin: occurrences live in the current catalog and are
   copied into state only when a link pins them. This keeps state genuinely
   small but weakens the search contract (exact refs returned by search would
   not survive a wipe unless pinned first) — probably not worth it, but the
   trade should be stated in the spec rather than left implicit.

At minimum, remove the word "small" and document the retention behavior
honestly in the spec.

### 2. Cross-database atomicity depends on journal mode — currently unspecified

The risk section relies on "explicit attached-database transactions" for
operations spanning both stores. SQLite makes a transaction across ATTACHed
database files atomic **only in rollback-journal mode; in WAL mode, commits
are atomic per file but not across files**. The code today sets no
`journal_mode` pragma, so it happens to be safe — but WAL is the obvious
future change for this exact architecture (a read-only web viewer plus a
writing CLI is the textbook WAL use case, and rollback mode will produce
reader/writer blocking that will invite that change). If WAL is enabled later
without revisiting this, the Milestone 1/2 consistency guarantees silently
break.

Required: the Milestone 0 spec must pin journal mode per store as a contract,
and state which cross-store operations rely on multi-database atomicity versus
the write-durable-first-then-retry-current pattern. The safer long-term
posture is to assume **no** cross-file atomicity (design every dual-store
write as durable-first plus retryable current mapping, as the risk section
already sketches) and treat attached-transaction atomicity as an optimization,
not a guarantee.

### 3. Migration pins "current at migration time," not "what was reviewed"

v10 never stored occurrences, so the migration step "resolve the v10 logical
ref, create the occurrence, pin it" necessarily pins whatever the content is
*now*. If a source changed between the original human review and the
migration, the migration manufactures a pinned occurrence the reviewer never
saw — precisely the drift this plan exists to prevent, laundered through the
migration itself. Additionally, the v10 row carries only the 500-character
preview; the full normalized text must come from the stored Docling artifact
in the wipeable cache, which may be absent or newer than the review.

This is not fixable — the historical information does not exist — but it must
be stated honestly rather than implied away:

- the spec and migration output should say that pre-migration drift is
  undetectable and that migration establishes the trust baseline *going
  forward*;
- pinned-at-migration links should carry a marker (e.g.
  `pinned_at_migration: true` in the audit attrs alongside the retained legacy
  ref) so audits can distinguish review-time pins from migration-time pins;
- where the source hash at migration differs from any hash recorded at
  review time (if recoverable from existing rows), the link should be flagged
  for re-review rather than pinned silently.

### 4. Milestone 2 pins become semantically stale at Milestone 3

Links pinned during Milestone 2 pin occurrences of the *synthetic
whole-document preview* object, because that is the only object shape that
exists until Milestone 3 lands. Milestone 3 then replaces the logical object
space with typed objects: the preview object ceases to exist as a current
object, so those links' `logical_ref`s stop resolving and their pinned
occurrences describe an object granularity the system no longer produces. The
exact refs still hydrate (correct), but the plan does not say:

- what `entity show` displays when the pinned occurrence's logical counterpart
  is gone (the "never substitute current content" rule covers missing
  occurrences, not orphaned logical refs);
- whether such links should be flagged for re-pin/re-review against typed
  objects.

Either sequence real-corpus pinning after Milestone 3, or add an explicit
"orphaned logical ref" state to the reference contract and integrity
diagnostics. The same applies to migrated v10 links, which will all be
document-preview-grained.

### 5. Deterministic occurrence IDs versus the activity reference need a precise derivation rule

Occurrence rows reference their generating `activity_id` (unique per run),
yet occurrence IDs must be deterministic so identical rebuilds dedupe. Two
consequences the spec must pin down before implementation:

- the ID derivation must **exclude** the activity instance and include exactly
  (source revision, producer, producer version, profile, config hash, producer
  object key, content hash) — if any implementer includes the activity ID,
  every rebuild forks history and the immutability triggers make it
  uncorrectable;
- on dedupe, the existing row keeps its original `activity_id` (first writer
  wins) — so "generating activity" means *first* generating activity, and the
  later activity's output is recorded only in the activity table. State this;
  otherwise the dedupe path looks like an update to an immutable row and will
  be "fixed" incorrectly.

## Moderate Caveats

### 6. RRF equalizes islands that are not equal

Reciprocal-rank fusion treats rank 1 in a 3-document island identically to
rank 1 in a 100k-document island, so tiny or noisy scopes get amplified. The
plan's tiny-versus-large benchmark (Milestone 5.4) is exactly the right test —
but be prepared for the outcome that plain RRF needs an island prior or a
minimum-native-score sanity floor, and leave room in the contract for that
(the locked decision OP-008 says "per-island ranks with RRF," which as worded
forbids score floors). Also audit downstream consumers: once `native_score`
is diagnostic-only, anything currently thresholding on score must be found and
converted, not just the final sort.

### 7. Low-budget routing risk and multi-scope queries

The budget ladder is sound and the exhaustive fallback plus separate
routing-recall metrics are the right safety net. One gap to close in the
evaluation fixtures: include queries whose relevant evidence deliberately
spans multiple scopes, since "L0 → best scope" (low budget) is structurally
unable to answer those and the widening rules are what is actually being
tested there.

### 8. `valuable_items` human-status migration rule is undefined

Milestone 4.1 migrates human review status "only when a real prior human
decision exists, otherwise map it to machine status" — but in v10 the two are
the same field, so there is no recorded way to tell them apart. Define the
rule now (e.g. any `accepted|rejected|deferred` value is presumed human and
migrated as a decision with `reviewer: unknown-pre-migration`, everything else
is machine), because this is another one-shot migration choice.

## Minor Points

- **Ref-prefix inconsistency:** `architecture.md` §3 shows the exact ref as
  `corpus_cache.evidence_occurrences.evo_a91`, but occurrences live in the
  `corpus_state` dataset per Milestone 0.2. Decide whether refs carry the
  dataset name (then this example is wrong) or are dataset-agnostic (then the
  reference grammar must say how legacy `corpus_cache.document_objects.*` refs
  and new refs are both parsed). Fix before the spec promotion.
- **Post-wipe state accumulation:** after an ordinary wipe and rescan,
  revisions/occurrences for sources that no longer exist on disk remain in
  state forever. Covered by the caveat-1 GC rule, but worth an explicit
  integrity diagnostic ("state rows with no current source").
- **Windows file locking:** wipe currently unlinks a file; with the web viewer
  holding read handles, unlink fails on Windows. Two database files double the
  exposure. Wipe should report *which* file is locked and by what category of
  holder, and the viewer should hold connections briefly rather than
  persistently.
- **Viewer during partial migration:** `src/web` must degrade gracefully when
  `state/state.sqlite` does not exist yet (un-migrated catalog) rather than
  erroring on attach.
- **Backup restore path:** Milestone 1.5 specifies backup but no documented
  restore procedure or test beyond "backup restore" in the test matrix; a
  backup command without a rehearsed restore is half a feature. Spell out the
  restore steps (and that restoring state against a mismatched current catalog
  is expected and safe, since cross-db refs are runtime-validated).
- **`review_tasks` reviewer defaults:** "usable local defaults for the current
  single-user CLI" — say what the default reviewer identity is (OS username?)
  so decision rows are consistent from the first migration onward.

## What Is Notably Good

- Failing-trust-test-first (Milestone 0.3) and baselines-before-behavior-change
  (Milestone 0.5 / OP-011) are the strongest process elements in the packet;
  hold those gates.
- Pin-at-write with no follow-current bindings (OP-003) is the correct
  resolution of the identity problem, and the exact/logical dual-ref contract
  is clean.
- The locked-decisions table, the abort-on-unresolvable-accepted-ref migration
  rule, and the explicit non-goals (no source byte retention, no ontology
  ownership) keep scope honest.
- The plan correctly refuses to let trace output count as recursive retrieval
  (OP-009) — that closes the most tempting shortcut.
- The dependency note that the `2026-07/04-webui-viewer` packet must consume
  this split-store contract prevents a second persistence interpretation.

## Requested Changes Before Milestone 0 Gate

1. Replace the "small ledger" claim; add the GC/collectibility rule and a
   state-growth diagnostic to Milestone 2 (caveat 1).
2. Pin journal-mode policy per store and restate which writes may rely on
   cross-file atomicity (caveat 2).
3. Document migration-time pinning honestly and add the
   `pinned_at_migration` audit marker (caveat 3).
4. Add the orphaned-logical-ref state and `entity show` behavior for
   preview-grained pins after Milestone 3 (caveat 4).
5. Specify the occurrence-ID derivation fields and first-writer-wins activity
   semantics (caveat 5).
6. Define the v10 human-versus-machine status migration rule (caveat 8) and
   fix the ref-prefix example (minor points).

None of these change the architecture's direction; they harden decisions the
plan already made.
