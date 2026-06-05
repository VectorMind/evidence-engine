# Specification: Corpus Cache CLI

## Purpose

`agents-cli` provides a reusable document corpus-cache CLI for manager
repositories. The CLI is exposed as `agents-docs`.

The CLI owns inventory, Docling parsing orchestration, SQLite catalog control,
Tantivy full-text index management, LanceDB semantic store management, refresh
lifecycle, health checks, and structured command reports.

Manager repositories own private source selection, policy, retention, and output
locations. Consumers may read generated SQLite databases directly. The CLI does
not provide a data-access SQL wrapper.

## Catalog Contract

The repository root contains `catalog.yaml`. It is the public SQLite schema
contract for the current-state corpus-cache catalog.

The catalog defines:

- source roots and source items;
- current documents;
- Docling artifact records;
- artifact blob records;
- normalized document object records;
- valuable item records;
- index scopes that point to lower FTS and semantic islands.

The catalog does not define migration-history tables, command-run tables,
command-message tables, embedding-profile tables, database-exposure registry
tables, chunk tables, Tantivy row tables, or LanceDB row tables.

## Configuration Contracts

The repository root contains configuration and template contracts:

- `config/exposures.yaml`: backend exposure kinds, cache-root layout, and blob
  storage profiles;
- `config/embeddings.yaml`: embedding profile configuration;
- `store_templates.yaml`: generated lower-index row templates for Tantivy and
  LanceDB chunk rows.

These files are configuration or templates, not generated SQLite tables.

## Layer Model

The implementation uses these layers:

- source authority: caller-owned files, folders, archives, or connector objects;
- SQLite catalog: authoritative current metadata and control database;
- Docling artifacts: stored as SQLite blobs or external hash-addressed files;
- document objects: normalized pages, sections, paragraphs, tables, figures,
  diagrams, images, charts, formulas, code blocks, lists, and captions;
- valuable items: high-value objects surfaced for manager repositories;
- Tantivy indexes: full-text lower islands generated from catalog objects;
- LanceDB stores: semantic lower islands generated from catalog objects;
- `.results/`: command reports, messages, and logs.

SQLite is the source of truth for source/document/object state and pointers to
lower-index islands. Tantivy and LanceDB own their internal generated chunk
rows.

## Storage Contract

A caller-provided cache root contains generated state:

```text
<cache_root>/
  catalog/
    catalog.sqlite
  blobs/
    <yyyy>/<mm>/<sha256_prefix>/<sha256>
  docling/
  fts/
    <fts_profile>/<scope_id>/
  semantic/
    <embedding_profile>/<scope_id>.lancedb/
  .results/
    <yyyy>-<mm>-<dd>/<hhmmss>-<run_id>/
```

The repository root YAML files are schema, config, and template contracts only.
Generated SQLite databases, Docling artifacts, FTS indexes, LanceDB stores, and
command results belong under caller-provided cache roots.

## Migration Contract

SQLite migrations are implemented in Python. The catalog tracks one current
schema version with SQLite `PRAGMA user_version`.

The catalog does not contain a `schema_migrations` table or full migration
history. Delta migrations may exist in code, but generated catalogs only need to
reflect the current supported version.

## Blob Storage Contract

Docling JSON, derived artifacts, and large generated payloads use thresholded
blob storage:

- payloads below the external threshold may be stored inline in SQLite;
- payloads above the external threshold are stored under a hash-addressed file
  path and referenced from SQLite;
- payload rows record SHA-256, size, storage mode, compression, first seen, and
  last seen;
- every external payload must have a SQLite row;
- refresh logic uses source and payload hashes to avoid unnecessary work.

## Identity Contract

The CLI exposes stable identities:

- `root_id`: source-root identity;
- `source_item_id`: file, folder, archive member, or connector object identity;
- `doc_id`: current document identity for a source item lineage;
- `artifact_id`: generated artifact identity;
- `blob_id`: stored payload identity;
- `object_id`: normalized document object identity;
- `item_id`: valuable item identity;
- `scope_id`: folder/root/specialist indexing scope identity;
- `chunk_id`: generated lower-index chunk/search-unit identity;
- `run_id`: command execution identity for `.results/` output.

Lower indexes may use backend-native row IDs, but generated chunk rows carry
`chunk_id`, `doc_id`, `object_id`, and `scope_id`.

## SQLite Contract

SQLite is implemented first with Python stdlib `sqlite3`.

SQLite owns:

- source roots and source items;
- current documents;
- Docling artifact records;
- blob payload records;
- normalized document objects;
- valuable items;
- index scopes with FTS and semantic island URIs and status.

SQLite does not own:

- full migration history;
- database exposure configuration;
- embedding profile configuration;
- generated chunk rows;
- Tantivy internal document rows;
- LanceDB internal rows;
- command logs or messages.

The CLI provides control commands for initialization, migration, status, health,
and lifecycle operations. It does not provide arbitrary SQL query or export
wrappers for data access.

## Docling Contract

The CLI wraps Docling through Python APIs so it can assign stable IDs, capture
tool versions and parser profiles, store artifacts through the blob policy, and
emit structured run messages.

Direct Docling CLI usage remains useful for debugging. The CLI contract maps
Docling options to named parser profiles rather than requiring callers to pass
raw Docling flags for every run.

The implementation stores raw Docling output where useful, but normalizes only
the first approved object and valuable-item layers into SQLite. It does not
mirror every Docling JSON node into SQL.

## Object And Chunk Contract

The first approved normalized object set is:

```text
page, section, paragraph, table, figure, diagram, image, chart, formula,
codeblock, list, caption
```

Chunks are not catalog objects. Chunking is an indexing feature that happens
when Tantivy or LanceDB stores are built or refreshed.

Generated chunks reference catalog master objects by `object_id`. No catalog
table is required to link chunks to objects.

## FTS Contract

The CLI owns Tantivy index creation, refresh, status, rebuild, and deletion.

Each Tantivy document represents one generated indexing chunk. The row shape is
defined in `store_templates.yaml`, not in `catalog.yaml`.

The SQLite catalog stores only current scope-level pointers and status for FTS:
profile name, cache-root-relative Tantivy URI, source high watermark, and
current lifecycle state.

## Semantic Contract

The CLI owns LanceDB store creation, refresh, status, rebuild, and deletion.

Each LanceDB row represents one generated indexing chunk. The row shape is
defined in `store_templates.yaml`, not in `catalog.yaml`.

Scoped LanceDB stores may be created per folder, root, or specialist scope. The
SQLite catalog stores only current scope-level pointers and status for semantic
stores: embedding profile, cache-root-relative LanceDB URI, source high
watermark, and current lifecycle state.

## Embedding Contract

Embedding logic is owned by this repo for v1. Embedding profiles are configured
in `config/embeddings.yaml`.

Remote embedding providers are not hard-coded defaults.

## Command Contract

The public CLI exposes:

- `agents-docs catalog init|migrate|status`;
- `agents-docs health`;
- `agents-docs inventory scan-folder`;
- `agents-docs parse docling-folder`;
- `agents-docs index fts build-folder|refresh-folder|status|rebuild|delete`;
- `agents-docs index semantic build-folder|refresh-folder|status|rebuild|delete`;
- `agents-docs index folder` as an early convenience command;
- search commands only after build/refresh/status behavior is stable.

Every non-interactive command supports structured `--json` or `--jsonl` output.
Commands that modify cache state support dry-run when the operation can be
planned without writes.

Every command writes structured results under `.results/` for the caller cache
root. Results include:

- command name;
- schema version;
- tool versions;
- config hash;
- run ID;
- cache root;
- created, changed, unchanged, skipped, deferred, stale, and failed counts;
- fatal errors separately from retryable or deferred work.

## Refresh Contract

The CLI tracks SHA-256 hashes and modification metadata for source items and
generated payloads.

Refresh behavior:

- skip unchanged source items;
- mark affected documents, objects, artifacts, and index scopes stale when
  source hashes change;
- for small scoped indexes, allow delete-and-rebuild instead of incremental
  mutation;
- record current stale/rebuilt/deleted/deferred/failed state in SQLite;
- record command details in `.results/`.

## Redaction And Privacy Contract

The CLI has no personal defaults. It never assumes private source roots, output
locations, taxonomies, or embedding providers.

Diagnostics are redacted by default. Full paths and raw private text require an
explicit caller option.

Errors distinguish:

- fatal failures;
- skipped work;
- deferred work;
- stale indexes;
- partial results;
- policy-denied work.

## Dependency Contract

The repository is autonomous and provides `pyproject.toml` dependency groups for
implementation and downstream use.

Dependency groups include:

- base CLI/runtime;
- Docling parsing;
- Tantivy FTS;
- LanceDB semantic indexing;
- local embeddings;
- optional heavier embeddings;
- optional external OCR/tooling checks.

External system tools are detected by health checks and are not assumed to
exist.

## Non-Goals

The CLI does not own private source policy, private retention policy, curated
personal knowledge, manager-repository reasoning, or central skill workflows.

The CLI does not provide a SQL data-access wrapper.

The CLI does not normalize every Docling JSON node into SQL tables.

The CLI does not require central skills to implement indexing internals.
