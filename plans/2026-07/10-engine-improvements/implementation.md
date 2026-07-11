# Implementation

## Progress

Milestone 0 (Contract, baseline, and failing trust proof) — done. Milestones
1-8 remain, gated on this milestone per `plan.md`'s own sequencing rule.

## Changes

- Updated `specifications/corpus-cache-cli/spec.md` ahead of runtime code, per
  the plan's ordering rule: rewrote the Workspace Storage, Catalog, Reference,
  and Entity contracts for the two-store/pin-at-write/append-only-review model,
  and added four new sections — Retention And Collectibility, Journal Mode And
  Cross-Store Write Contract, Migration Trust Contract, Orphaned Logical
  Reference Contract — mirroring `plan.md`'s Target Data Contract and
  Reference And Compatibility Contract. Each new/changed section states
  inline where behavior is still target-only versus already live, so the spec
  does not claim unimplemented behavior is current.
- Split `catalog.yaml`'s single `corpus_cache` dataset into two:
  `corpus_cache` (21 current/rebuildable tables) and `corpus_state` (the 7
  existing Layer-4 entity tables). Fixed the 6 intra-entity `ref:` strings
  that pointed at `corpus_cache.entities.entity_id` to `corpus_state.entities.
  entity_id` for contract correctness (no SQL behavior change — `catalog.py`'s
  `_parse_ref` already discards the dataset segment when building `REFERENCES`
  clauses).
- `src/even/catalog.py`: `load_catalog_tables()` now takes an explicit
  `dataset: str` argument (raises `ValueError` on an unknown name) instead of
  hardcoding `datasets[0]`. Added `load_all_catalog_tables()` — the merge of
  both datasets — and switched `create_catalog()`/`catalog_status_report()` to
  it, since the physical `state/state.sqlite` split is Milestone 1's job; for
  now both datasets are still created in and reported from the single
  existing `catalog.sqlite` file, so current runtime behavior is unchanged.
  Updated the three call sites in `references.py` and the test suite
  (`test_routing.py`, `test_config.py`, `test_catalog_schema.py`) to pass an
  explicit dataset.
- Added `tests/test_catalog_schema.py::test_entity_layer_tables_live_only_in_corpus_state_dataset`
  and `::test_load_catalog_tables_rejects_unknown_dataset` to lock in the
  dataset split.
- Added `tests/test_parse_evidence_drift.py` with the two Milestone 0
  regression tests:
  - `test_accepted_link_survives_reparse_to_changed_source` — proves an
    accepted `entity_evidence_links` row silently resolves to a reparsed
    source's new content today, because `document_objects.object_id`
    (`even.parse._stable_id("obj", doc_id, "paragraph", "0")`) is derived only
    from `doc_id`, never content, and reparse does `DELETE`+`INSERT` under the
    same `object_id`.
  - `test_ordinary_wipe_preserves_accepted_link_and_evidence` — proves
    `catalog wipe` destroys accepted Layer-4 rows today, because it
    unconditionally `unlink()`s the single `catalog.sqlite` file.
  - Both are marked `@pytest.mark.xfail(strict=True, ...)` citing the
    Milestone/OP that fixes them, so the suite stays green while the gap
    stays visible and cannot be silently forgotten (`strict=True` fails loudly
    if a future milestone's fix makes them pass without removing the marker).
- Added `evaluation/` with the Milestone 0 deterministic fixture/query/
  judgment format: a two-root, four-document text corpus
  (`evaluation/datasets/milestone0/root-{a,b}/`) with one deliberately
  cross-root query and one deliberately cross-root judgment set, a runner
  (`evaluation/runners/run_milestone0_baseline.py`) that seeds evidence via
  `even.parse._write_parsed_document` directly (bypassing Docling) and fakes
  semantic embeddings/summaries the same way `tests/test_routing.py` already
  does (bypassing fastembed model downloads and Ollama), and the committed
  pre-change baseline report `evaluation/reports/milestone0-baseline.json`.
  See `evaluation/README.md` for the format and determinism rationale.

## Verification

- `python -m pytest tests/test_parse_evidence_drift.py --runxfail -q` — both
  new tests fail with the exact predicted `AssertionError` (revision B content
  overwrote revision A; `show_entity` returns `not_found` after wipe) before
  the `xfail` marker was added; see `test.md` for the captured output.
- `python -m pytest tests/ -q -rxX`: full suite green, `2 xfailed` (the two
  new regression tests), no unexpected failures.
- `python -m ruff check src tests evaluation`: clean.
- `python evaluation/runners/run_milestone0_baseline.py` run twice; the two
  `evaluation/reports/milestone0-baseline.json` outputs are byte-identical
  (`diff` clean), confirming determinism.
- Manually confirmed `catalog create`/`catalog status` still report the same
  single-file, same-table-set behavior after the `catalog.yaml` split (all
  pre-existing catalog/entity/routing tests pass unchanged in shape).

## Follow-Up Risks

- `src/even/semantic.py`'s `_semantic_runtime_status()` calls
  `importlib.util.find_spec` without importing the `importlib.util` submodule
  itself; this only surfaces as `AttributeError` in a fresh process where
  nothing else has imported `importlib.util` yet (pytest runs are unaffected
  because some other import path pulls it in first). The evaluation runner
  works around it locally (`import importlib.util` at the top of the script).
  Worth a one-line fix in `semantic.py` in a later milestone; out of scope
  here since it isn't part of Milestone 0's task list.
- The evaluation fixture corpus is intentionally tiny (2 roots, 4 documents),
  so routed search mostly reports `route_status: fallback_all_scopes` in the
  baseline report — the router correctly recognizes a corpus this small as
  too weak/small to route confidently and falls back to exhaustive. That is
  expected, real signal for this fixture size, not a bug; a larger fixture
  would be needed to observe non-fallback routing behavior in a future
  milestone's baseline.
- Milestone 0 leaves the physical `state/state.sqlite` store, WAL pragmas,
  and all runtime behavior described in the new spec sections unimplemented
  by design — those are Milestones 1-4. The two `xfail`-marked regression
  tests are the tracked proof that this is still open.
