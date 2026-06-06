# Implementation: Docling Search Index

Date: 2026-06-04
Status: Phase 6 LanceDB semantic indexing started.

## Notes

- Created the dated planning packet.
- Added `survey.md` as the review gate before implementation planning.
- Reviewed the documents-manager handoff for expected public lower-layer
  responsibilities.
- Revised `plan.md` around a split architecture: central SQLite metadata
  catalog, Tantivy FTS shards, scoped LanceDB vector stores, and preserved
  Docling artifacts.
- Added `handoff.md` for lower-layer expectations from `.agents/skills` and
  likely Python dependency groups.
- Read the `documents-manager` workflow and personal document index plan.
- Corrected the scope: `agents-cli` owns the reusable corpus-cache CLI
  implementation, while central skills are wrappers and manager repositories
  are customers.
- Added `WORKFLOW.md` with the repository's spec-driven process and plan shape.
- Added `specifications/corpus-cache-cli/spec.md` for binding corpus-cache CLI
  contracts.
- Rewrote `plan.md` around problem summary, resolution summary, objectives,
  open points, and implementation phases.
- Rewrote `handoff.md` as a consumer contract and skills-wrapper boundary.
- No search-index code, dependency changes, package scaffolding, or CLI behavior
  changes have been made for this work.
- Read the 2026-06-05 reference handoff from
  `C:\dev\wassfila\documents-manager\plans\2026-06-05-personal-document-index\handoff.md`.
- Reviewed the `MicroWebStacks/content-structure` repository, especially its
  root catalog, README, `src/blob_manager.js`, `src/structure_db.js`, and CLI.
- Added root `catalog.yaml` as the draft schema review surface for all SQLite,
  file, Tantivy, and LanceDB exposures.
- Updated `catalog.yaml` so dataset metadata is represented as direct entries
  (`dataset_role`, `durability`) instead of nested `fields`.
- Rewritten `catalog.yaml` table `columns` entries as one-line YAML maps in the
  form `{name: ..., type: ..., description: ...}`.
- Reworked `plan.md` with the user answers to OP-001 through OP-015, concrete
  `agents-docs` command examples, a root layout scope table, Docling mapping,
  blob-storage analysis, embedding profile candidates, and new open points.
- Rewrote `specifications/corpus-cache-cli/spec.md` to align with the reviewed
  decisions: stdlib `sqlite3`, no SQL data-access wrapper, chunk-only lower
  indexes, thresholded blob storage, and SQLite registry rows for file-based
  database islands.
- Applied the catalog review:
  removed `schema_migrations`, `database_exposures`, `document_versions`,
  `chunk_records`, `chunk_object_links`, `embedding_profiles`,
  `tantivy_indexes`, `tantivy_documents`, `lancedb_stores`, `lancedb_chunks`,
  `index_jobs`, `command_runs`, and `command_messages` from `catalog.yaml`.
- Replaced `document_versions` with current-state `documents`.
- Removed `chunk` from `document_objects.object_type`.
- Added `valuable_items` as a catalog table for current high-value document
  items.
- Added `config/exposures.yaml`, `config/embeddings.yaml`, and
  `store_templates.yaml` so backend settings and lower-index row shapes are not
  modeled as catalog tables.
- Rewrote `specifications/corpus-cache-cli/spec.md` and `plan.md` around the
  reviewed split: current-state catalog, config files, lower-index templates,
  and `.results/` command output.
- Reintroduced lean catalog registry tables `tantivy_indexes` and
  `lancedb_stores` after clarifying that the catalog must know which physical
  lower-index islands exist and where to find them. The internal row schemas
  remain only in `store_templates.yaml`.
- Updated the CLI contract so the cache root is fixed at
  `$HOME/.cache/agents-docs/`, commands never accept a cache-root argument, and
  there is no `init` command.
- Added `config/parser.yaml` for parser profiles, traversal defaults, indexing
  defaults, and safeguard defaults.
- Reworked the CLI surface to two levels at most: `catalog migrate`,
  `catalog status`, `health`, `scan folder`, `parse folder`, `index folder`,
  and later `search text`.
- Added `pyproject.toml` with package metadata, `agents-docs` console script,
  base dependencies, optional dependency extras, and dev dependency group.
- Added `src/agents_cli/` package skeleton with `__init__.py`, fixed path
  helpers, and a minimal stdlib-backed `agents-docs` command router.
- Implemented read-only scaffold behavior for `agents-docs --help`,
  `agents-docs catalog status`, and `agents-docs health`.
- Reserved `scan folder`, `parse folder`, `index folder`, and `search text`
  command surfaces; they currently emit structured `not_implemented` JSON until
  later phases land.
- Rewrote `README.md` to document the fixed cache root, binding CLI surface,
  data surface, catalog/store-template/config links, and CLI/data flow diagrams.
- Added `docs/dependencies.md` with a table of all declared Python dependencies,
  one-sentence descriptions, selection rationale, and closest alternatives.
- Linked `docs/dependencies.md` from the top of `README.md`.
- Added `src/agents_cli/contracts.py` for bundled/source-tree contract file
  discovery.
- Added `src/agents_cli/catalog.py` with catalog schema loading, stdlib fallback
  parsing for `catalog.yaml`, centralized SQLite table creation, `PRAGMA
  user_version` migration, idempotent migration, and status reporting.
- Replaced the scaffold `catalog migrate` implementation with real fixed-home
  catalog creation at `$HOME/.cache/agents-docs/catalog/catalog.sqlite`.
- Expanded `catalog status` to report expected tables, missing tables, extra
  tables, row counts, and SQLite `user_version`.
- Updated `README.md` current status and catalog-status description.
- Split fixed catalog lifecycle into explicit `catalog create`, explicit
  `catalog migrate`, and shared producer `ensure_catalog()`.
- `catalog create` creates the fixed catalog when missing and is idempotent
  when the catalog is already current.
- `catalog migrate` now upgrades an existing stale or incomplete fixed catalog;
  when the catalog is missing it reports `status: missing` instead of acting as
  the manual create command.
- `ensure_catalog()` is the future producer path: it creates a missing catalog
  and migrates stale or incomplete catalog state before writes.
- Updated README, durable spec, and plan wording so the binding surface is
  `catalog create|migrate|status` with no `init` and no cache-root argument.
- Accepted `one_per_root` as the LanceDB V1 store policy. The user CLI folder
  root is the V1 index unit; automatic splitting into many roots is out of
  scope.
- Updated `config/parser.yaml` so `defaults.store_policy` is `one_per_root`.
- Added `src/agents_cli/config.py` for stdlib-first access to
  `config/parser.yaml`, with PyYAML support when installed and a fallback
  parser for the current simple config shape.
- Added `src/agents_cli/results.py` for fixed-cache command result folders with
  `result.json` and `events.jsonl`.
- Added `src/agents_cli/inventory.py` implementing `scan folder` source
  inventory over folder trees.
- `scan folder` now calls `ensure_catalog()`, records `source_roots`,
  `source_items`, and a root `index_scopes` row, hashes matching source files,
  detects created/changed/unchanged/deleted inventory rows, and returns
  redaction-safe JSON.
- `scan folder` supports only the accepted safeguard override flags:
  `--max-files`, `--max-bytes`, and `--max-depth`.
- Added a public synthetic fixture under `tests/fixtures/scan-basic/`.
- Verified the user-provided root labeled `scalable capital`; the first scan
  recorded 107 matching files, four folders, and about 34 MB of source bytes,
  and the second scan classified all 111 rows as unchanged.
- Added `reports_root()` for optional HTML analytics reports under
  `$HOME/.cache/agents-docs/reports/`.
- Updated `config/exposures.yaml` so `results/` is the mandatory result
  surface and `reports/` is the optional on-demand report surface.
- Updated `CommandRun.finish()` so every command result folder includes
  `result.json`, `events.jsonl`, and a user-facing `summary.md`.
- Added generic HTML report generation for commands that request it. `scan
  folder --report` writes `reports/<date>/<run>/report.html` and returns
  `report_uri`.
- Updated health output so it reports both `results_root_exists` and
  `reports_root_exists`.
- Recorded the report responsibility split: the CLI owns stable result inputs
  and generic HTML reports; skill wrappers can customize richer reports from
  `result.json`, `summary.md`, and the catalog.
- Implemented the inventory-statistics patch before moving to parsing/indexing.
- Bumped `catalog.yaml` to spec version `0.3` and the runtime SQLite
  `PRAGMA user_version` target to `3`.
- Added `source_root_stats` and `source_extension_stats` to `catalog.yaml`.
- Renamed new mandatory command output from `.results/` to `results/`; existing
  `.results/` folders are legacy local output and were not migrated.
- Updated `results_root()` and `config/exposures.yaml` to use
  `$HOME/.cache/agents-docs/results/`.
- `scan folder` now emits `statistics` in `result.json`, including folder
  count, file count, total/average/min/max file size, and per-extension count
  and byte aggregates.
- Successful scans upsert `source_root_stats` and replace current
  `source_extension_stats` for the root. Deferred scans return run-level
  statistics but do not replace current catalog stats.
- `summary.md` now includes file-size statistics and a top-extension table.
- `scan folder --report` now includes generic SVG pie charts for extension mix
  by file count and by total size, plus an extension summary table.
- Updated parser defaults so omitted `--profile` uses `docling_ocr` and
  canonical artifact outputs default to `docling_json` only.
- Added `src/agents_cli/blobs.py` with thresholded artifact blob storage for
  inline SQLite blobs and external `blobs/` payloads, with zstd compression
  when available and gzip fallback for larger inline payloads.
- Added `src/agents_cli/parse.py` implementing `parse folder`.
- `parse folder` auto-runs catalog ensure and folder scan, then parses current
  source files through Docling.
- Added parse CLI flags `--profile`, `--limit`, and `--report`.
- Added Docling runtime health detection.
- Added public PDF fixture `tests/fixtures/parse-basic/dummy.pdf`.
- `parse folder` stores canonical Docling JSON through `artifact_blobs` and
  `docling_artifacts`, updates `documents`, and writes a first preview
  `document_objects` paragraph row.
- Parse freshness now includes source hash, parser profile, and `parsed` status,
  so switching profiles reparses instead of incorrectly returning unchanged.
- Installed the Docling extra successfully in the local uv environment with
  `uv pip install -e ".[docling]"` after
  `python -m pip install -e ".[docling]"` timed out twice.
- The first parallel OCR/fast-text run exposed a first-run model-download race:
  OCR returned one `RuntimeError` while RapidOCR/docling models were still being
  downloaded. A sequential direct OCR diagnostic succeeded after models were
  present.
- Verified default `docling_ocr` parsing on the public PDF fixture after model
  downloads; it wrote one document, one JSON artifact, one blob, and one
  preview object.
- Verified `docling_fast_text` parsing on the public PDF fixture; it wrote the
  same canonical JSON artifact shape with OCR disabled.
- Verified a repeated default `docling_ocr` parse returns one unchanged document
  after freshness detection includes source hash, parser profile, and parsed
  status.
- Reworked console output so commands print a compact human summary instead of
  the full JSON payload.
- Reworked command result and report folder naming to
  `<yyyy>.<mm>/<dd>/<hhmmss>-<command>/`, using command slugs such as
  `scan-folder` and `parse-folder` instead of hash suffixes. Same-second
  collisions get a small numeric suffix.
- Updated `config/exposures.yaml`, README, spec, and plan wording for the new
  result/report path contract.
- Installed the FTS extra successfully in the local uv environment with
  `uv pip install -e ".[fts]"`; this installed `tantivy==0.26.0`.
- Added `src/agents_cli/fts.py` for Tantivy-backed FTS build and search.
- `index folder` now auto-runs scan, builds one FTS island per folder root
  scope under `fts/<fts_profile>/<scope_id>/`, and updates the
  `tantivy_indexes` registry row.
- FTS V1 generates one chunk per current parsed `document_objects` text preview.
  Chunks remain only inside Tantivy and reference catalog objects by
  `object_id`.
- `index folder` does not silently parse or OCR missing documents; it returns a
  deferred result when no parsed objects exist.
- Added `--force` to `index folder` for explicit rebuilds when the watermark is
  already current.
- `search text` now searches current Tantivy indexes, merges hits, and returns
  stored chunk provenance with compact console output and persisted
  `result.json`.
- Added `--limit` to `search text`.
- Health output now reports Tantivy availability.
- Redirected Docling stdout/stderr during conversion so third-party progress
  output does not leak past the CLI's compact console summary.
- Installed the semantic and embeddings extras in the local uv environment.
  Verified `lancedb==0.33.0`, `fastembed==0.8.0`, `pyarrow==24.0.0`, and
  `numpy==2.4.6`.
- Added `src/agents_cli/chunks.py` so FTS and semantic indexing use the same
  generated chunk IDs, source high-watermarks, document counts, and content
  types.
- Refactored `src/agents_cli/fts.py` to use the shared chunk helper instead of
  its private chunk loader.
- Added `src/agents_cli/semantic.py` for LanceDB-backed semantic build and
  search.
- `index folder --semantic` now auto-runs scan, embeds current parsed chunks
  with the configured FastEmbed profile, writes a LanceDB `chunks` table under
  `semantic/<embedding_profile>/<scope_id>.lancedb/`, and updates
  `lancedb_stores`.
- FastEmbed model files are cached under
  `$HOME/.cache/agents-docs/models/fastembed/`, now declared in
  `config/exposures.yaml` and the storage contract.
- `search semantic` now embeds the query, searches current LanceDB stores, and
  returns hydrated chunk provenance with semantic distance and a normalized
  score.
- Added OS-level stdout/stderr suppression around FastEmbed/LanceDB calls so
  first-time model/table creation does not leak third-party progress or Rust
  warnings past the compact CLI summary.
- Health output now reports LanceDB and FastEmbed availability.
- Added `docs/models.md` to document all model/runtime surfaces: Docling/OCR,
  embeddings, semantic stores, planned hybrid RRF, planned local-only reranking
  with FastEmbed or SentenceTransformers, and planned local REST providers
  limited to OpenAI-compatible local servers and Ollama.
- Linked `docs/models.md` from README and `docs/dependencies.md`.

## Pending Decisions

- Confirm whether the initial blob threshold and compression defaults need
  tuning after larger real-document parsing.
- Define the exact generated chunking profile and copied lower-index metadata
  set for `store_templates.yaml`.
- Choose the first embedding default.
- Decide when search commands enter scope after build/refresh/status commands.
- Pin dependency versions in `pyproject.toml`.
- Finalize folder-tree safeguards and override flags for large jobs.
- Decide whether the initial stdlib command router remains or gets replaced by
  Typer after dependency installation.
