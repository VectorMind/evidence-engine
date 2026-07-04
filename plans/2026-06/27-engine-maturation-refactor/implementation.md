# Implementation Log — Engine Maturation Refactor

## Progress

`▰▰▰▰▰▰ Done` — Findings 2–5 and 7 closed: hermetic test fixture; catalog access
layer fully migrated (all 9 modules); dead YAML fallbacks removed (−358 LOC);
representative manifest layer unified (6 helpers → 2); ollama text-gen
consolidated; tests broadened (+10, 67 total). Finding 1 (`routing.py` file
split) handed off to its own packet:
[2026-06-27-routing-decomposition](../27-routing-decomposition/).

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

### Phase 2 — Delete dead YAML fallback parsers (Finding 5 / OP-002) — done

- Confirmed OP-002: PyYAML 6.0.3 is importable and is a hard base dependency
  (`pyproject.toml`), so the `except ModuleNotFoundError` fallback branches are
  unreachable in any supported install. The other `ModuleNotFoundError` sites in
  the tree guard optional deps (pillow/tantivy/docling), not yaml — left intact.
- `config.py`: lifted `import yaml` to module top; removed
  `_load_parser_config_fallback`, `_load_embedding_config_fallback`,
  `_load_routing_config_fallback`, and the fallback-only `_scalar`/`_list`/
  `_parse_value`/`re` helpers. 246 → 35 lines.
- `catalog.py`: lifted `import yaml` to top; removed the try/except and the
  `_load_catalog_tables_fallback`/`_parse_column_line`/`_split_inline_mapping`
  hand-rolled parser. Kept `re` (still used by `parse_reference`).
- Net −358 lines (9 insertions, 358 deletions across the two files).
- Round-trip sanity: real-YAML loaders return the same values the fallbacks
  hardcoded (routing `representative_top_k=12`, fastembed `dimension=384`,
  21 catalog tables, 15 parser defaults).

### Phase 3 — Representative-store dedupe (Finding 2) — manifest layer done

Reviewed all three families before refactoring. They split into three bands:

- **Manifest layer** (currency-check + write) — pure JSON/watermark logic, six
  near-identical functions. **Unified.**
- **Index-write bodies** — genuinely different engines (tantivy schema+documents
  vs lancedb embed+create vs lancedb reuse-vectors). **Kept separate by design.**
- **Search + build orchestrators** — different row sources
  (`_current_summary_rows` vs `_current_album_medoid_rows`), different
  store-exists predicates (`_tantivy_index_exists` vs `_lancedb_store_exists`),
  and different `counts` schemas (`summary_nodes_*` vs `media_representatives_*`).
  **Kept separate by design** — forcing them into one parameterized function
  would trade triplication for a conditional-heavy abstraction that reads worse.

Done:

- Replaced `_manifest_current` / `_semantic_manifest_current` /
  `_siglip_manifest_current` (3) with one `_manifest_current(path, watermark,
  template, *, fts_profile=None)`. Behavior preserved: all three validate
  watermark + template; only FTS additionally pins `fts_profile` (the vector
  backends never validated their profile field, so it stays opt-in).
- Replaced `_write_manifest` / `_write_semantic_manifest` /
  `_write_siglip_manifest` (3) with one `_write_manifest(path, *, template,
  profile_field, profile_value, watermark, row_count, extra=None)`. `extra`
  carries the backend's extra count (`overflow_count` for text, `album_count`
  for media). Manifest JSON key sets are identical to before (sorted output).
- Updated all 8 call sites (3 build writers, 5 currency checks).
- Net −40 LOC in `routing.py` (78 insertions, 118 deletions); 6 functions → 2.
- Verified across backends by `test_routing.py` (29 passed), which exercises
  FTS/semantic/siglip build, "unchanged"/currency, and search routes.

See OP-005 for the deferred build-orchestrator consolidation.

### Phase 1 completion — `routing.py` sqlite sites (Findings 3+4) — done

Migrated all 9 remaining `sqlite3.connect(catalog_path())` sites in `routing.py`
to `catalog_connection()` with keyed row access, without restructuring the file
(the Phase 4 split is parked):

- `_current_album_medoid_rows`, `list_representatives`, `_upsert_summary_row`
  (write), `_summary_state`, `_current_summary_rows` (17-column read),
  `_root_source_item_id`, `_media_assets_for_root`, `_delete_stale_media_clusters`,
  `_summary_region_rows`.
- `_media_assets_for_root` previously set `conn.row_factory = sqlite3.Row` by
  hand; dropped that line since the helper provides it. `dict(row)` unchanged.
- Added `from even.db import catalog_connection`; dropped the now-unused
  `catalog_path` import. Kept `sqlite3` (still used by `except sqlite3.Error`).
- Result: the only `sqlite3.connect` in the whole `src/even` tree is now inside
  `db.py`. Findings 3+4 fully closed.
- Proof: ruff clean; `uv run pytest -q` → `57 passed`.

### Phase 5 — Ollama text-gen consolidation — done

- Added policy-free `ollama.generate_text(prompt, *, model, url, timeout,
  options=None)` — the text-only sibling of `generate_from_image`. Builds the
  `/api/generate` POST, returns the stripped `response`, raises plain
  transport/parse errors. The image path is untouched (zero risk there).
- `routing._generate_summary_text` now delegates the HTTP to
  `ollama.generate_text`, keeping its domain policy in routing: localhost-only
  enforcement (renamed `_local_ollama_generate_url` → `_validated_local_base_url`,
  now returns the validated *base* since `generate_text` appends the path) and
  the `SummaryGenerationError` taxonomy (`ollama_unreachable` /
  `ollama_response_parse_failed`). Behavior preserved: same payload, endpoint,
  and error mapping.
- Dropped the now-unused `from urllib.request import Request, urlopen` in
  `routing.py` (`urlparse`/`HTTPError`/`URLError` still used).
- This path has no fake-injection in the suite, so it is now covered directly by
  `tests/test_ollama.py` (payload shape + response parsing via a fake urlopen).

### Phase 6 — Test broadening — done (focused on this packet's changes)

Added direct tests for the surfaces this packet introduced or changed, rather
than a broad sweep:

- `tests/test_db.py` — `catalog_connection`: keyed + positional row access,
  commit-on-clean-exit, rollback-on-error, and `read_only=True` blocking writes.
  Covers the keystone every migrated module now depends on.
- `tests/test_ollama.py` — `generate_text` payload/endpoint/timeout and the
  `options`-omitted case (covers Phase 5).
- `tests/test_config.py` — config/catalog loaders parse the real packaged YAML
  and resolve profiles by name (guards the Phase 2 fallback removal).
- +10 tests; suite now 67.

## Proof

- `uv run ruff check src/even/ tests/` — all checks passed.
- `uv run pytest -q` — `67 passed` (env vars exported; hermetic via conftest).

## Follow-up risks

- The read-only path in `catalog.py:288` should adopt
  `catalog_connection(read_only=True)` when migrated, keeping the `mode=ro`
  guarantee.
- No public CLI/JSON/schema change in these steps; contract-invariance diff
  (test.md) still to be captured once the access-layer migration is complete.
