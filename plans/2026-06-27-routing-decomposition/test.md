# Test Proof — Routing Module Decomposition

This packet is in planning; no implementation has happened. Below are the
baseline facts and the proof obligations each phase must satisfy.

## Baseline (2026-06-27, at hand-off)

- `src/even/routing.py` = ~3.6k lines, ~120 top-level `def`/`class`.
- External importers of `even.routing`:
  - `cli.py`: `RoutingIndexOptions`, `index_routing`, `list_representatives`.
  - `fts.py`: `search_text_with_routing`.
  - `tests/test_routing.py`: those plus 10 private helpers
    (`_blend_tokens_per_sec`, `_entry_budget`, `_estimate_tokens`,
    `_fuse_representative_hits`, `_importance_prior`, `_kmeans_medoids`,
    `_parse_importance`, `_search_global_representatives_siglip`,
    `_select_budgeted_rows`, `_token_budget`).
- Suite at hand-off: `67 passed`, Ruff clean (after the maturation packet).

## Proof Obligations (fill as phases land)

| Phase | Expected | Actual |
| --- | --- | --- |
| 1 Seam design | Function→submodule map recorded; cycles/OP-001 resolved | **Done** — `seam-map.md` records the 12-module map; AST cycle check = NONE; OP-001 resolved (re-export 4 public + 10 tested-private from `__init__`). Baseline suite `69 passed`. |
| 2 Package + facade | `from even.routing import ...` resolves for all callers + tests; suite green | **Done** — `routing/` package with `__init__` re-exporting from a temporary `_core`. One extra facade name surfaced (`build_global_representative_siglip`, imported by the test) beyond the documented 14. Suite `69 passed`. |
| 3 Leaf modules moved | `medoids`/`budget`/`_shared` relocated; suite green | **Done** — `shared`, `budget`, `importance`, `medoids`, `summary_store` relocated in topo order; suite `69 passed`. |
| 4 Larger clusters moved | `summaries`/`representatives`/`search` relocated; suite green after each | **Done** — `media_summaries`, `summaries`, `representative_store`, `representatives`, `representative_search`, `search` relocated; suite `69 passed`. |
| 5 Orchestrator + facade | `index_routing` in `__init__`; re-export list final; suite green | **Done** — `index_routing` + `list_representatives` moved into `__init__`; `_core` deleted; facade re-exports point directly at submodules. Suite `69 passed`. Test-import tightening (OP-001) intentionally deferred. |
| 6 Size + contract | No submodule > ~800 lines; CLI/JSON diff identical on a fixture | **Done** — largest submodule `media_summaries` = 783 lines (all others smaller); `ruff check` clean repo-wide; before/after JSON byte-identical (see below). |

## Module sizes (final)

```
media_summaries 783   summaries 445   representatives 507   search 608
summary_store 322     representative_search 275   __init__ 281
shared 191   medoids 190   representative_store 159   budget 125   importance 88
```

All under the ~800 target.

## Contract-Invariance Check (done)

A harness reusing `tests/test_routing.py` helpers drove `index_routing`
(two roots, document + media), routed text search (`search_text_indexes`, which
calls `search_text_with_routing`) for two queries, and `list_representatives`,
dumping canonical JSON with volatile fields (timestamps, elapsed seconds)
redacted. The same harness was run against (a) the refactored working tree and
(b) a HEAD worktree holding the original monolith **plus the same unrelated
in-progress image-search changes**, both against an identical workspace path so
content-hash IDs line up.

Result: **byte-identical** output (`diff` exit 0). Both trees are also
self-consistent across repeated runs (0 diff), confirming the comparison is not
masking non-determinism.
