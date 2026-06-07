# Specification: corpus-evidence-stack Evidence Engine

## Purpose

`corpus-evidence-stack` is the public reusable evidence engine for local document
and generic media workflows. The installable package and console script remain
`documents-manager`.

It owns:

- source inventory;
- Docling parsing orchestration;
- artifact/blob storage;
- current-state SQLite catalog control;
- normalized document objects;
- generic media evidence contracts planned for the next slice;
- text search index management;
- semantic search store management;
- hybrid search result hydration;
- command result files;
- health checks and diagnostics.

Private repositories own source policy, review decisions, private semantic
meaning, curated knowledge, and user-specific workflows.

## Workspace Storage Contract

Generated state lives under the caller workspace:

```text
.documents-manager/
  catalog/
    catalog.sqlite
  blobs/
    <yyyy>/<mm>/<sha256_prefix>/<sha256>
  docling/
  fts/
    <fts_profile>/<scope_id>/
  semantic/
    <embedding_profile>/<scope_id>.lancedb/
  models/
    fastembed/
  results/
    <yyyy>.<mm>/<dd>/<hhmmss>-<command>/
  reports/
    <yyyy>.<mm>/<dd>/<hhmmss>-<command>/
```

The old beta home-cache layout is not a compatibility target. During this
phase, catalog and index wipe/rebuild is acceptable.

## Catalog Contract

`catalog.yaml` defines the public SQLite schema contract for current state.

The catalog stores:

- source roots and source items;
- current source root and extension statistics;
- current documents;
- Docling artifact records;
- artifact blob records;
- normalized document object records;
- valuable item records;
- index scopes;
- text index registry rows;
- semantic store registry rows.

The catalog does not store:

- command logs;
- generated chunk tables;
- text-index internal documents;
- vector-store internal rows;
- private review decisions;
- private semantic facts;
- private knowledge.

Private repositories may open `catalog.sqlite` read-only. They should reference
catalog rows through stable IDs and evidence refs rather than copying lower
rows.

## Search Contract

Search projections are rebuildable implementation details. Higher layers should
not know physical backend names or projection database layouts.

Public search commands are:

```text
documents-manager search text <query>
documents-manager search semantic <query>
documents-manager search hybrid <query>
```

Search results hydrate back to catalog identities such as `source_item_id`,
`doc_id`, `object_id`, `scope_id`, and index/store registry IDs. Result payloads
use public labels: `text`, `semantic`, and `hybrid`.

## Command Contract

The CLI returns JSON on stdout. Commands that perform larger work also persist
result files under workspace-local `results/`.

Public commands:

| First command | Subcommand | Mandatory args | Purpose |
| --- | --- | --- | --- |
| `catalog` | `create` | none | Create the workspace catalog if missing. |
| `catalog` | `status` | none | Report catalog status and row counts. |
| `catalog` | `wipe` | none | Delete the workspace catalog database. |
| `health` | none | none | Check workspace paths and optional dependencies. |
| `sources` | `scan <path>` | `path` | Inventory a mixed-content source folder. |
| `docs` | `parse <path>` | `path` | Parse documents and write lower evidence rows. |
| `index` | `scope <path>` | `path` | Build or refresh the text index. |
| `index` | `scope <path> --semantic` | `path` | Build or refresh the semantic index. |
| `search` | `text <query>` | `query` | Search text projections. |
| `search` | `semantic <query>` | `query` | Search semantic projections. |
| `search` | `hybrid <query>` | `query` | Fuse text and semantic candidates. |

There is no `manage` command group and no V1 `handoff` command group.

## Future Transport Note

A future long-lived stdio surface may be useful for high-volume callers, but it
is not an MCP-compatible commitment. It should be MCP-inspired at most and use
the same JSON schemas as the CLI.

For now, default operation is CLI arguments plus persisted files. Any future
`--input <json-file>` command shape should be planned separately.

## Layer Rule

Use this rule everywhere:

```text
Lower schemas describe what was observed and generated.
Upper schemas describe what was believed, reviewed, promoted, or used.
```

Public engine rows describe source evidence, generated observations, and
rebuildable projections. Private rows describe reviewed meaning and durable
knowledge.

## Non-Goals

- No private source paths or personal facts in public repo fixtures.
- No public-engine dependency on private catalogs.
- No generated chunks in SQLite.
- No command logs in SQLite.
- No direct public access to text/vector projection internals.
- No topic-manager abstraction in this repo.
- No handoff/export packaging in V1.
- No global routing implementation in this packet; that remains a separate
  plan.
