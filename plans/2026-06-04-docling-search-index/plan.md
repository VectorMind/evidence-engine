# Plan: Docling Corpus Cache CLI

Date: 2026-06-04
Status: Draft reworked after CLI-surface review on 2026-06-05.

## Problem Summary

Manager repositories need a reusable public CLI that can build local document
corpus caches from explicit caller-owned folders, files, archives, or manifests.
This repo owns the reusable implementation: inventory, Docling conversion,
SQLite catalog control, Tantivy FTS indexes, LanceDB embedding stores, refresh
lifecycle, and machine-readable command reports.

The catalog must stay focused. It should not become a second copy of every
backend, every run log, every migration step, or every generated indexing row.

The CLI must also stay simple. The cache root is fixed in the user's home cache
directory, and commands should have as few arguments as possible.

## Catalog Review Decisions From 2026-06-05

| ID | Review Point | Resolution |
| --- | --- | --- |
| CR-001 | Migration history does not belong in catalog tables. | Removed `schema_migrations`; Python migrations track one current catalog version with SQLite `PRAGMA user_version`. |
| CR-002 | `database_exposures` is over-modeled. | Removed it. Backend exposure settings now live in `config/exposures.yaml`; each catalog table keeps its direct `exposures` metadata. |
| CR-003 | `source_roots` may be unnecessary for single-root queries. | Kept it but scoped it as usually one row for single-root CLI calls; it keeps stable root labels and relative paths without hurting the single-root path. |
| CR-004 | Historical `document_versions` are not needed. | Replaced with current-state `documents`; only current source hash, parser profile, and parse state matter. |
| CR-005 | `chunk` should not be a document object type. | Removed `chunk` from `document_objects.object_type`; chunking is an indexing feature only. |
| CR-006 | `chunk_object_links` is unnecessary. | Removed it. Generated lower-index chunks reference master catalog objects directly by `object_id`. |
| CR-007 | `embedding_profiles` is config material. | Moved embedding profiles to `config/embeddings.yaml`. |
| CR-008 | Tantivy/LanceDB internal row schemas should not be catalog tables. | Removed `tantivy_documents` and `lancedb_chunks` from `catalog.yaml`; added `store_templates.yaml`. |
| CR-009 | Tantivy/LanceDB store registries are still needed, but not their internal rows. | Keep lean `tantivy_indexes` and `lancedb_stores` registry tables for locating and managing physical islands. Keep generated row templates in `store_templates.yaml`. |
| CR-010 | Command runs and messages do not belong in the database. | Removed command-run/message tables; command output goes to `$HOME/.cache/agents-docs/results/<yyyy>.<mm>/<dd>/<hhmmss>-<command>/`. |

## Resolution Summary

Use a current-state catalog plus separate config/template files:

- root `catalog.yaml` defines only SQLite current-state catalog tables;
- `config/exposures.yaml` defines exposure kinds, cache-root layout, and blob
  storage profiles, including the fixed `$HOME/.cache/agents-docs/` cache root;
- `config/parser.yaml` defines parser, traversal, indexing, and safeguard
  defaults;
- `config/embeddings.yaml` defines embedding profiles;
- `store_templates.yaml` defines generated Tantivy and LanceDB chunk row shapes;
- SQLite stores source inventory, current documents, artifacts, blobs, document
  objects, valuable items, index scopes, and lower-index registry rows;
- generated chunks live inside lower index islands, not as catalog tables;
- command result JSON, events, logs, and user-facing Markdown summaries live
  under `results/` folders, not SQLite.
- optional HTML analytics reports live under `reports/` only when requested.
- there is no `init` command; producers call centralized table creation before
  writing. `catalog create` creates the fixed catalog when it is missing, and
  `catalog migrate` upgrades an existing stale or incomplete catalog.
- producer commands auto-run safe prerequisites with defaults. `parse folder`
  auto-runs catalog ensure and folder scan before parsing.

## Goal

Deliver an autonomous Python package and CLI named `agents-docs` that can build,
refresh, inspect, and health-check local document corpus caches from explicit
folders or manifests.

## Root Layout Scope

| Path | Owner | Exposure | Scope In V1 |
| --- | --- | --- | --- |
| `catalog.yaml` | repo | YAML schema | Reviewable public schema for current-state SQLite catalog tables. |
| `config/exposures.yaml` | repo | YAML config | Exposure kinds, fixed home cache root, path templates, and blob storage profile defaults. |
| `config/parser.yaml` | repo | YAML config | Parser profiles, traversal defaults, index defaults, and safety limits. |
| `config/embeddings.yaml` | repo | YAML config | Local embedding profiles accepted by semantic indexing commands. |
| `store_templates.yaml` | repo | YAML template | Lower-index generated row templates for Tantivy and LanceDB chunks. |
| `$HOME/.cache/agents-docs/catalog/catalog.sqlite` | CLI | SQLite | Authoritative current source, document, object, valuable-item, blob, and scope state. |
| `$HOME/.cache/agents-docs/blobs/<yyyy>/<mm>/<prefix>/<sha256>` | CLI | file | External payloads above the blob threshold. Referenced by SQLite. |
| `$HOME/.cache/agents-docs/docling/` | CLI | SQLite/file | Optional exported Docling JSON/Markdown/text artifacts. Small payloads may be inline SQLite blobs. |
| `$HOME/.cache/agents-docs/fts/<fts_profile>/<scope_id>/` | CLI | Tantivy directory | Chunk-level full-text island generated from catalog objects. |
| `$HOME/.cache/agents-docs/semantic/<embedding_profile>/<scope_id>.lancedb/` | CLI | LanceDB directory | Chunk-level semantic island generated from catalog objects. |
| `$HOME/.cache/agents-docs/models/fastembed/` | CLI | file | Local FastEmbed model cache for semantic indexing commands. |
| `$HOME/.cache/agents-docs/results/<yyyy>.<mm>/<dd>/<hhmmss>-<command>/` | CLI | file | Mandatory `result.json`, `events.jsonl`, logs, and user-facing `summary.md`. |
| `$HOME/.cache/agents-docs/reports/<yyyy>.<mm>/<dd>/<hhmmss>-<command>/` | CLI | file | Optional on-demand HTML analytics reports. |

## Catalog Contract

The root `catalog.yaml` defines:

- `source_roots`: caller-approved root scope, usually one row for single-root
  CLI calls;
- `source_items`: current file/archive/connector inventory and hashes;
- `source_root_stats`: current aggregate source inventory statistics per root;
- `source_extension_stats`: current aggregate source inventory statistics per
  file extension and root;
- `documents`: current parse state, not historical versions;
- `docling_artifacts`: current generated artifacts;
- `artifact_blobs`: inline or external payload rows;
- `document_objects`: normalized Docling object layer before indexing;
- `valuable_items`: high-value tables, diagrams, charts, signatures, clauses,
  receipts, and similar items;
- `index_scopes`: logical root/folder/archive/specialist indexing scopes;
- `tantivy_indexes`: current registry rows for physical Tantivy FTS islands;
- `lancedb_stores`: current registry rows for physical LanceDB semantic
  islands.

The catalog does not define chunk tables, command logs, embedding config, or
backend-internal Tantivy/LanceDB rows. Source inventory statistics are allowed
because they are current-state metadata derived from `source_items`, not command
history.

## Fixed Cache And Catalog Creation

There is no `init` command and no configurable cache root. All commands use:

```text
$HOME/.cache/agents-docs/
```

The generated catalog is always:

```text
$HOME/.cache/agents-docs/catalog/catalog.sqlite
```

Every producer command calls the same centralized table creation/migration
function before writing. `catalog create` and the first write command both
create missing tables according to `catalog.yaml`; `catalog migrate` upgrades
an existing stale or incomplete catalog.

## CLI Surface

The first public command is `agents-docs`.

Use two levels at most: first command plus subcommand. Prefer positional args
for the only values that cannot sensibly default.

| First command | Subcommand | Mandatory args | Explanation | Defaults |
| --- | --- | --- | --- | --- |
| `catalog` | `create` | none | Creates `$HOME/.cache/agents-docs/catalog/catalog.sqlite` if it is missing. | `catalog.yaml`; no args. |
| `catalog` | `migrate` | none | Upgrades an existing stale or incomplete fixed home catalog. | `catalog.yaml`; no args. |
| `catalog` | `status` | none | Reports catalog version, table presence, key counts, and stale state. | Fixed home cache; no args. |
| `health` | none | none | Checks configured paths and available dependencies. | Fixed home cache and config files; no args. |
| `scan` | `folder <path>` | `path` | Inventories a folder tree, records source items, and creates the root index scope. | Includes/excludes and safety limits from `config/parser.yaml`; optional overrides are `--max-files`, `--max-bytes`, `--max-depth`, and `--report`. |
| `parse` | `folder <path>` | `path` | Auto-scans the folder tree, parses current sources through Docling, and records JSON artifacts/objects. | Parser defaults from `config/parser.yaml`; default profile is `docling_ocr`; optional flags are `--profile`, `--limit`, and `--report`. |
| `index` | `folder <path>` | `path` | Builds or refreshes the Tantivy FTS island for the folder root from current parsed document objects. Add `--semantic` to build the LanceDB semantic store instead. | FTS, embedding, and chunk defaults from config; optional `--force` rebuilds even when current. |
| `search` | `text <query>` | `query` | Searches current Tantivy FTS islands and returns hydrated chunk provenance. | Search defaults from config; optional `--limit` caps returned hits. |
| `search` | `semantic <query>` | `query` | Searches current LanceDB semantic stores and returns hydrated chunk provenance. | Embedding defaults from config; optional `--limit` caps returned hits. |

Example minimal calls:

```powershell
agents-docs catalog create
agents-docs catalog migrate
agents-docs catalog status
agents-docs health
agents-docs scan folder "C:\docs\example-folder"
agents-docs parse folder "C:\docs\example-folder"
agents-docs index folder "C:\docs\example-folder"
```

## Design Answers

- `source_roots` is kept because it gives stable relative paths, labels, and
  future multi-root support. For a single-root CLI call, it is just one row.
- `document_versions` was too heavy for this cache; current `documents` rows
  are enough because stale state and source hashes drive refresh.
- Chunking belongs to indexing. SQLite stores paragraph/section/table/etc.
  master objects; lower index chunks reference those objects.
- FTS V1 indexes only current parsed objects. `index folder` auto-scans, but it
  does not silently parse or OCR missing documents because that prerequisite can
  be expensive.
- Semantic V1 uses the same generated chunks as FTS, writes one LanceDB table
  named `chunks` per folder-root store, and resolves the default FastEmbed
  profile from `config/embeddings.yaml`.
- Tantivy/LanceDB row shapes are still useful to specify, but they are templates
  for generated island rows, not catalog tables.
- Tantivy/LanceDB registry rows are catalog state because the CLI must know
  which islands exist and where to find them.
- Command results are operational proof and belong in `results/`, not the
  current-state catalog. Every result folder contains a user-facing
  `summary.md`.
- Console output is a short human summary with links to `result.json`,
  `summary.md`, and optional `report.html`; machine consumers read persisted
  files rather than scraping terminal output.
- HTML analytics reports belong in `reports/` and are generated only when the
  caller passes a report flag.
- `folder` means folder tree by default. The given folder is the explicit root
  scope and V1 index unit.
- LanceDB defaults to one store per explicit folder root. Strategic splitting
  into many roots is out of scope for V1.
- Safeguards such as max file count, max byte budget, max parse time, traversal
  depth, symlink behavior, include globs, and exclude globs live in
  `config/parser.yaml`.
- Docling JSON is the canonical stored parse artifact. Markdown is lazy or
  optional export output, not a default stored duplicate.

## Implemented Patch: Inventory Statistics

This patch was implemented before moving to parsing and indexing.

### Output Path Rename

Rename the mandatory command result directory from `.results/` to `results/`.
The cache root is already hidden under `$HOME/.cache/agents-docs/`, so an
additional hidden child directory is unnecessary.

Implementation:

- `config/exposures.yaml` changes the result path template to
  `results/{yyyy}.{mm}/{dd}/{hhmmss}-{command}/`;
- `results_root()` returns `$HOME/.cache/agents-docs/results`;
- new runs write `result.json`, `events.jsonl`, and `summary.md` under
  `results/`;
- existing `.results/` run folders may be left as legacy local output and do
  not require migration.

### Scan Statistics

`scan folder` should compute inventory statistics during the existing traversal.
This does not require another filesystem pass because the scanner already sees
folders, file sizes, file extensions, media types, and matched/skipped files.

Run-level `result.json` should include:

- `statistics.folder_count`;
- `statistics.file_count`;
- `statistics.total_size_bytes`;
- `statistics.average_file_size_bytes`;
- `statistics.min_file_size_bytes`;
- `statistics.max_file_size_bytes`;
- `statistics.extension_stats[]` with extension, file count, total bytes,
  average bytes, min bytes, and max bytes.

`summary.md` should remain concise and user-facing:

- overview table with folder count, file count, total size, average size, min
  size, max size, skipped unmatched files, and failures;
- top extension table by count or size, capped to a small useful list.

`--report` should add generic HTML analytics content:

- overview text;
- file extension pie or donut chart by file count;
- file extension pie or donut chart by total bytes;
- compact extension table, capped or grouped with `other` when there are many
  extensions.

### Catalog Patch

The catalog now materializes current root statistics so manager repositories and
report skills can read stable current-state facts directly without finding the
latest result folder or repeating SQL aggregation.

Add `source_root_stats`:

| Column | Type | Purpose |
| --- | --- | --- |
| `root_id` | text | Source root being summarized. |
| `scope_id` | text | Root index scope summarized by this row. |
| `computed_at` | timestamp | UTC timestamp for the latest scan statistics. |
| `folder_count` | integer | Current folders seen for the root. |
| `file_count` | integer | Current matched files for the root. |
| `skipped_unmatched_count` | integer | Files skipped by include rules in the latest scan. |
| `failed_path_count` | integer | Paths that failed stat/hash in the latest scan. |
| `total_size_bytes` | integer | Total bytes across current matched files. |
| `average_file_size_bytes` | real | Average size across current matched files. |
| `min_file_size_bytes` | integer | Smallest matched file size. |
| `max_file_size_bytes` | integer | Largest matched file size. |
| `stats_status` | enum | `current`, `deferred`, or `failed`. |

Add `source_extension_stats`:

| Column | Type | Purpose |
| --- | --- | --- |
| `root_id` | text | Source root being summarized. |
| `extension` | text | Normalized lowercase extension, with `[none]` for no extension. |
| `media_type` | text | Dominant or representative media type for this extension. |
| `file_count` | integer | Current matched file count for this extension. |
| `total_size_bytes` | integer | Total bytes for this extension. |
| `average_file_size_bytes` | real | Average file size for this extension. |
| `min_file_size_bytes` | integer | Smallest matched file size for this extension. |
| `max_file_size_bytes` | integer | Largest matched file size for this extension. |
| `computed_at` | timestamp | UTC timestamp for the latest scan statistics. |

Recommended indexes:

- `pk_source_root_stats` unique on `root_id`;
- `pk_source_extension_stats` unique on `root_id, extension`;
- `idx_source_extension_stats_count` on `root_id, file_count`;
- `idx_source_extension_stats_size` on `root_id, total_size_bytes`.

Migration:

- bump catalog schema/user version from `0.2`/`2` to `0.3`/`3`;
- Python migration creates the two new tables and indexes if absent;
- each successful scan upserts root stats and replaces extension stats for that
  root;
- deferred scans may write run-level statistics to `result.json` but should not
  replace current catalog stats unless the traversal completed.

Higher-layer impact:

- manager repositories can read current inventory stats from SQLite;
- report skills can use catalog stats for current state or run stats for a
  specific command execution;
- no higher layer needs to rescan the filesystem to answer file-count,
  file-size, or extension-mix questions.

## Scope

This work covers:

- root catalog schema;
- config and store template contracts;
- package metadata and autonomous dependency groups;
- CLI command contracts;
- folder and manifest inventory;
- SQLite catalog migrations and control commands;
- source SHA and freshness tracking;
- Docling parsing through our wrapper;
- thresholded artifact blob storage;
- normalized object and valuable-item extraction;
- Tantivy FTS build, refresh, status, rebuild, and delete;
- LanceDB semantic build, refresh, status, rebuild, and delete;
- structured JSON/JSONL command reports under `results/`;
- tests with synthetic public fixtures.

## Non-Goals

- No private source paths, personal examples, personal taxonomies, or private
  fixture data.
- No data-access SQL wrapper; consumers can open the generated SQLite database
  read-only.
- No central skill implementation of indexing internals.
- No manager-repo policy implementation.
- No exhaustive SQL mirror of every Docling JSON node.
- No catalog history table for every migration.
- No catalog tables for generated chunks or lower-index rows.
- No command log tables in SQLite.
- No cache-root command argument.
- No `init` command.
- No remote embedding default.
- No MCP server before CLI and JSON contracts are stable.

## Implementation Phases

### Phase 0: Workflow And Specification

Deliverables:

- `WORKFLOW.md`;
- `specifications/corpus-cache-cli/spec.md`;
- dated plan packet.

Proof:

- planning review recorded in `test.md`.

### Phase 1: Catalog Schema Review

Deliverables:

- root `catalog.yaml`;
- `config/exposures.yaml`;
- `config/embeddings.yaml`;
- `store_templates.yaml`;
- reworked plan and durable spec alignment.

Proof:

- YAML shape checks pass;
- old catalog tables and stale references are removed.

### Phase 2: Package And CLI Skeleton

Deliverables:

- `pyproject.toml`;
- Python package layout;
- `agents-docs` console script;
- dependency extras for base, Docling, FTS, semantic, local embeddings, and
  optional heavy embeddings;
- command help and structured report helpers.

Proof:

- `agents-docs --help` runs;
- `agents-docs catalog status` reports a missing fixed catalog cleanly.

### Phase 3: SQLite Catalog

Deliverables:

- stdlib `sqlite3` migration runner using `PRAGMA user_version`;
- tables from `catalog.yaml`;
- source root/item/document/object/valuable-item/blob/scope/index registry
  state;
- control-only catalog commands.

Proof:

- `agents-docs catalog create` creates the fixed catalog when missing;
- `agents-docs catalog migrate` upgrades an existing stale or incomplete catalog;
- synthetic folder inventory can also create missing tables through the central
  table-creation path;
- consumers can open the `.db` read-only and inspect rows.

### Phase 4: Docling Artifact Import

Deliverables:

- Docling parser profiles;
- artifact blob storage;
- normalized object extraction;
- valuable-item extraction.

Proof:

- synthetic PDF/Markdown fixtures produce Docling artifacts, objects, valuable
  items, and hashes.

### Phase 5: Tantivy FTS

Deliverables:

- generated chunking for FTS;
- Tantivy row generation from `store_templates.yaml`;
- build, refresh, status, rebuild, and delete commands;
- `tantivy_indexes` registry updates in SQLite.

Proof:

- fixture searches hit expected generated chunks;
- unchanged input skips indexing;
- stale small scope can rebuild cleanly.

### Phase 6: LanceDB Semantic Stores

Deliverables:

- embedding profile loader from `config/embeddings.yaml`;
- generated chunking for semantic indexing;
- scoped LanceDB store creation;
- build, refresh, status, rebuild, and delete commands;
- `lancedb_stores` registry updates in SQLite.

Proof:

- fixture semantic queries hit expected generated chunks;
- status reports embedding profile, dimensions, row counts, and freshness.

### Phase 7: Search And Handoff Outputs

Deliverables:

- lexical, semantic, and hybrid search commands if still wanted after build
  commands stabilize;
- structured handoff/export records for manager repositories;
- redaction-safe diagnostics.

Proof:

- manager-style synthetic run can consume SQLite plus `results/` reports
  without knowing lower-index internals.

## Design Decisions

| ID | Decision | Resolution |
| --- | --- | --- |
| DD-001 | Blob thresholds and compression. | Use 512 KiB external threshold, 32 KiB inline compression threshold, and zstd for our Python stack. |
| DD-002 | First Docling parser profiles. | Use `docling_default`, `docling_ocr`, and `docling_fast_text`. |
| DD-003 | Chunking profile. | Use `docling_hybrid_v1`; generate chunks only while building lower indexes and reference primary catalog `object_id`. |
| DD-004 | LanceDB store policy default. | Use `one_per_root`; the user CLI folder root is the V1 index unit. |
| DD-005 | First embedding default. | Use `fastembed_bge_small_en_v1_5`; keep static model2vec optional. |
| DD-006 | Search timing. | Build/refresh/status come first; search follows once indexes are populated. |
| DD-007 | Dependency version pinning. | Keep current dependency bounds until full-stack install proof, then pin compatible versions. |
| DD-008 | Folder versus folder tree behavior and safeguards. | `folder` means folder tree by default; keep safeguard defaults in `config/parser.yaml` and require explicit overrides for big jobs. |
| DD-009 | Result summaries. | Every `results/` command folder includes a user-focused `summary.md` with concise overview tables and no long raw listings. |
| DD-010 | HTML reports. | Reports are optional on-demand CLI artifacts under `reports/`; the CLI owns generic reports and stable data inputs, while skill wrappers may create customized reports from the same surfaces. |
| DD-011 | Producer prerequisites. | Producer commands auto-run safe prior steps with defaults; `parse folder` auto-scans before parsing. |
| DD-012 | Default parser profile. | Omitted `--profile` uses `docling_ocr`; faster non-OCR parsing remains available through `--profile docling_fast_text`. |
| DD-013 | Parse artifact storage. | Store canonical Docling JSON through the blob storage manager; Markdown is lazy/optional and not stored by default. |
| DD-014 | FTS V1 scope. | Default `index folder` builds Tantivy FTS from existing parsed objects and auto-runs scan. |
| DD-015 | Semantic V1 scope. | `index folder --semantic` builds one LanceDB store per folder root from the same generated chunks, using the default FastEmbed profile. |

## Exit Criteria

- Root `catalog.yaml` is accepted as the SQLite catalog baseline.
- Config and lower-index template YAML files are accepted.
- `agents-docs` package and console script exist.
- SQLite catalog can be created and migrated with stdlib `sqlite3`.
- No command accepts a cache-root argument.
- No `init` command exists.
- Folder inventory tracks SHA-256 and freshness.
- Docling artifacts can be stored inline or externally by threshold.
- Catalog objects feed generated Tantivy and LanceDB chunks only at indexing
  time.
- Synthetic fixtures prove build, refresh, rebuild, status, and `results/`
  behavior.
