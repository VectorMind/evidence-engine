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
| OP-001 | Preserve the tested-private import surface via `__init__` re-exports, or migrate `tests/test_routing.py` to import from submodules? | Resolved | Re-export the 4 public + 10 tested-private names from `__init__` (zero test churn). Tightening test imports deferred to Phase 5. See `seam-map.md`. |
| OP-002 | Final submodule seams and names. | Resolved | 12-module cut verified against the AST call-graph; see `seam-map.md` for the function→module map. The plan's first-draft `summaries.py` was ~1446 lines, so it is split into `summaries` / `media_summaries` / `summary_store` / `importance`. |
| OP-003 | Does the split expose import cycles? Where do shared helpers live? | Resolved | No cycle exists once `RoutingIndexOptions` / `SummaryGenerationError` move to `_shared` and `_root_source_item_id` / `_coverage` / `_clean_routing_meta` are relocated. The feared summaries↔representatives cycle is not real: summary writers never read summaries back. Cross-cut helpers live in `routing/_shared.py`. DFS cycle check: NONE. |
| OP-004 | Revisit OP-005 (build-orchestrator consolidation) during the split? | Resolved | Leave the three `build_*` orchestrators separate (as previously decided); they share the `representative_store` manifest/watermark layer but stay distinct functions. The new structural change is splitting representatives along the build/search consumer seam. |

## Verified Submodule Cut (OP-002 — see `seam-map.md` for full map)

Twelve modules, leaf → root. Every module is under the ~800 line target; largest
is `media_summaries` (~705 body lines). Verified acyclic.

- `routing/_shared.py` — module constants, `RoutingIndexOptions`,
  `SummaryGenerationError`, cross-cut helpers + config accessors.
- `routing/budget.py` — token estimate, calibration, build-budget reporting.
- `routing/importance.py` — importance prior/parse/learn subsystem.
- `routing/medoids.py` — k-means / medoid math and album clustering.
- `routing/summary_store.py` — summary-node read/write + row-budgeting layer.
- `routing/summaries.py` — root/document summary generation, prompts, LLM call.
- `routing/media_summaries.py` — media album + cluster summary generation.
- `routing/representative_store.py` — manifest/watermark/uri/medoid-row helpers
  shared by the build and search sides.
- `routing/representatives.py` — the three `build_*` orchestrators + writers.
- `routing/representative_search.py` — the three `_search_global_*` readers.
- `routing/search.py` — `search_text_with_routing`, RRF fusion, scope selection,
  recursive deepening, route traces.
- `routing/__init__.py` — `index_routing` + `list_representatives` orchestrators
  and the facade re-export block.

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
