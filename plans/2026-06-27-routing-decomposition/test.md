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
| 1 Seam design | Function→submodule map recorded; cycles/OP-001 resolved | — |
| 2 Package + facade | `from even.routing import ...` resolves for all callers + tests; suite green | — |
| 3 Leaf modules moved | `medoids`/`budget`/`_shared` relocated; suite green | — |
| 4 Larger clusters moved | `summaries`/`representatives`/`search` relocated; suite green after each | — |
| 5 Orchestrator + facade | `index_routing` in `__init__`; re-export list final; suite green | — |
| 6 Size + contract | No submodule > ~800 lines; CLI/JSON diff identical on a fixture | — |

## Contract-Invariance Check (required before closure)

Capture `even` JSON stdout for a representative command set (`index routing`,
`search text/semantic/hybrid`, `list-representatives`) on a fixture before and
after the split and diff them; they must match.
