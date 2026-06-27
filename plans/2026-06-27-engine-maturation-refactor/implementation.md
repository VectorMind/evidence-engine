# Implementation Log — Engine Maturation Refactor

## Progress

`▰▰▰▱▱▱▱ Phase 1/6` — hermetic fixture done; catalog access layer landed and all
non-routing modules migrated (8 of 9). Only `routing.py`'s 9 sites remain, folded
into the Phase 4 decomposition. Next: Phase 2 (delete dead YAML fallbacks) or
Phase 3 (representative-store dedupe).

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

#### Second migration batch (committed `chunks`/`fts`/`semantic`/`inventory`)

- `media.py` — three `media inspect/describe/dedupe` write transactions + the
  `_media_items_for_root` read (4 sites). Kept `import sqlite3` (used by the
  `_inspect_*(conn: sqlite3.Connection, ...)` annotations); dropped unused
  `catalog_path`. Left the non-sqlite dict access untouched.
- `parse.py` — two document-write transactions + `_source_items_for_root` and
  `_document_state` reads (4 sites). Dropped unused `sqlite3`/`catalog_path`.
- `image_index.py` — asset-register write, `_image_assets_for_root`,
  `_image_registry_state`, `_current_image_stores`, `_upsert_image_registry`
  (5 sites). Bound `source_item_id` once to keep the `_stable_id` reuse readable.
  Dropped unused `sqlite3`/`catalog_path`.
- `catalog.py` — `create_catalog` DDL connect → `catalog_connection()`;
  `catalog_status_report` read-only connect → `catalog_connection(read_only=True)`
  with `row["name"]` keyed access. Kept `sqlite3` (Connection annotations +
  `sqlite3.Error`) and `catalog_path` (still used for path checks/mkdir/unlink).
- After this batch the only `sqlite3.connect(catalog_path())` sites left are in
  `db.py` (the helper) and `routing.py` (deferred to Phase 4).
- Proof: `uv run ruff check src/even/` clean; `uv run pytest -q` → `57 passed`.

## Proof

- `uv run ruff check src/even/ tests/` — all checks passed.
- `uv run pytest -q` — `57 passed` (env vars exported; hermetic via conftest).

## Follow-up risks

- The read-only path in `catalog.py:288` should adopt
  `catalog_connection(read_only=True)` when migrated, keeping the `mode=ro`
  guarantee.
- No public CLI/JSON/schema change in these steps; contract-invariance diff
  (test.md) still to be captured once the access-layer migration is complete.
