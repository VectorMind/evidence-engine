# Plan: Docling Corpus Cache CLI

Date: 2026-06-04
Status: Draft reworked after catalog review on 2026-06-05.

## Problem Summary

Manager repositories need a reusable public CLI that can build local document
corpus caches from explicit caller-owned folders, files, archives, or manifests.
This repo owns the reusable implementation: inventory, Docling conversion,
SQLite catalog control, Tantivy FTS indexes, LanceDB embedding stores, refresh
lifecycle, and machine-readable command reports.

The catalog must stay focused. It should not become a second copy of every
backend, every run log, every migration step, or every generated indexing row.

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
| CR-009 | Tantivy/LanceDB store registries duplicate island responsibility. | Removed dedicated registry tables; `index_scopes` stores only current pointers and status for lower islands. |
| CR-010 | Command runs and messages do not belong in the database. | Removed command-run/message tables; command output goes to `<cache_root>/.results/<date>/<time-run_id>/`. |

## Resolution Summary

Use a current-state catalog plus separate config/template files:

- root `catalog.yaml` defines only SQLite current-state catalog tables;
- `config/exposures.yaml` defines exposure kinds, cache-root layout, and blob
  storage profiles;
- `config/embeddings.yaml` defines embedding profiles;
- `store_templates.yaml` defines generated Tantivy and LanceDB chunk row shapes;
- SQLite stores source inventory, current documents, artifacts, blobs, document
  objects, valuable items, and lower-index scope pointers;
- generated chunks live inside lower index islands, not as catalog tables;
- command reports and logs live under `.results/` folders, not SQLite.

## Goal

Deliver an autonomous Python package and CLI named `agents-docs` that can build,
refresh, inspect, and health-check local document corpus caches from explicit
folders or manifests.

## Root Layout Scope

| Path | Owner | Exposure | Scope In V1 |
| --- | --- | --- | --- |
| `catalog.yaml` | repo | YAML schema | Reviewable public schema for current-state SQLite catalog tables. |
| `config/exposures.yaml` | repo | YAML config | Exposure kinds, cache-root path templates, and blob storage profile defaults. |
| `config/embeddings.yaml` | repo | YAML config | Local embedding profiles accepted by semantic indexing commands. |
| `store_templates.yaml` | repo | YAML template | Lower-index generated row templates for Tantivy and LanceDB chunks. |
| `<cache_root>/catalog/catalog.sqlite` | CLI | SQLite | Authoritative current source, document, object, valuable-item, blob, and scope state. |
| `<cache_root>/blobs/<yyyy>/<mm>/<prefix>/<sha256>` | CLI | file | External payloads above the blob threshold. Referenced by SQLite. |
| `<cache_root>/docling/` | CLI | SQLite/file | Optional exported Docling JSON/Markdown/text artifacts. Small payloads may be inline SQLite blobs. |
| `<cache_root>/fts/<fts_profile>/<scope_id>/` | CLI | Tantivy directory | Chunk-level full-text island generated from catalog objects. |
| `<cache_root>/semantic/<embedding_profile>/<scope_id>.lancedb/` | CLI | LanceDB directory | Chunk-level semantic island generated from catalog objects. |
| `<cache_root>/.results/<date>/<time-run_id>/` | CLI | file | Structured command reports, messages, and logs. |

## Catalog Contract

The root `catalog.yaml` defines:

- `source_roots`: caller-approved root scope, usually one row for single-root
  CLI calls;
- `source_items`: current file/archive/connector inventory and hashes;
- `documents`: current parse state, not historical versions;
- `docling_artifacts`: current generated artifacts;
- `artifact_blobs`: inline or external payload rows;
- `document_objects`: normalized Docling object layer before indexing;
- `valuable_items`: high-value tables, diagrams, charts, signatures, clauses,
  receipts, and similar items;
- `index_scopes`: current pointers and status for lower FTS and semantic
  islands.

The catalog does not define chunk tables, command logs, embedding config, or
backend-internal Tantivy/LanceDB rows.

## CLI Surface

The first public command is `agents-docs`.

Control commands:

```powershell
agents-docs catalog init --cache-root .corpus-cache --catalog catalog.yaml --json
agents-docs catalog migrate --cache-root .corpus-cache --json
agents-docs catalog status --cache-root .corpus-cache --json
agents-docs health --cache-root .corpus-cache --json
```

Folder inventory:

```powershell
agents-docs inventory scan-folder `
  --source-root "C:\docs\example-folder" `
  --root-label example_folder `
  --cache-root .corpus-cache `
  --include "**/*.pdf" `
  --include "**/*.docx" `
  --include "**/*.md" `
  --jsonl
```

Docling parse and artifact registration:

```powershell
agents-docs parse docling-folder `
  --source-root "C:\docs\example-folder" `
  --cache-root .corpus-cache `
  --parser-profile docling_default `
  --to docling_json `
  --to markdown `
  --artifact-storage default_artifact_blobs `
  --jsonl
```

Tantivy FTS build for a folder scope:

```powershell
agents-docs index fts build-folder `
  --source-root "C:\docs\example-folder" `
  --scope-path "." `
  --cache-root .corpus-cache `
  --fts-profile tantivy_default_en `
  --chunk-profile docling_hybrid_v1 `
  --json
```

LanceDB semantic build for a folder scope:

```powershell
agents-docs index semantic build-folder `
  --source-root "C:\docs\example-folder" `
  --scope-path "." `
  --cache-root .corpus-cache `
  --embedding-profile fastembed_bge_small_en_v1_5 `
  --chunk-profile docling_hybrid_v1 `
  --store-policy one_per_folder `
  --json
```

## Design Answers

- `source_roots` is kept because it gives stable relative paths, labels, and
  future multi-root support. For a single-root CLI call, it is just one row.
- `document_versions` was too heavy for this cache; current `documents` rows
  are enough because stale state and source hashes drive refresh.
- Chunking belongs to indexing. SQLite stores paragraph/section/table/etc.
  master objects; lower index chunks reference those objects.
- Tantivy/LanceDB row shapes are still useful to specify, but they are templates
  for generated island rows, not catalog tables.
- Command results are operational proof and belong in `.results/`, not the
  current-state catalog.

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
- structured JSON/JSONL command reports under `.results/`;
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
- `agents-docs catalog status --json` reports an uninitialized cache cleanly.

### Phase 3: SQLite Catalog

Deliverables:

- stdlib `sqlite3` migration runner using `PRAGMA user_version`;
- tables from `catalog.yaml`;
- source root/item/document/object/valuable-item/blob/scope state;
- control-only catalog commands.

Proof:

- synthetic folder inventory initializes a catalog;
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
- scope pointer updates in SQLite.

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
- scope pointer updates in SQLite.

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

- manager-style synthetic run can consume SQLite plus `.results/` reports
  without knowing lower-index internals.

## New Open Points

| ID | Open Point | Current Leaning |
| --- | --- | --- |
| NOP-001 | Confirm blob thresholds and compression. | Start with 512 KiB external threshold, 32 KiB inline compression threshold, zstd for our Python stack. |
| NOP-002 | Confirm first Docling parser profiles. | `docling_default`, `docling_ocr`, and `docling_fast_text` are likely enough for first fixtures. |
| NOP-003 | Define the exact chunking profile. | Generate chunks only while building lower indexes; reference primary catalog `object_id`. |
| NOP-004 | Confirm LanceDB store policy default. | Expose `one_per_folder`; allow `one_per_root` as a simpler first test if folder fanout is noisy. |
| NOP-005 | Choose the first embedding default. | `fastembed_bge_small_en_v1_5` is the likely default; static model2vec remains optional. |
| NOP-006 | Decide when search commands enter scope. | Build/refresh/status come first; search can follow once indexes are populated. |
| NOP-007 | Pin dependency versions. | Defer until `pyproject.toml` and install proof. |

## Exit Criteria

- Root `catalog.yaml` is accepted as the SQLite catalog baseline.
- Config and lower-index template YAML files are accepted.
- `agents-docs` package and console script exist.
- SQLite catalog can be initialized and migrated with stdlib `sqlite3`.
- Folder inventory tracks SHA-256 and freshness.
- Docling artifacts can be stored inline or externally by threshold.
- Catalog objects feed generated Tantivy and LanceDB chunks only at indexing
  time.
- Synthetic fixtures prove build, refresh, rebuild, status, and `.results/`
  behavior.
