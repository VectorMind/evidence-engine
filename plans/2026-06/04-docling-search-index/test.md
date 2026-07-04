# Test: Docling Search Index

Date: 2026-06-04
Status: Phase 4 Docling parse proof started.

## Proof So Far

- Read the existing plan packet:
  `plans/2026-06/04-docling-search-index/{survey.md,plan.md,implementation.md,test.md,deep-research-report.md}`.
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
- Rewrote `plans/2026-06/04-docling-search-index/plan.md` with OP-001 through
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
  `plans/2026-06/04-docling-search-index/plan.md`, and
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
  `plans/2026-06/04-docling-search-index/plan.md`; all are ASCII-only and have
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
- Updated `config/parser.yaml` from `one_per_folder` to `one_per_root`.
- Added public fixture files under `tests/fixtures/scan-basic/`.
- Ran `python -m py_compile` on all current `src/agents_cli/*.py` files;
  result: success.
- Ran `$env:PYTHONPATH='src'; python -m agents_cli.cli scan folder tests\fixtures\scan-basic`;
  result: `status: ok`, `store_policy: one_per_root`, two folders seen, two
  files matched, four catalog items created, and a `.results/` run folder
  written.
- Reran `$env:PYTHONPATH='src'; python -m agents_cli.cli scan folder tests\fixtures\scan-basic`;
  result: `status: ok`, zero items created, zero items changed, and four items
  unchanged.
- Ran `$env:PYTHONPATH='src'; python -m agents_cli.cli scan folder --help`;
  result: scan help lists `path`, `--max-files`, `--max-bytes`, and
  `--max-depth`; it does not expose cache-root configuration.
- Ran `$env:PYTHONPATH='src'; python -m agents_cli.cli catalog status` after
  the synthetic scan; result: `source_roots: 1`, `source_items: 4`, and
  `index_scopes: 1`.
- Checked fixed-cache `.results/` output with PowerShell; result: `result.json`
  files exist under `$HOME/.cache/agents-docs/.results/<date>/<run>/`.
- Ran `$env:PYTHONPATH='src'; python -m agents_cli.cli scan folder <user-provided scalable-capital root>`;
  result: `status: ok`, `store_policy: one_per_root`, four folders seen, 107
  files matched, 20 files skipped as unmatched, 34,139,128 bytes matched, 111
  catalog items created, and zero failures.
- Reran the same user-provided root scan; result: `status: ok`, zero items
  created, zero items changed, and 111 items unchanged.
- Ran `$env:PYTHONPATH='src'; python -m agents_cli.cli catalog status` after
  the user-provided root scan; result: `source_roots: 2`,
  `source_items: 115`, and `index_scopes: 2`.
- Ran `$env:PYTHONPATH='src'; python -m agents_cli.cli scan folder tests\fixtures\scan-basic --max-files 1`;
  result: exit code 1 with `status: deferred`, safeguard kind `max_files`,
  limit `1`, and `needed_at_least: 2`.
- Reran `python -m py_compile` on all current `src/agents_cli/*.py` files;
  result: success.
- Ran `rg` over active README, spec, config, source, plan, and implementation
  files for `one_per_folder`, `--cache-root`, `catalog init`, and old command
  names; result: no matches.
- Added mandatory Markdown summaries and optional HTML reports.
- Ran `python -m py_compile` on all current `src/agents_cli/*.py` files;
  result: success.
- Ran `$env:PYTHONPATH='src'; python -m agents_cli.cli scan folder tests\fixtures\scan-basic`;
  result: `status: ok` and payload includes
  `summary_uri: .results/<date>/<run>/summary.md`.
- Ran `$env:PYTHONPATH='src'; python -m agents_cli.cli scan folder tests\fixtures\scan-basic --report`;
  result: `status: ok`, payload includes `summary_uri`, and payload includes
  `report_uri: reports/<date>/<run>/report.html`.
- Read the generated `summary.md`; result: it contains a one-screen scan
  summary with two Markdown tables: overview and inventory changes.
- Checked the generated `report.html`; result: it contains a generic scan
  folder report with overview text, a table, and inventory signal bars.
- Ran `$env:PYTHONPATH='src'; python -m agents_cli.cli health`; result:
  `paths.results_root_exists: true` and `paths.reports_root_exists: true`.
- Added a plan-only inventory-statistics proposal. No runtime command was run
  for this proposal and no catalog migration was applied.
- Implemented the inventory-statistics patch.
- Ran `python -m py_compile` on all current `src/agents_cli/*.py` files;
  result: success.
- Ran `$env:PYTHONPATH='src'; python -m agents_cli.cli catalog migrate`;
  result: `status: migrated`, `sqlite_user_version_before: 2`,
  `sqlite_user_version: 3`, and `table_count: 12`.
- Reran `$env:PYTHONPATH='src'; python -m agents_cli.cli catalog status`;
  result: `status: current`, `missing_tables: []`, `extra_tables: []`,
  expected user version `3`, and expected tables now include
  `source_root_stats` and `source_extension_stats`.
- Ran `$env:PYTHONPATH='src'; python -m agents_cli.cli scan folder tests\fixtures\scan-basic --report`;
  result: `status: ok`, `schema_version: 0.3`, `result_uri` under `results/`,
  `summary_uri` under `results/`, `report_uri` under `reports/`, and
  `statistics.file_count: 2`, `statistics.total_size_bytes: 144`, with `.md`
  and `.txt` extension stats.
- Read the generated fixture `summary.md`; result: it includes total size,
  average file size, min/max file size, and top extension rows.
- Checked the generated fixture `report.html`; result: it includes
  "Extension Mix", "By File Count", "By Total Size", SVG chart markup, and
  `.md`/`.txt` extension labels.
- Ran `$env:PYTHONPATH='src'; python -m agents_cli.cli scan folder <user-provided scalable-capital root> --report`;
  result: `status: ok`, `statistics.file_count: 107`,
  `statistics.folder_count: 4`, `statistics.total_size_bytes: 34139128`,
  `statistics.min_file_size_bytes: 10`, and
  `statistics.max_file_size_bytes: 3164811`.
- The scalable-capital extension stats were `.pdf: 105 files / 34123402 bytes`,
  `.docx: 1 file / 15716 bytes`, and `.txt: 1 file / 10 bytes`.
- Read the scalable-capital `summary.md`; result: compact overview table plus
  top extension table.
- Checked the scalable-capital `report.html`; result: it includes extension
  pie charts by file count and by total size.
- Ran `$env:PYTHONPATH='src'; python -m agents_cli.cli catalog status` after
  both scans; result: `source_root_stats: 2`, `source_extension_stats: 5`,
  `source_items: 115`, and `table_count: 12`.
- Ran a read-only SQLite query against `source_root_stats` and
  `source_extension_stats`; result: both roots have materialized current stats,
  and scalable-capital stats match the scan output.
- Ran `$env:PYTHONPATH='src'; python -m agents_cli.cli scan folder tests\fixtures\scan-basic --max-files 1`;
  result: exit code 1 with `status: deferred`, a partial `statistics` object,
  and `result_uri` under `results/`. A later read-only stats query confirmed
  the fixture's current catalog stats still reflect the prior complete scan.
- Updated `config/parser.yaml` so omitted parse profiles default to
  `docling_ocr`, and canonical artifact outputs default to `docling_json`.
- Added `tests/fixtures/parse-basic/dummy.pdf` as a public PDF fixture.
- Ran `$env:PYTHONPATH='src'; python -m agents_cli.cli parse folder tests\fixtures\parse-basic --limit 1 --report`
  before Docling was installed in the active Python; result: `status: failed`,
  `error_kind: docling_missing`, `parser_profile: docling_ocr`, and
  `auto_scan_status: ok`, proving parse auto-runs scan/catalog prerequisites
  before failing on the missing runtime dependency.
- Ran `uv pip install -e ".[docling]"`; result: Docling and OCR dependencies
  installed successfully in `.venv` after two timeout attempts with
  `python -m pip install -e ".[docling]"`.
- Ran `uv run python -m agents_cli.cli parse folder tests\fixtures\parse-basic --profile docling_fast_text --limit 1`;
  result: `status: ok`, `parser_profile: docling_fast_text`,
  `ocr_requested: false`, `documents_planned: 1`, `documents_parsed: 1`,
  `documents_failed: 0`, `artifacts_written: 1`, and `objects_written: 1`.
- Ran `uv run python -m agents_cli.cli parse folder tests\fixtures\parse-basic --limit 1 --report`;
  result: `status: ok`, `parser_profile: docling_ocr`,
  `ocr_requested: true`, `documents_planned: 1`, `documents_parsed: 1`,
  `documents_failed: 0`, `artifacts_written: 1`, `objects_written: 1`,
  `summary_uri: results/2026-06-06/094130-4715251af6/summary.md`, and
  `report_uri: reports/2026-06-06/094130-4715251af6/report.html`.
- Ran a read-only catalog query after the successful default OCR parse; result:
  one `documents` row with profile `docling_ocr` and status `parsed`, one
  `docling_artifacts` row of type `docling_json`, one inline blob, and one
  preview `document_objects` row.
- Reran `uv run python -m agents_cli.cli parse folder tests\fixtures\parse-basic --limit 1`;
  result: `status: ok`, `documents_unchanged: 1`, `documents_parsed: 0`, and
  `documents_failed: 0`, proving profile-aware freshness for the default OCR
  path.
- Ran `uv run python -m agents_cli.cli catalog status` after parsing; result:
  `status: current`, `documents: 1`, `docling_artifacts: 1`,
  `artifact_blobs: 1`, and `document_objects: 1`.
- Observed first-run OCR model behavior on Windows: a parallel OCR/fast-text run
  returned one OCR `RuntimeError` while RapidOCR models were being downloaded,
  but the direct sequential OCR diagnostic and the later default OCR parse
  succeeded after models were present.
- Ran `python -m py_compile` on all current `src/agents_cli/*.py` files after
  the console/path contract change; result: success.
- Ran `$env:PYTHONPATH='src'; python -m agents_cli.cli scan folder tests\fixtures\scan-basic --report`;
  result: concise terminal output, not JSON. The output showed status `ok`,
  file/folder/size counts, change counts, and links to
  `results/2026.06/06/100602-scan-folder/result.json`,
  `results/2026.06/06/100602-scan-folder/summary.md`, and
  `reports/2026.06/06/100602-scan-folder/report.html`.
- Ran `$env:PYTHONPATH='src'; python -m agents_cli.cli catalog status`; result:
  concise terminal output with catalog path, version `3`, and table count `12`.
- Ran `$env:PYTHONPATH='src'; python -m agents_cli.cli health`; result: concise
  terminal output with cache path and check statuses. Bare Python reported
  `docling=missing`; the uv environment remains the verified Docling runtime.
- Ran `uv pip install -e ".[fts]"`; result: `tantivy==0.26.0` installed in the
  local uv environment.
- Ran a throwaway Tantivy API check in the uv environment; result: created a
  temporary index, inserted one stored document, searched `bank`, and retrieved
  stored fields successfully.
- Ran `uv run python -m agents_cli.cli health`; result: concise output with
  `docling=ok` and `tantivy=ok`.
- Ran `python -m py_compile` on all current `src/agents_cli/*.py` files after
  adding FTS; result: success.
- Ran `uv run python -m agents_cli.cli index folder tests\fixtures\parse-basic --force`;
  result: `status: ok`, root `parse-basic`, one planned/indexed chunk, one
  indexed document, and index URI
  `fts/tantivy_default_en/scope_e2bf17f2ccde28e25ef84119053e88cd`.
- Ran `uv run python -m agents_cli.cli search text "dummy pdf" --limit 5`;
  result: `status: ok`, one hit returned across one FTS index, and the hit
  resolved to the public dummy PDF fixture.
- Reran `uv run python -m agents_cli.cli index folder tests\fixtures\parse-basic`;
  result: `status: ok`, `index_status: current`, `chunks_indexed: 0`, and
  `chunks_unchanged: 1`, proving watermark-based unchanged behavior.
- Ran `uv run python -m agents_cli.cli parse folder "<scalable capital root>" --profile docling_fast_text --limit 1`;
  result: `status: ok`, one planned document parsed successfully, and auto-scan
  status `ok`.
- Ran `uv run python -m agents_cli.cli index folder "<scalable capital root>" --force`;
  result: `status: ok`, root `scalable capital`, 99 planned/indexed chunks,
  99 indexed documents, and index URI
  `fts/tantivy_default_en/scope_c50618d3203d3739e34239c58c6a919d`.
- Ran `uv run python -m agents_cli.cli search text "scalable capital" --limit 5`;
  result: `status: ok`, five hits returned across two current FTS indexes,
  with hits from the scalable-capital FTS island.
- Ran `uv run python -m agents_cli.cli search text "dummy pdf" --limit 5` after
  the scalable index was added; result: `status: ok`, one dummy fixture hit
  returned across two current FTS indexes.
- Ran a read-only SQLite query against `tantivy_indexes`; result: two current
  Tantivy registry rows totaling 100 indexed chunks, with 99 chunks for the
  scalable-capital root and one chunk for the dummy fixture root.
- Reran `uv run python -m agents_cli.cli parse folder tests\fixtures\parse-basic --profile docling_fast_text --limit 1`
  after redirecting Docling conversion stdout/stderr; result: concise CLI
  summary only, with no third-party progress output leaking to the terminal.
- Ran `uv pip install -e ".[semantic,embeddings]"`; initial attempts timed out
  on stale uv locks, then succeeded after removing the confirmed stale lock
  files and retrying with a longer lock timeout.
- Verified semantic dependency imports in the uv environment: `lancedb 0.33.0`,
  `fastembed 0.8.0`, `pyarrow 24.0.0`, and `numpy 2.4.6`.
- Ran a temporary LanceDB smoke test; result: created a local table with one
  vector row and retrieved it through vector search.
- Ran a FastEmbed dimension check; result: default
  `BAAI/bge-small-en-v1.5` profile reports dimension `384`. The first check
  downloaded model files and showed the usual Windows Hugging Face symlink
  warning.
- Ran `uv run python -m agents_cli.cli health`; result: concise output with
  `docling=ok`, `tantivy=ok`, `lancedb=ok`, and `fastembed=ok`.
- Ran `uv run python -m agents_cli.cli index folder tests\fixtures\parse-basic --semantic --force`;
  result: `status: ok`, root `parse-basic`, one planned/indexed chunk, one
  indexed document, vector dimension `384`, and store URI
  `semantic/fastembed_bge_small_en_v1_5/scope_e2bf17f2ccde28e25ef84119053e88cd.lancedb`.
- Ran `uv run python -m agents_cli.cli search semantic "dummy pdf" --limit 5`;
  result: `status: ok`, one semantic hit returned, with the dummy PDF fixture as
  the top hit.
- Reran `uv run python -m agents_cli.cli index folder tests\fixtures\parse-basic --semantic`;
  result: `status: ok`, `index_status: current`, one unchanged chunk, and no
  third-party console output.
- Ran `uv run python -m agents_cli.cli parse folder tests\fixtures\scan-basic --profile docling_fast_text --limit 1`;
  result: `status: ok`, one small public fixture document parsed successfully.
- Ran `uv run python -m agents_cli.cli index folder tests\fixtures\scan-basic --semantic --force`;
  result: first-time LanceDB table creation for a new root completed with only
  the compact CLI summary, proving OS-level suppression of Lance/Rust warnings.
- Ran `uv run python -m agents_cli.cli index folder "<scalable capital root>" --semantic --force`;
  result: `status: ok`, root `scalable capital`, 99 planned/indexed chunks, 99
  indexed documents, vector dimension `384`, and store URI
  `semantic/fastembed_bge_small_en_v1_5/scope_c50618d3203d3739e34239c58c6a919d.lancedb`.
- Ran `uv run python -m agents_cli.cli search semantic "scalable capital" --limit 5`;
  result: `status: ok`, five semantic hits returned across three current
  LanceDB stores, including hits from the scalable-capital store.
- Ran a read-only SQLite query against `lancedb_stores`; result: three current
  LanceDB registry rows totaling 101 indexed chunks, with 99 chunks for the
  scalable-capital root and one chunk each for the dummy and scan-basic fixture
  roots.
- Ran final `python -m py_compile` on all current `src/agents_cli/*.py` files
  after adding shared chunk helpers and semantic indexing; result: success.
- Reran `uv run python -m agents_cli.cli index folder tests\fixtures\parse-basic`;
  result: `status: ok`, backend `fts`, one planned chunk, one indexed document.
  The first run after chunk-helper refactoring refreshed the FTS index because
  the source high-watermark now includes the FTS profile.
- Reran `uv run python -m agents_cli.cli index folder tests\fixtures\parse-basic --semantic`;
  result: `status: ok`, backend `semantic`, `index_status: current`, one
  unchanged chunk.
- Ran final `uv run python -m agents_cli.cli search text "dummy pdf" --limit 3`;
  result: `status: ok`, one FTS hit returned across two current FTS indexes.
- Ran final `uv run python -m agents_cli.cli search semantic "dummy pdf" --limit 3`;
  result: `status: ok`, three semantic hits returned across three current
  LanceDB stores, with the dummy PDF fixture as the top hit.
- Ran final `uv run python -m agents_cli.cli health`; result: concise output
  with `docling=ok`, `tantivy=ok`, `lancedb=ok`, and `fastembed=ok`.
- Ran final read-only registry counts; result: `tantivy_indexes` has two
  current rows totaling 100 chunks, and `lancedb_stores` has three current rows
  totaling 101 chunks with vector dimension `384`.
- Ran `uv run pytest tests\test_hybrid_search.py tests\test_parse_failure_reporting.py`;
  result: six tests passed, including RRF fusion and localhost-only Ollama
  endpoint validation.
- Ran `uv run python -m py_compile src\agents_cli\hybrid.py src\agents_cli\cli.py src\agents_cli\results.py`;
  result: success.
- Ran `uv run ruff check src\agents_cli\hybrid.py src\agents_cli\cli.py src\agents_cli\results.py tests\test_hybrid_search.py`;
  result: all checks passed.
- Reran `uv run pytest tests\test_hybrid_search.py` and the same Ruff command
  after the final rerank-mode normalization tweak; result: two hybrid tests
  passed and Ruff passed.
- Ran `uv run python -m agents_cli.cli search hybrid --help`; result: help
  shows `--limit`, `--candidate-limit`, `--rrf-k`, `--rerank {none,ollama}`,
  `--ollama-model`, and `--ollama-url`.
- Ran `uv run python -m agents_cli.cli search hybrid "dummy pdf" --limit 5`;
  result: `status: ok`, five hits returned, 50 candidates fused, and the dummy
  PDF fixture was the top hit with matched backends `fts+semantic`. Result
  folder: `results/2026.06/06/172325-search-hybrid/`.
- Ran `uv run python -m agents_cli.cli search hybrid "scalable capital" --limit 5`;
  result: `status: ok`, five hits returned, 58 candidates fused, and the top
  three hits were scalable-capital documents matched by both FTS and semantic
  search. Result folder: `results/2026.06/06/172339-search-hybrid/`.
- Ran `uv run python -m agents_cli.cli search hybrid "dummy pdf" --limit 3 --rerank ollama --ollama-model local-test --ollama-url https://example.com`;
  result: `status: partial`, the non-local Ollama URL was rejected before any
  remote call, and RRF results were preserved. Result folder:
  `results/2026.06/06/172350-search-hybrid/`.
- Updated search defaults to FTS `--limit 30`, semantic `--limit 30`, and
  hybrid final `--limit 30` with `--candidate-limit 60` per backend.
- Verified `agents-docs search text --help`, `agents-docs search semantic
  --help`, and `agents-docs search hybrid --help` expose the new defaults.

Runtime proof currently covers Phase 2 CLI scaffold commands, Phase 3 SQLite
catalog migration/status plus source inventory, the first Phase 4 Docling parse
path, Phase 5 Tantivy FTS build/search, and Phase 6 LanceDB semantic
build/search, and Phase 7 hybrid RRF search.

## Future Proof Targets

- Show expected versus actual search hits for a small fixture corpus.
- Show that search results hydrate provenance through SQLite instead of relying
  on lower indexes as the catalog.
- Record index health, rebuild, refresh, and deletion commands.
- Prove the manager-repository contract with a synthetic source manifest and
  structured JSON/JSONL outputs under `results/`.
- Prove no command exposes `--cache-root` and that producer commands create
  missing catalog tables through the centralized table-creation path.
