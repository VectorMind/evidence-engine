# Implementation: Docling Search Index

Date: 2026-06-04
Status: Phase 3 SQLite catalog started.

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
- No heavy runtime dependency installation has been run.

## Pending Decisions

- Confirm blob thresholds and compression defaults.
- Confirm first Docling parser profiles.
- Define the exact generated chunking profile and copied lower-index metadata
  set for `store_templates.yaml`.
- Confirm whether LanceDB defaults to one store per folder or one store per
  root for the first proof.
- Choose the first embedding default.
- Decide when search commands enter scope after build/refresh/status commands.
- Pin dependency versions in `pyproject.toml`.
- Define the synthetic fixture set for first proofs.
- Finalize folder-tree safeguards and override flags for large jobs.
- Decide whether the initial stdlib command router remains or gets replaced by
  Typer after dependency installation.
