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

## Fixed Cache Contract

The corpus-cache root is fixed at:

```text
$HOME/.cache/agents-docs/
```

Commands must not accept a cache-root argument. The catalog path is always:

```text
$HOME/.cache/agents-docs/catalog/catalog.sqlite
```

Every producer command calls the central catalog table-creation/migration
function before it writes catalog state. There is no `init` command. A missing
catalog is created by `catalog create` or by the first producer command that
needs it, using the schema in `catalog.yaml`. A stale or incomplete catalog is
upgraded by `catalog migrate` or by the same producer ensure path before writes.

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
- index scopes;
- Tantivy FTS island registry rows;
- LanceDB semantic island registry rows.

The catalog does not define migration-history tables, command-run tables,
command-message tables, embedding-profile tables, database-exposure registry
tables, chunk tables, Tantivy row-template tables, or LanceDB row-template
tables.

## Configuration Contracts

The repository root contains configuration and template contracts:

- `config/exposures.yaml`: backend exposure kinds, cache-root layout, and blob
  storage profiles;
- `config/parser.yaml`: parser, traversal, indexing, and safeguard defaults;
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
- Tantivy index registry: current locations and lifecycle state for full-text
  lower islands generated from catalog objects;
- LanceDB store registry: current locations and lifecycle state for semantic
  lower islands generated from catalog objects;
- `.results/`: command reports, messages, and logs.

SQLite is the source of truth for source/document/object state and for finding
lower-index islands. Tantivy and LanceDB own their internal generated chunk
rows.

## Storage Contract

The fixed cache root contains generated state:

```text
$HOME/.cache/agents-docs/
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
command results belong under the fixed home cache root.

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
- `fts_index_id`: Tantivy island registry identity;
- `semantic_store_id`: LanceDB island registry identity;
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
- index scopes;
- Tantivy index registry rows with profile, URI, template, row count,
  freshness, and lifecycle status;
- LanceDB store registry rows with embedding profile, URI, table name,
  template, row count, freshness, and lifecycle status.

SQLite does not own:

- full migration history;
- database exposure configuration;
- embedding profile configuration;
- generated chunk rows;
- Tantivy internal document rows;
- LanceDB internal rows;
- command logs or messages.

The CLI provides control commands for table creation, migration, status, health,
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

The SQLite catalog stores current Tantivy index registry rows: profile name,
chunk profile, template name, cache-root-relative Tantivy URI, indexed chunk
count, source high watermark, and lifecycle state. The catalog does not store
Tantivy documents.

## Semantic Contract

The CLI owns LanceDB store creation, refresh, status, rebuild, and deletion.

Each LanceDB row represents one generated indexing chunk. The row shape is
defined in `store_templates.yaml`, not in `catalog.yaml`.

Scoped LanceDB stores may be created per folder, root, or specialist scope. The
SQLite catalog stores current LanceDB store registry rows: embedding profile,
chunk profile, template name, cache-root-relative LanceDB URI, table name,
vector dimension, indexed chunk count, source high watermark, and lifecycle
state. The catalog does not store LanceDB rows.

## Embedding Contract

Embedding logic is owned by this repo for v1. Embedding profiles are configured
in `config/embeddings.yaml`.

Remote embedding providers are not hard-coded defaults.

## Command Contract

The public CLI exposes:

- `agents-docs catalog create|migrate|status`;
- `agents-docs health`;
- `agents-docs scan folder`;
- `agents-docs parse folder`;
- `agents-docs index folder`;
- `agents-docs search text`;
- search commands only after build/refresh/status behavior is stable.

The CLI is two levels at most: first command plus optional subcommand. Profiles,
cache paths, traversal defaults, parser defaults, index defaults, and safeguard
limits come from config files. Commands use positional arguments for the source
path or query text when those cannot be defaulted.

| First command | Subcommand | Mandatory args | Explanation | Defaults |
| --- | --- | --- | --- | --- |
| `catalog` | `create` | none | Creates the fixed home catalog when it is missing; returns current when it already exists. | Fixed cache root and `catalog.yaml`. |
| `catalog` | `migrate` | none | Upgrades a stale or incomplete existing fixed home catalog to the current schema. | Fixed cache root and `catalog.yaml`. |
| `catalog` | `status` | none | Reports fixed catalog version, table presence, counts, and stale state. | Fixed cache root. |
| `health` | none | none | Checks Python package, SQLite catalog, Docling, Tantivy, LanceDB, embeddings, and configured paths. | Fixed cache root and config files. |
| `scan` | `folder <path>` | `path` | Inventories a folder tree and records current source items. | Traversal and safeguard defaults from `config/parser.yaml`. |
| `parse` | `folder <path>` | `path` | Parses inventoried or directly supplied folder-tree sources through Docling and records artifacts/objects. | Parser and artifact defaults from `config/parser.yaml`. |
| `index` | `folder <path>` | `path` | Builds or refreshes FTS and semantic islands for the given folder root. | FTS, embedding, chunk, store, and safeguard defaults from config. |
| `search` | `text <query>` | `query` | Searches built lower-index islands and hydrates results through SQLite. | Search/index defaults from config; exact scope rules are deferred. |

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
- fixed cache root;
- created, changed, unchanged, skipped, deferred, stale, and failed counts;
- fatal errors separately from retryable or deferred work.

`catalog create`, `catalog migrate`, `catalog status`, and `health` accept no additional
arguments.

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

Folder commands treat `folder` as a folder tree by default. The given folder is
the default indexing scope root. Limits such as maximum file count, maximum byte
budget, maximum parse time, traversal depth, symlink behavior, include globs,
and exclude globs come from `config/parser.yaml`. Large jobs require explicit
override flags before they exceed configured safeguards.

## Redaction And Privacy Contract

The CLI has no personal source defaults. It never assumes private source roots,
taxonomies, or embedding providers. The only fixed path default is the required
home cache root `$HOME/.cache/agents-docs/`.

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
