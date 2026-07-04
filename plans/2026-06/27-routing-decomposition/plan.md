# Routing Module Decomposition

> **Status: COMPLETE (2026-06-28).** All six phases landed. `src/even/routing.py`
> is now a 12-module `routing/` package; `uv run pytest` = **69 passed**, `ruff
> check` clean repo-wide, and `even` JSON output is byte-identical to the
> monolith (proof in `test.md`). All four open points resolved. Changes are left
> **unstaged** for the maintainer (no git operations — WORKFLOW.md). Companion
> docs: `seam-map.md` (verified function→module map) and `test.md` (proof log).
> Remaining optional follow-up: tighten `tests/test_routing.py` to import from
> submodules instead of the facade (OP-001 — deliberately not done).

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
- `tests/test_routing.py` — `RoutingIndexOptions`, `index_routing`,
  `list_representatives`, **`build_global_representative_siglip`** (a 5th public
  name the original draft of this section missed), **plus 10 private helpers**:
  `_blend_tokens_per_sec`, `_entry_budget`, `_estimate_tokens`,
  `_fuse_representative_hits`, `_importance_prior`, `_kmeans_medoids`,
  `_parse_importance`, `_search_global_representatives_siglip`,
  `_select_budgeted_rows`, `_token_budget`.

So either the package `__init__` re-exports all of these (public + the tested
privates), or the test imports are repointed at submodules. **Resolved (OP-001):**
`__init__` re-exports all of them; the test file is unchanged.

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
| OP-001 | Preserve the tested-private import surface via `__init__` re-exports, or migrate `tests/test_routing.py` to import from submodules? | Resolved | Re-export the 5 public + 10 tested-private names from `__init__` (zero test churn). Tightening test imports to point at submodules is optional and was intentionally **not** done. See `seam-map.md`. |
| OP-002 | Final submodule seams and names. | Resolved | 12-module cut verified against the AST call-graph; see `seam-map.md` for the function→module map. The plan's first-draft `summaries.py` was ~1446 lines, so it is split into `summaries` / `media_summaries` / `summary_store` / `importance`. |
| OP-003 | Does the split expose import cycles? Where do shared helpers live? | Resolved | No cycle exists once `RoutingIndexOptions` / `SummaryGenerationError` move to `shared` and `_root_source_item_id` / `_coverage` / `_clean_routing_meta` are relocated. The feared summaries↔representatives cycle is not real: summary writers never read summaries back. Cross-cut helpers live in `routing/shared.py`. DFS cycle check: NONE. |
| OP-004 | Revisit OP-005 (build-orchestrator consolidation) during the split? | Resolved | Leave the three `build_*` orchestrators separate (as previously decided); they share the `representative_store` manifest/watermark layer but stay distinct functions. The new structural change is splitting representatives along the build/search consumer seam. |

## Verified Submodule Cut (OP-002 — see `seam-map.md` for full map)

Twelve modules, leaf → root. Every module is under the ~800 line target; largest
is `media_summaries` (783 lines as landed). Verified acyclic.

- `routing/shared.py` — module constants, `RoutingIndexOptions`,
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

## Implementation Phases (all complete — see `test.md` for per-phase proof)

1. ✅ **Design the seams (no code move).** Every function mapped via an AST
   call-graph; cycles and shared helpers identified; OP-001/002/003/004 settled.
   Recorded in `seam-map.md`.
2. ✅ **Stand up the package + facade.** `routing/__init__.py` re-exported the
   facade from a temporary `_core.py` (the relocated monolith).
3. ✅ **Move leaf modules first.** `shared`, `budget`, `importance`, `medoids`,
   `summary_store` relocated in topo order; suite green after each batch.
4. ✅ **Move the larger clusters.** `media_summaries`, `summaries`,
   `representative_store`, `representatives`, `representative_search`, `search`.
5. ✅ **Finalize the orchestrator + facade.** `index_routing` +
   `list_representatives` moved into `__init__`; `_core.py` deleted; re-exports
   repointed at submodules. Test-import tightening (OP-001) intentionally skipped.
6. ✅ **Contract-invariance check.** Before/after `even` JSON byte-identical on a
   fixture; no module over the size target.

### How it was executed (notes for a follow-up thread)

The move was script-driven (AST slicing) rather than hand-copied, to avoid
transcription error across ~3.6k lines. Extraction ran in strict topo
(leaf→root) order so each new submodule imported only from already-created
submodules + external packages — never from `_core` — which sidesteps circular
imports. `_core` back-imported moved names so its remaining code kept resolving
until it was emptied and deleted. Unused imports were trimmed with
`ruff check --fix --select F401,I` after each move. All module constants were
placed in `shared` (matching the plan's "cross-cut helpers + module constants"
intent); colocating them with owning modules is a possible future tidy-up.

## Dependencies And Risks (as encountered)

- Cycle risk: turned out the feared `summaries ↔ representatives` cycle does not
  exist (summary writers never read summaries back). The only real cycle came
  from `RoutingIndexOptions` / `SummaryGenerationError` living in `__init__`;
  moving them to `shared` plus relocating `_root_source_item_id` / `_coverage` /
  `_clean_routing_meta` produced a clean DAG (DFS check: NONE).
- The tested surface (5 public + 10 private) was the tripwire — the `__init__`
  facade re-exports protected it throughout; `tests/test_routing.py` never changed.
- Safety net held: `tests/test_routing.py` (~1k lines) plus the broadened suite
  (now **69 tests**) stayed green after every batch.

## Exit Criteria — all met

- ✅ `routing.py` is a package; no submodule over ~800 lines (largest:
  `media_summaries` = 783).
- ✅ `from even.routing import ...` unchanged for `cli.py`, `fts.py`, and the
  tests; `uv run pytest` = 69 passed; `ruff check` clean.
- ✅ `even` JSON/schema output byte-identical to the monolith (proven in `test.md`).
