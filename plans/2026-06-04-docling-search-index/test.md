# Test: Docling Search Index

Date: 2026-06-04
Status: Planning proof only. No implementation to test yet.

## Proof So Far

- Read the existing plan packet:
  `plans/2026-06-04-docling-search-index/{survey.md,plan.md,implementation.md,test.md,deep-research-report.md}`.
- Read the upstream consumer handoff:
  `C:\dev\wassfila\documents-manager\plans\2026-06-05-personal-document-index\handoff.md`.
- Read the upstream workflow:
  `C:\dev\wassfila\documents-manager\WORKFLOW.md`.
- Read the upstream personal document index plan:
  `C:\dev\wassfila\documents-manager\plans\2026-06-05-personal-document-index\plan.md`.
- Listed repository files with `rg --files`; this workspace currently contains
  planning/specification scaffolding only and no Python package metadata.
- Checked `git status --short`; only `deep-research-report.md` was already
  untracked before this planning update.
- Added planning/specification files only; no runtime commands or dependency
  installation were run.
- Read the 2026-06-05 reference handoff:
  `C:\dev\wassfila\documents-manager\plans\2026-06-05-personal-document-index\handoff.md`.
- Reviewed `MicroWebStacks/content-structure` via GitHub and fetched its
  `catalog.yaml`, `src/blob_manager.js`, `src/structure_db.js`, and `cli.js`
  for the thresholded blob-storage analysis.
- Added root `catalog.yaml` for schema review.
- Rewrote `plans/2026-06-04-docling-search-index/plan.md` with OP-001 through
  OP-015, concrete `agents-docs` examples, root layout scope, Docling mapping,
  blob-storage analysis, embedding candidates, and new open points.
- Rewrote `specifications/corpus-cache-cli/spec.md` so the durable spec matches
  the updated decisions.
- Tried to parse `catalog.yaml` with default Python:
  `python -c "import yaml, pathlib; ..."`. This failed because PyYAML is not
  installed.
- Tried to parse `catalog.yaml` with bundled Codex Python at
  `C:\Users\wassi\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe`.
  This also failed because PyYAML is not installed.
- Tried to parse `catalog.yaml` with bundled Node using `require('yaml')`. This
  failed because the `yaml` package is not installed.
- Before the catalog review rewrite, ran structural checks with `rg` confirming
  the former schema shape contained `exposure_kinds`, `storage_profiles`,
  `database_exposures`, `document_objects`, `chunk_records`,
  `embedding_profiles`, `tantivy_indexes`, `lancedb_stores`, and
  `command_runs`.
- Ran structural checks with `rg` confirming `catalog.yaml` no longer contains
  nested `fields:`, malformed empty `values: }`, or accidental table entries
  formatted as column maps.
- Ran a read-only Python structural scanner confirming
  `old_style_column_entries=0` under `columns:` blocks.
- Tried to parse the updated `catalog.yaml` with Python `yaml`; this could not
  run because PyYAML is not installed in the active Python environment.
- Ran cross-file checks with `rg` confirming the plan/spec mention
  `agents-docs`, stdlib `sqlite3`, no SQL data-access wrapper, `one_per_folder`,
  and the new open points.
- Ran ASCII/no-tab checks with Python. `catalog.yaml`,
  `plans/2026-06-04-docling-search-index/plan.md`, and
  `specifications/corpus-cache-cli/spec.md` are ASCII-only; `catalog.yaml` has
  no tab characters.
- Updated catalog review split and added `config/exposures.yaml`,
  `config/embeddings.yaml`, and `store_templates.yaml`.
- Removed catalog tables for migration history, database exposure registry,
  document versions, catalog chunks, chunk/object links, embedding profiles,
  lower-index row internals, index jobs, command runs, and command messages.
- Reintroduced lean catalog registry tables for `tantivy_indexes` and
  `lancedb_stores`; lower-index row templates remain in `store_templates.yaml`.
- Ran `rg` against `catalog.yaml` for removed table names and stale catalog
  fields. After the registry clarification, `tantivy_indexes` and
  `lancedb_stores` are expected matches; removed migration, command, chunk,
  document-version, embedding-profile, and row-template tables remain absent.
- Ran a read-only Python structural scanner confirming
  `old_style_column_entries=0` for both `catalog.yaml` and
  `store_templates.yaml`.
- Ran ASCII/no-tab checks on `catalog.yaml`, `config/exposures.yaml`,
  `config/embeddings.yaml`, `store_templates.yaml`,
  `specifications/corpus-cache-cli/spec.md`, and
  `plans/2026-06-04-docling-search-index/plan.md`; all are ASCII-only and have
  no tab characters.
- Added `config/parser.yaml` and updated the spec/plan so the cache root is
  fixed at `$HOME/.cache/agents-docs/`, no CLI command accepts a cache-root
  argument, and no `init` command exists.
- Ran `rg` for stale CLI surface wording including `catalog init`,
  `--cache-root`, `<cache_root>`, `inventory scan-folder`,
  `parse docling-folder`, `index fts`, `index semantic`, and
  `initialization`; no matches were found in the active spec/plan/config files.
- Ran ASCII/no-tab checks on the updated schema, config, spec, plan,
  implementation, and test files; all checked files are ASCII-only and have no
  tab characters.
- Ran the column-format scanner again; `catalog.yaml` and
  `store_templates.yaml` both report `old_style_column_entries=0`.
- Parsed `pyproject.toml` with Python `tomllib`; result: `pyproject parsed`.
- Ran `python -m py_compile` on `src/agents_cli/__init__.py`,
  `src/agents_cli/paths.py`, and `src/agents_cli/cli.py`; result: success.
- Ran `$env:PYTHONPATH='src'; python -m agents_cli.cli --help`; result:
  top-level help lists `catalog`, `health`, `scan`, `parse`, `index`, and
  `search`.
- Ran `$env:PYTHONPATH='src'; python -m agents_cli.cli catalog status`;
  result: JSON reports fixed cache root
  `C:\Users\wassi\.cache\agents-docs`, fixed catalog path, and
  `status: missing`.
- Ran `$env:PYTHONPATH='src'; python -m agents_cli.cli health`; result: JSON
  reports fixed paths and stdlib SQLite check as `ok`.
- Removed generated `src/agents_cli/__pycache__` after syntax checks.
- Rechecked for `__pycache__` directories; none remain.
- Ran `rg` over README, spec, plan, and CLI code for stale command surface
  strings such as `--cache-root`, `catalog init`, `inventory scan-folder`,
  `parse docling-folder`, `index fts`, `index semantic`, and `<cache_root>`;
  no matches were found.
- Added `docs/dependencies.md` and linked it from `README.md`.
- Ran a dependency-doc coverage check against `pyproject.toml`; every declared
  Python dependency appears in `docs/dependencies.md`.
- Ran ASCII/no-tab checks on `README.md`, `docs/dependencies.md`,
  `implementation.md`, and `test.md`; all checked files are ASCII-only and have
  no tab characters.
- Ran `python -m py_compile` on `src/agents_cli/__init__.py`,
  `src/agents_cli/paths.py`, `src/agents_cli/contracts.py`,
  `src/agents_cli/catalog.py`, and `src/agents_cli/cli.py`; result: success.
- Ran `$env:PYTHONPATH='src'; python -m agents_cli.cli catalog status` before
  migration; result: JSON reported the fixed catalog as missing and listed ten
  expected missing tables.
- Ran `$env:PYTHONPATH='src'; python -m agents_cli.cli catalog migrate`; result:
  created `$HOME/.cache/agents-docs/catalog/catalog.sqlite`, set
  `sqlite_user_version` to `2`, and created ten catalog tables.
- Ran `$env:PYTHONPATH='src'; python -m agents_cli.cli catalog status` after
  migration; result: `status: current`, `missing_tables: []`,
  `extra_tables: []`, `table_count: 10`, and zero row counts for all expected
  tables.
- Ran `$env:PYTHONPATH='src'; python -m agents_cli.cli health` after migration;
  result: fixed cache and catalog paths exist, stdlib SQLite check is `ok`.
- Tried a direct read-only SQLite schema inspection command once with bad
  PowerShell quoting; it failed with a Python `SyntaxError`.
- Reran the read-only SQLite schema inspection with parameterized SQL; result:
  `user_version 2`, ten expected tables, and expected primary/secondary indexes.
- Reran `$env:PYTHONPATH='src'; python -m agents_cli.cli catalog migrate`;
  result: idempotent output with `created: false`, `status: current`, and
  `sqlite_user_version_before: 2`.
- Reran stale command-surface scan over README, spec, plan, and CLI code for
  `--cache-root`, `catalog init`, old command names, and `<cache_root>`; no
  matches were found.
- Ran ASCII/no-tab checks on updated README, Python files, implementation notes,
  and test notes; all checked files are ASCII-only and have no tab characters.
- Removed generated `src/agents_cli/__pycache__` after verification.
- Added explicit `catalog create` while keeping `catalog migrate` and
  `catalog status`.
- Ran `$env:PYTHONPATH='src'; python -m agents_cli.cli catalog create`;
  result against the existing fixed catalog: `status: current`,
  `created: false`, `sqlite_user_version_before: 2`,
  `sqlite_user_version: 2`, and `table_count: 10`.
- Ran `$env:PYTHONPATH='src'; python -m agents_cli.cli catalog migrate`;
  result against the existing fixed catalog: `status: current`,
  `created: false`, `sqlite_user_version_before: 2`,
  `sqlite_user_version: 2`, and `table_count: 10`.
- Ran `$env:PYTHONPATH='src'; python -m agents_cli.cli catalog status`;
  result: `status: current`, `missing_tables: []`, `extra_tables: []`,
  `table_count: 10`, and zero row counts for all expected tables.
- Ran `python -m py_compile` on all current `src/agents_cli/*.py` files;
  result: success.
- Ran `$env:PYTHONPATH='src'; python -m agents_cli.cli catalog --help`;
  result: help lists `{create,migrate,status}` with no cache-root argument.
- Ran `rg` over README, spec, plan, and source for stale active CLI wording:
  `catalog init`, `--cache-root`, legacy `catalog migrate|status`, and
  "create or upgrade" migration wording. Matches were limited to historical
  test notes, not active contracts or code.
- Removed generated `src/agents_cli/__pycache__` after verification.
- Did not delete the fixed user catalog to retest the missing-create path; that
  path was already created in the prior migration proof, and the new
  non-destructive proof covers idempotent `catalog create` on an existing
  current catalog.

Runtime proof currently covers Phase 2 CLI scaffold commands and Phase 3
SQLite catalog migration/status. Docling, Tantivy, LanceDB, embedding, and
indexing behavior is not implemented yet.

## Future Proof Targets

- Convert at least one PDF or Markdown source through Docling.
- Persist Docling artifacts and SQLite catalog records for source items,
  current documents, objects, valuable items, blobs, and index scopes.
- Build or refresh Tantivy FTS indexes over generated chunks derived from
  catalog objects.
- Build or refresh scoped LanceDB vector stores over generated chunks derived
  from catalog objects.
- Query in FTS, vector, and hybrid modes.
- Show expected versus actual search hits for a small fixture corpus.
- Show that search results hydrate provenance through SQLite instead of relying
  on lower indexes as the catalog.
- Record index health, rebuild, refresh, and deletion commands.
- Prove the manager-repository contract with a synthetic source manifest and
  structured JSON/JSONL outputs under `.results/`.
- Prove no command exposes `--cache-root` and that producer commands create
  missing catalog tables through the centralized table-creation path.
