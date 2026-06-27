# Implementation Log — Engine Maturation Refactor

## Progress

`▰▰▱▱▱▱▱ Phase 1/6` — hermetic test fixture done; catalog access layer landed
and four modules migrated; next is migrating the remaining sqlite call sites
(`media.py`, `parse.py`, `image_index.py`, `catalog.py`, `routing.py`).

## Log

### Phase 0 — Hermetic test fixture (Finding 7) — done

- Added `tests/conftest.py` with an autouse `clear_even_path_env` fixture that
  `monkeypatch.delenv`s `EVEN_CACHE`/`EVEN_HOME` for every test module.
- Removed the now-redundant file-scoped copy of that fixture from
  `tests/test_cli_contract.py`.
- Proof: full suite previously failed 12/57 when `EVEN_CACHE`/`EVEN_HOME` were
  exported in the shell (tests read the real `~/.even` catalog, e.g.
  `assert 23 == 1`). After the fixture, `57 passed` **with those vars still
  exported**.

### Phase 1 — Catalog access layer (Findings 3+4) — in progress

- Added `src/even/db.py`: `catalog_connection(*, read_only=False)` context
  manager. Sets `row_factory = sqlite3.Row` (column-name access), commits on
  clean exit, rolls back on exception, and always closes the connection (a bare
  `with sqlite3.connect(...)` only wraps a transaction and leaks the handle).
- Migrated call sites from `with sqlite3.connect(catalog_path())` to
  `with catalog_connection()` and converted positional `row[i]` to keyed access:
  - `chunks.py` — `chunks_for_root`, `media_chunks_for_root` (2 sites).
  - `fts.py` — `_fts_registry_state`, `_current_fts_indexes`,
    `_upsert_fts_registry` (3 sites). Dropped unused `sqlite3`/`catalog_path`
    imports.
  - `semantic.py` — `_semantic_registry_state`, `_current_semantic_stores`,
    `_upsert_semantic_registry` (3 sites). Left the LanceDB `row.get(...)` dict
    access untouched (not a sqlite row). Dropped unused imports.
  - `inventory.py` — the source-root/items upsert transaction (1 site). Left the
    stats dict `row["extension"]` access untouched (not a sqlite row). Dropped
    unused imports.
- `sqlite3.Row` keys are unique per query in every migrated SELECT (verified by
  reading each statement), so keyed access is unambiguous.

Remaining Phase 1 call sites (future steps): `media.py` (4), `parse.py` (4),
`image_index.py` (5), `routing.py` (9), `catalog.py` (2, including the
`mode=ro` read — candidate for `catalog_connection(read_only=True)`).

## Proof

- `uv run ruff check src/even/ tests/` — all checks passed.
- `uv run pytest -q` — `57 passed` (env vars exported; hermetic via conftest).

## Follow-up risks

- The read-only path in `catalog.py:288` should adopt
  `catalog_connection(read_only=True)` when migrated, keeping the `mode=ro`
  guarantee.
- No public CLI/JSON/schema change in these steps; contract-invariance diff
  (test.md) still to be captured once the access-layer migration is complete.
