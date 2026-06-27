# Test Proof — Engine Maturation Refactor

This packet is planning-only so far; no implementation has happened. Record
below is the review evidence that motivated the plan plus the proof obligations
each phase must satisfy.

## Review Evidence (2026-06-27)

Measured on the current tree:

- `routing.py` = 3,672 lines, 126 top-level `def`/`class` (`grep -cE`).
- Codebase = 11,789 lines across 19 modules; routing.py is ~31%.
- `sqlite3.connect(catalog_path())` call sites = 33 across 11 modules.
- `row_factory = sqlite3.Row` used once (routing.py:2430).
- `chunks.py:chunks_for_root` reads `row[14]` against a 15-column SELECT.
- PyYAML is a hard base dependency (`pyproject.toml`), yet
  `_load_*_fallback` parsers remain in `config.py` and `catalog.py`.
- Tests = 1,596 lines; `test_routing.py` = 1,039 of them.
- Representative families present for three backends (FTS/semantic/siglip):
  `_write_global_*_index`, `_*_manifest_current`, `_write_*_manifest`,
  `_search_global_representatives*`.

## Proof Obligations (to fill as phases land)

| Phase | Expected | Actual |
| --- | --- | --- |
| 0 Hermetic fixture | Suite green with `EVEN_CACHE`/`EVEN_HOME` exported | Done — was 12 failed; now `57 passed` with vars exported |
| 1 Catalog layer | Migrated modules use keyed row access; suite green after each | In progress — `chunks`/`fts`/`semantic`/`inventory` migrated; `57 passed`, ruff clean |
| 2 Dead fallbacks | Files smaller; `uv run pytest` + Ruff green; no install path regressed | — |
| 3 Representative dedupe | One abstraction; `index routing` output JSON unchanged on a fixture | — |
| 4 routing split | `from even.routing import ...` paths intact; suite green | — |
| 5 ollama consolidation | Summary generation unchanged on a fixture run | — |
| 6 Test broadening | New parse/inventory/semantic/helper tests pass | — |

## Contract-Invariance Check (required before closure)

Capture `even` JSON stdout for a representative command set (catalog status,
sources scan, index scope, index routing, search text/semantic/hybrid) on a
fixture before and after the refactor and diff them; they must match. Record
the commands and the diff result here.
