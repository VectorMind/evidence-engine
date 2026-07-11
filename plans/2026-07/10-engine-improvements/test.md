# Test Proof: Evidence Engine Trust, Structure, And Retrieval Improvements

Status: Planning review only; implementation proof not yet run.

## Planning Checks

Read-only inspection on 2026-07-10 confirmed the plan is grounded in the
current implementation:

```powershell
rg -n "source_revision|evidence_occurrence|document_objects|valuable_items|entity_evidence|review_decision|review_tasks|recursive|RRF|BM25|image_store" src tests specifications catalog.yaml
rg -n "object_id|doc_id|_stable_id|DELETE FROM|INSERT INTO|text_preview" src/even/parse.py
rg -n "def review_target|UPDATE|review_tasks" src/even/entities.py
```

Actual planning findings:

- catalog schema/user version is `0.10` / `10` and stale catalogs require wipe;
- `catalog wipe` deletes the one `catalog/catalog.sqlite` file;
- parse uses a stable `obj` ID, deletes current document objects, and inserts
  one synthetic paragraph whose indexed content is a 500-character preview;
- entity evidence links store current catalog refs and hydrate the live row;
- review updates one target status without an append-only decision model or
  linked task transition;
- high-budget recursive behavior currently reports lower summary nodes but
  does not use them to restrict another proof search;
- cross-index FTS results are pooled by native score;
- pure image search enumerates all current compatible image stores;
- hybrid and representative-route RRF already exist and should be reused;
- the prior entity-runtime proof establishes persistence of Layer-4 rows across
  same-source rebuilds, not semantic immutability after source-content change.

Architecture review coverage:

- all structural diagrams use fenced Mermaid syntax; no ASCII architecture
  diagrams remain in `plan.md` or `architecture.md`;
- `architecture.md` compares current and target topology;
- semantic layers are mapped separately from physical stores;
- exact occurrence and current logical identities are illustrated;
- evidence production, review transactions, recursive text retrieval, image
  routing, and v10 migration flows are diagrammed;
- impact tables cover stores, references, budgets, commands, components,
  invariants, unchanged boundaries, and decisions requiring maintainer review.

## Review Incorporation

`review.md` was accepted as a plan-hardening review. `plan.md` now explicitly
covers:

- occurrence retention, the collectibility predicate, and growth diagnostics;
- WAL per store with no reliance on cross-file transaction atomicity;
- honest migration-time trust markers and legacy re-review flags;
- orphaned logical refs across preview-to-typed normalization;
- exact occurrence-ID derivation and first-writer activity semantics;
- calibrated-RRF room, multi-scope evaluation, and score-consumer audits;
- deterministic v10 `valuable_items` review migration and reviewer defaults;
- dataset-prefixed refs, Windows lock reporting, partial-migration viewer
  behavior, and rehearsed state restore.

## Implementation Proof Required

Populate this file milestone by milestone with:

- exact commands and environment variables;
- migration fixtures and pre/post row counts/checksums;
- source-change and wipe/rebuild provenance proof;
- typed-object fixtures and expected/actual hierarchy/locators;
- transaction fault-injection results;
- ranking/routing/image evaluation reports;
- full Python, Ruff, and applicable web test results;
- dependency skips, machine/model profiles, and remaining gaps.

Do not mark the packet complete from the planning checks above.

## Milestone 0 Proof (2026-07-11)

Environment: Windows, `python` from the repo's active virtualenv
(`docling`, `tantivy`, `fastembed`, `lancedb` all importable — no dependency
skips were needed for this milestone's proof).

### Trust-gap regression, captured failing before the `xfail` marker was added

Command: `python -m pytest tests/test_parse_evidence_drift.py --runxfail -q`

```
FAILED tests/test_parse_evidence_drift.py::test_accepted_link_survives_reparse_to_changed_source
AssertionError: accepted link must keep resolving to the reviewed revision A content, not whatever the current reparse wrote
assert 'revision B content' == 'revision A content'

FAILED tests/test_parse_evidence_drift.py::test_ordinary_wipe_preserves_accepted_link_and_evidence
AssertionError: ordinary wipe must not delete durable entity/review rows
assert 'not_found' == 'ok'

2 failed in 2.20s
```

Both failures are for the exact predicted reason: `object_id` is
content-independent (`even.parse._stable_id("obj", doc_id, "paragraph",
"0")`), so a reparse silently swaps the content an accepted link resolves to;
and `wipe_catalog()` unconditionally deletes the single `catalog.sqlite` file,
including Layer-4 entity/review rows. This satisfies Milestone 0's gate:
"the semantic-drift test fails for the verified reason."

With the `xfail(strict=True)` markers in place (command:
`python -m pytest tests/test_parse_evidence_drift.py -q -rxX`):

```
XFAIL tests/test_parse_evidence_drift.py::test_accepted_link_survives_reparse_to_changed_source - Milestone 0 trust-gap proof: ...
XFAIL tests/test_parse_evidence_drift.py::test_ordinary_wipe_preserves_accepted_link_and_evidence - Milestone 0 trust-gap proof: ...
2 xfailed in 2.23s
```

### Full suite and lint

- `python -m pytest tests/ -q -rxX` → `94 passed, 2 xfailed, 50 warnings in
  40.24s`. No unexpected failures; the two xfails above are the only
  non-passing outcomes and are intentional Milestone 0 proof artifacts.
- `python -m ruff check src tests evaluation` → `All checks passed!`.

### `catalog.yaml` dataset split sanity

```
python -c "
import yaml
data = yaml.safe_load(open('catalog.yaml', encoding='utf-8'))
for d in data['datasets']:
    print(d['name'], len(d['tables']), [t['name'] for t in d['tables']])
"
```
→ `corpus_cache 21 [...]`, `corpus_state 7 ['entities', 'entity_aliases',
'entity_evidence_links', 'entity_classifications', 'entity_attributes',
'entity_relationships', 'review_tasks']`. `catalog create`/`catalog status`
behavior is unchanged (verified via the full `test_catalog_schema.py`,
`test_routing.py`, `test_config.py`, `test_entities.py` runs above), since
Milestone 0 intentionally still applies both datasets to the single existing
`catalog.sqlite` file.

### Evaluation baseline

Command: `python evaluation/runners/run_milestone0_baseline.py`, run twice
consecutively; `diff` between the two `evaluation/reports/
milestone0-baseline.json` outputs was empty — confirmed deterministic.

Report summary (4-document, 2-root fixture; full report committed at
`evaluation/reports/milestone0-baseline.json`): exhaustive, hybrid, and all
three routed budgets (`low`/`mid`/`high`) reach recall@5/recall@20/nDCG@10/
MRR of `1.0` on all four queries, including the two deliberately cross-root
queries (`q1_northwind_drifter_recovery`, `q4_reef_point_breach`). Routed
search reports `route_status: fallback_all_scopes` for most budget/query
combinations — expected for a fixture this small, since the router correctly
treats a 2-root/4-document corpus as too weak to route confidently and falls
back to exhaustive search rather than guessing; see `implementation.md`'s
Follow-Up Risks. This is the pre-change baseline future milestones must not
regress without documented justification.

### Gaps intentionally left open by Milestone 0

- No runtime behavior changed: `state/state.sqlite`, WAL pragmas, occurrence
  pinning, transactional review, and everything else in the newly-written
  spec sections remain unimplemented until Milestones 1-4. The two `xfail`
  tests are the tracked proof.
- The `importlib.util` latent bug in `src/even/semantic.py` (see
  `implementation.md`) was worked around in the evaluation runner, not fixed
  in production code — out of scope for this milestone's task list.
