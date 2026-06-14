# Specification: Evidence Engine

## Purpose

Evidence Engine is the public reusable evidence engine for local document
and generic media workflows. The installable package and console script are
named `even`.

It owns:

- source inventory;
- Docling parsing orchestration;
- artifact/blob storage;
- current-state SQLite catalog control;
- normalized document objects;
- media-aware source inventory and generic media evidence (assets, typed
  metadata, generated observations, duplicate candidates);
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
.cache/even/
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

The `.cache/even/` root is resolved relative to the caller's current
directory, so the same convention serves the user home (`~/.cache/even/`) and a
project-local cache (`<folder>/.cache/even/`). The scanner excludes `.cache/`
so it never inventories its own generated output.

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
- lossy summary nodes used only for routing;
- text index registry rows;
- semantic store registry rows;
- media assets and typed image/video/3D metadata;
- media artifacts, generated observations, and duplicate candidates;
- image-embedding store registry rows.

The catalog does not store:

- command logs;
- generated chunk tables;
- text-index internal documents;
- vector-store internal rows;
- global representative FTS or semantic registry rows;
- private review decisions;
- private semantic facts;
- private knowledge.

Private repositories may open `catalog.sqlite` read-only. They reference
catalog rows through the Reference Contract below rather than copying lower
rows.

## Reference Contract

Any reference to an evidence row is a catalog coordinate. It reuses the same
`dataset.table.column` convention `catalog.yaml` already uses for foreign keys
(for example `ref: corpus_cache.document_objects.object_id`). The public
dataset is `corpus_cache`, so a reference to one row is:

```text
corpus_cache.<table>.<row_id>
```

Rules:

- A reference is just the target row id plus the `dataset.table.column` it
  points at. There is no separate `evidence_ref` object or nested payload.
- Upper catalogs reference lower rows by adding a column with
  `ref: corpus_cache.<table>.<column>`, identical to how the lower catalog
  declares its own foreign keys. The reference mechanism is the column `ref:`
  convention; nothing more is needed.
- "Kind", locator (page, bbox, time range, byte range), and provenance
  (producer, profile, source hash) are **columns on the referenced row**. They
  are resolved by reading the row, never copied into the reference.
- Cross-catalog references are expected and supported through the `dataset`
  prefix. An upper catalog is its own dataset and points at `corpus_cache.*`;
  the dependency direction stays one-way.
- References are not versioned. The catalog is current-state and migrates as a
  single monolith, so a reference always resolves to the current row. Referencing
  rows must not snapshot or copy lower-row data.

## Media Contract

Media is inventoried through the single `sources scan` path; there is no
`media scan`. Scan classifies items by `media_class` (image, video, audio,
model3d) alongside documents, including 3D model formats (`.obj`, `.stl`,
`.gltf`, `.glb`, `.ply`).

Each inventoried source item is routed to exactly one processor by media class:
documents and unknown types go to `docs parse`; image, video, audio, and 3D
items go to `media inspect`. Neither processor handles the other's types.

Media processors operate on already-inventoried items:

- `media inspect` extracts deterministic metadata into typed tables —
  `media_assets` plus `image_metadata`, `video_metadata`, or
  `model3d_metadata` — and stores thumbnails/previews through the shared blob
  store (`media_artifacts` referencing `artifact_blobs`). No model is involved.
- `media describe` generates shallow observations with a local laptop-tier VLM.
  It is off by default and profile-gated; defaults are decided only after the
  compute cost is benchmarked.
- `media dedupe` writes near-duplicate candidate pairs from perceptual hashing
  into `media_dedupe_candidates`. Candidates are for review, never decisions.

Generated media meaning has a deliberate ceiling:

- A shallow **`media_kind`** observation may classify an asset with a small,
  closed vocabulary (for example photo, screenshot, document_scan, diagram,
  chart, illustration, map, render). This is generic and useful for routing.
- A **caption** observation is general free text only. The engine does not
  produce a subject taxonomy (nature, animal, people, objects). Mixed-subject
  content is left as text; upper layers extract structured subjects from it.
- Identity meaning — faces, people, named places, reviewed identity — is never
  produced here. It belongs to private workspaces.

Media observations are stored in `media_observations` as generated, rebuildable
rows; they are never evidence of absence.

`index scope` indexes media text — captions, media-kind, and filenames — into
the same text and semantic projections as documents, so media is retrievable
through `search text`, `semantic`, and `hybrid`. Media hits reference
`corpus_cache.media_assets.<asset_id>`, document hits reference
`corpus_cache.document_objects.<object_id>`, per the Reference Contract.

## Search Contract

Search projections are rebuildable implementation details. Higher layers should
not know physical backend names or projection database layouts.

Public search commands are:

```text
even search text <query>
even search semantic <query>
even search hybrid <query>
even search image <image-path>
```

`text`, `semantic`, and `hybrid` take a text query. Media participates in them
through its indexed metadata and generated captions. `search image` is a
distinct query-by-example mode: it takes an image path, embeds it with the media
image-embedding model, and returns visually similar assets. Visual similarity is
a separate retrieval mode, not a text search over generated captions.

`search text` may use global representative routing when a current derived
representative FTS map exists. Routing first searches lossy `summary_nodes`,
selects likely root scopes, then searches the root-scoped FTS indexes that
remain the evidence layer. If routing is unavailable or weak, `search text`
falls back to all current FTS indexes and records the fallback in
`route_trace`. Global representative stores are fixed-path derived projections,
not catalog registry rows.

Search results hydrate back to catalog identities such as `source_item_id`,
`doc_id`, `object_id`, `scope_id`, and index/store registry IDs. Every hit also
carries a `ref` field holding its canonical evidence coordinate
`corpus_cache.document_objects.<object_id>` per the Reference Contract, so upper
layers can store the hit as a plain reference without copying lower rows. Result
payloads use public labels: `text`, `semantic`, and `hybrid`.

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
| `media` | `inspect <path>` | `path` | Extract deterministic media metadata into typed tables and store thumbnails. |
| `media` | `describe <path>` | `path` | Generate shallow VLM captions/kinds as observations. Off by default, profile-gated. |
| `media` | `dedupe <path>` | `path` | Write near-duplicate media candidate pairs from perceptual hashing. |
| `index` | `scope <path>` | `path` | Build or refresh the text index. |
| `index` | `scope <path> --semantic` | `path` | Build or refresh the semantic index. |
| `index` | `scope <path> --image` | `path` | Build or refresh the image-embedding store for media images. |
| `index` | `routing <path>` | `path` | Build or refresh document/media summaries and the global representative FTS map. |
| `search` | `text <query>` | `query` | Search text projections. |
| `search` | `semantic <query>` | `query` | Search semantic projections. |
| `search` | `hybrid <query>` | `query` | Fuse text and semantic candidates. |
| `search` | `image <image-path>` | `image-path` | Query-by-image visual similarity over media image embeddings. |

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
