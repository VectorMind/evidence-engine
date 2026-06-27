# Routing Module Decomposition

## Problem Summary

`src/even/routing.py` is a god module: ~3.6k lines and ~120 functions (about a
third of the codebase) carrying at least six responsibilities — the
`index_routing` orchestrator, root/media/cluster summary generation, three
representative-store backends, the routed-search engine, k-means/medoid math,
and a token-budget/calibration/importance subsystem. It is the file most likely
to be reused by private workspaces and the hardest to navigate.

This is **Finding 1** from the 2026-06-27 engine review, deferred out of the
`2026-06-27-engine-maturation-refactor` packet because splitting a 3.6k-line
module is a deliberate design task, not a mechanical cleanup. That packet
finished every other finding (catalog access layer, dead-fallback removal,
representative manifest dedupe, ollama consolidation, test broadening) and left
this one to be designed properly on its own.

## Resolution Summary

Convert `routing.py` into a `routing/` sub-package along responsibility seams,
behind a stable `__init__` facade that preserves every import path callers and
tests currently rely on. Move code in small, reviewable batches, keeping
`uv run pytest` green after each batch. No behavior change and no public
CLI/JSON/schema change — this is internal structure only.

## Facade Contract (must not break)

External importers of `even.routing` today:

- `cli.py` — `RoutingIndexOptions`, `index_routing`, `list_representatives`.
- `fts.py` — `search_text_with_routing`.
- `tests/test_routing.py` — the above **plus 10 private helpers**:
  `_blend_tokens_per_sec`, `_entry_budget`, `_estimate_tokens`,
  `_fuse_representative_hits`, `_importance_prior`, `_kmeans_medoids`,
  `_parse_importance`, `_search_global_representatives_siglip`,
  `_select_budgeted_rows`, `_token_budget`.

So either the package `__init__` re-exports all of these (public + the tested
privates), or the test imports are repointed at submodules. See OP-001.

## Goal And Objectives

Goal: make routing navigable and reusable without changing what it does.

Objectives:

- No module over ~800 lines; clear single-responsibility submodules.
- `from even.routing import ...` keeps working for `cli.py`, `fts.py`, and the
  test suite (or tests are migrated deliberately).
- Suite green and byte-identical CLI/JSON output throughout.

## Scope And Non-Goals

In scope:

- Splitting `routing.py` into `routing/` submodules + facade.
- Untangling any import cycles the split exposes.
- Optionally revisiting OP-005 from the prior packet (consolidating the three
  representative *build orchestrators*) if a clean seam emerges here.

Non-goals:

- No change to CLI surface, JSON/JSONL output, result-file layout, or
  `catalog.yaml` schema.
- No new features or algorithm changes.
- No git operations — maintainer owns staging and commits (WORKFLOW.md).

## Open Points

| ID | Question | Status | Resolution |
| --- | --- | --- | --- |
| OP-001 | Preserve the tested-private import surface via `__init__` re-exports, or migrate `tests/test_routing.py` to import from submodules? | Open | Lean: re-export from `__init__` first (zero test churn, proves the move is behavior-neutral); optionally tighten test imports afterward. |
| OP-002 | Final submodule seams and names (see proposed cut below). | Open | — |
| OP-003 | Does the split expose import cycles (e.g. summaries ↔ representatives via `_current_summary_rows` / `_select_budgeted_rows`)? Where do shared helpers (`_iso`, `_utc_now`, `_json_object`, watermark, config accessors) live? | Open | Candidate: a small `routing/_shared.py` (or `common.py`) for cross-cut helpers. |
| OP-004 | Revisit OP-005 (build-orchestrator consolidation) during the split, or leave the three builders separate as decided? | Open | — |

## Proposed Submodule Cut (first draft — OP-002)

Derived from the current function inventory; treat as a starting point, not
committed scope:

- `routing/__init__.py` — `index_routing` orchestrator + facade re-exports.
- `routing/summaries.py` — root/media/cluster summary upserts, prompts,
  sampling, `_current_summary_rows`, importance parse/learn.
- `routing/representatives.py` — the three backend build/write/search plus the
  already-unified `_manifest_current` / `_write_manifest` layer.
- `routing/search.py` — `search_text_with_routing`, RRF fusion, scope selection,
  recursive deepening, route traces.
- `routing/medoids.py` — k-means / medoid math and album clustering.
- `routing/budget.py` — token estimate, calibration, build-budget reporting.
- `routing/_shared.py` — cross-cut helpers + module constants (OP-003).

## Implementation Phases

1. **Design the seams (no code move).** Map every function to a target
   submodule; identify shared helpers and any cycles (OP-002/OP-003). Settle
   OP-001 (facade vs test migration). Record the agreed map before moving code.
2. **Stand up the package + facade.** Create `routing/` with `__init__.py`
   re-exporting the current public + tested-private names from a temporary
   single module, so imports keep resolving while code is relocated.
3. **Move leaf modules first.** Relocate the lowest-dependency clusters
   (`medoids`, `budget`, `_shared`) and rerun the suite.
4. **Move the larger clusters.** `summaries`, `representatives`, `search`,
   rerunning the suite after each.
5. **Finalize the orchestrator + facade.** Land `index_routing` in `__init__`;
   confirm the re-export list; optionally tighten test imports (OP-001).
6. **Contract-invariance check.** Diff `even` JSON output before/after on a
   fixture; confirm no module over the size target.

## Dependencies And Risks

- Large diff with high cycle risk: `summaries` and `representatives` share
  `_current_summary_rows` / `_select_budgeted_rows`; the import graph must stay
  acyclic (mitigated by `_shared.py` and moving leaves first).
- The tested-private surface (10 helpers) is the tripwire — Phase 2's facade
  re-exports protect it until OP-001 is settled.
- Safety net: `tests/test_routing.py` (~1k lines) plus the broadened suite
  (67 tests) must stay green after every batch.

## Exit Criteria

- `routing.py` is a package; no submodule over ~800 lines.
- `from even.routing import ...` unchanged for `cli.py`, `fts.py`, and tests (or
  tests migrated by decision); `uv run pytest` green; Ruff clean.
- `even` CLI/JSON/schema output byte-identical (proven in `test.md`).
