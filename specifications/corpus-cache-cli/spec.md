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
- generic entity catalog management;
- command result files;
- health checks and diagnostics.

Private or upper workspaces own source policy, private Knowledge Markdown,
custom domain semantics, and user-specific workflows. The public engine owns the
standard entity catalog shape, but not the private data rows committed nowhere
in this repo.

## Workspace Storage Contract

Generated evidence state lives under `EVEN_CACHE`:

```text
<EVEN_CACHE>/
  catalog/
    catalog.sqlite
  blobs/
    <yyyy>/<mm>/<sha256_prefix>/<sha256>
  docling/
  fts/
    <fts_profile>/<scope_id>/
  semantic/
    <embedding_profile>/<scope_id>.lancedb/
  results/
    <yyyy>.<mm>/<dd>/<hhmmss>-<command>/
  reports/
    <yyyy>.<mm>/<dd>/<hhmmss>-<command>/
```

`EVEN_CACHE` is read from the current directory `.env` first, then the process
environment. When unset, it defaults to `.cache/` relative to the caller's
current directory. The scanner excludes `.cache/` so it never inventories its own
generated output.

Shared model downloads are not evidence state. They live under
`EVEN_HOME/models`; `EVEN_HOME` defaults to `~/.even`.

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
- image-embedding store registry rows;
- generic entities, aliases, evidence links, classifications, attributes,
  relationships, and review tasks.

The catalog does not store:

- command logs;
- generated chunk tables;
- text-index internal documents;
- vector-store internal rows;
- global representative FTS or semantic registry rows;
- private source maps and selected local/private paths;
- non-standard domain schemas that do not fit the generic entity catalog;
- private Knowledge Markdown.

Private repositories may open `catalog.sqlite` read-only. They reference catalog
rows through the Reference Contract below rather than copying lower rows. If
they need custom facts that do not fit the generic entity tables, those custom
rows stay above the engine.

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
  content is left as text; generic entity workflows may later bind structured
  subjects to evidence.
- Identity meaning — faces, people, named places, reviewed identity — belongs
  in the Layer 4 entity catalog when it fits the generic schema. Domain-specific
  meaning beyond that catalog stays in upper workspaces.

Media observations are stored in `media_observations` as generated, rebuildable
rows; they are never evidence of absence.

`index scope` indexes media text — captions, media-kind, and filenames — into
the same text and semantic projections as documents, so media is retrievable
through `search text`, `semantic`, and `hybrid`. Media hits reference
`corpus_cache.media_assets.<asset_id>`, document hits reference
`corpus_cache.document_objects.<object_id>`, per the Reference Contract.

## Search Contract

Indexes are rebuildable implementation details. Entity and Knowledge layers
should not know physical backend names or projection database layouts.

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
a separate retrieval mode, not a text search over generated captions. Image recall
is served directly by a single central image index — currently the logical union of
the current per-root image stores — and never routes through representatives,
because an image embedding is already a compact representation and an ANN index
scales over the whole corpus (see Modality asymmetry below).

`search text` may use global representative routing when a current derived
representative map exists. Routing searches the lossy `summary_nodes`
representatives, selects likely root scopes, then searches the root-scoped FTS
indexes that remain the evidence layer. When both representative routes are
current, the FTS-representative and semantic-representative hit lists are fused
with RRF before scope selection; the semantic route is optional by cost.
Representative routes only select scopes — for `search text` the deep search stays
FTS. If routing is unavailable or weak, `search text` falls back to all current
FTS indexes and records the fallback in `route_trace`. A query-time
`--budget low|mid|high` (default `mid`) governs fanout depth: `low` searches the
single best scope, `mid` searches the top routed scopes, and `high` adds recursive
deepening into matched roots plus a listing of the matched region. When deep
search returns no hits, the result falls back to the routing suggestions rather
than empty. The separate `list` command walks the representative hierarchy
directly with no query. Global representative stores are fixed-path derived
projections, not catalog registry rows. For media, `search text` stays FTS-first:
a text query reaches media only through its summarized text (album and root
summaries) in the FTS router, and the engine does not additionally fire a
cross-modal text-to-image-vector route, so each media region is surfaced once as
summarized text rather than twice. Image vectors are fused into the router only for
explicit cross-modal or entity probes that supply example images, per the Global
Representation Contract. `search text --image PATH` is that probe: the example
images are embedded with SigLIP, their visual route is fused (RRF, scope
granularity) with the text routes to select scopes, and image hits from the routed
scopes are returned alongside the text hits.

Search results hydrate back to catalog identities such as `source_item_id`,
`doc_id`, `object_id`, `scope_id`, and index/store registry IDs. Every hit also
carries a `ref` field holding its canonical evidence coordinate
`corpus_cache.document_objects.<object_id>` per the Reference Contract, so upper
layers can store the hit as a plain reference without copying lower rows. Result
payloads use public labels: `text`, `semantic`, and `hybrid`.

## Global Representation Contract

The global representative layer is a lossy routing map, not evidence. It is built
under an explicit per-root budget so that one large root cannot dominate the
global index, and so that a 10-file root and a 10,000-file root differ by
content, not by volume.

Representation unit. The global index is built only from `summary_nodes` rows
("representation units"). No lower row — chunk, asset, or object — is ever
projected directly into the global index.

Two layers, opposite contracts. Root-scoped FTS, semantic, and image indexes are
the proof layer: they are exhaustive and are never budget-limited or sampled. The
global representative layer is the routing layer: it is lossy and
budget-constrained. Only the routing layer is budgeted.

Modality asymmetry. The router-then-proof split is mandatory for text but not for
images, for a structural reason. Text proof is verbatim: exact-term matching cannot
survive compression, so the global text layer must be a separate lossy artifact
(summaries) and routing into the exhaustive per-root FTS is required. An image
embedding is already a compact lossy representation — there is no verbatim image
layer beneath it — and an ANN index scales sub-linearly over the whole corpus, so
image recall is served directly by a single central image index, not by routing.
`search image` therefore queries that central index (currently the logical union of
the current per-root image stores) directly and never routes through
representatives. Image medoids exist for a different purpose: they are an album's
visual fingerprint in the router — the visual parallel to a text summary — used
only to rank scopes for cross-modal and entity probes that combine text with
example images. A medoid is never a substitute for the central image index on a
pure visual query.

Media representatives. Each root-level `album_summary` contributes a text
fingerprint like any unit and, when image vectors exist, a small set of visual
fingerprints: `k` medoid assets chosen by k-means over the L2-normalized per-scope
image vectors (`k = clamp(ceil(sqrt(n / 2)), 1, EVEN_MEDIA_CLUSTER_K_MAX)`, default
ceiling `16`), reusing the proof-layer vectors rather than re-embedding. The chosen
medoid asset references are persisted on the `album_summary` unit (its `attrs`) so
the projection fetches their vectors without recomputation or clustering drift.
Medoids project into a separate SigLIP-space representative store, one per image
profile, never mixed with text vectors, and budgeted by their own `k` clamp
independent of the text `max_entries`. Visual and text fingerprints are fused only
for explicit cross-modal or entity probes, by RRF at scope granularity; selected
scopes are then proven exhaustively in the per-root FTS for text and the central
image index for images, and hits return as plain `media_assets` and
`document_objects` references so upper layers can attach evidence to an entity
without copying lower rows.

Representation budget. Each root's global representation is produced under a typed
budget envelope. Two dimensions are decisive; the rest are advisory for now and
derived from them:

- `max_build_seconds` — decisive cost budget: wall-clock build time per root,
  default `300` (5 minutes). Time is the primary cost limit; the builder stops
  adding companion units when it is reached.
- `max_entries` — decisive volume budget: representation-unit count on a
  logarithmic scale versus source size, floor `1` and ceiling `max_entries`
  (default `20`).
- `embedding_units`, `local_llm_tokens`, `remote_llm_tokens` — advisory and
  derived. Token and embedding budgets follow from `max_build_seconds` times a
  calibrated machine throughput (`tokens_per_sec`). `remote_llm_tokens` defaults
  to `0` (local-only). The text semantic representative store embeds each unit's
  derived `routing_payload` **fresh** with a selectable fast model — that text is
  not a proof chunk, so there is no vector to reuse. The marginal cost is low not
  through reuse but because the representative set is budget-bounded (a handful of
  units per root). Reuse of existing vectors applies only to the later SigLIP
  medoid route, where representatives are drawn from image vectors the proof layer
  already computed.

Dynamic configuration. `tokens_per_sec` is measured on first summarization,
cached, and self-corrected as builds run, so the time budget stays meaningful per
machine without manual tuning. Budgets are soft: exhausting a dimension stops
companion expansion; it never fails the build.

Mandatory floor. Whenever a root has any routable inputs, it produces at least one
`root_summary` unit, indexed into the mandatory FTS map. A single `root_summary`
is a valid, sufficient global representation; routing into the root's local
indexes can proceed on it alone. Companion units (folder, album, document, or
cluster summaries) are optional refinements added only while the budget allows.

Lossy by budget. Large sources are sampled, or fully embedded and then clustered
down to the entry budget. The loss is recorded per unit as
`coverage_estimate = sample_count / source_count`.

Importance. Every representation unit carries an importance signal in `[0, 1]`,
emitted as a structured side output of the summary call alongside `summary_text`.
There is no separate rationale field — the summary itself should make the
importance clear, and the prompt asks the model to surface the reason inside the
summary only for extreme cases. Importance drives hierarchical summarization: more
important sources receive more of the entry and time budget and finer
representation in the next layer; less important sources are compressed, clustered
together, or represented by a single low-detail companion or a `negative_summary`
unit (generalizing OP-015). Importance is advisory for routing only and never
suppresses evidence in the proof layer.

Importance priors. Deterministic priors seed importance before the model refines
it. A maintained low-importance prior list covers build, tooling, and system paths
such as `node_modules`, `.git`, `.venv`/`venv`, git-ignored paths, and OS folders
(for example `Program Files`). The prior list is dynamic: model importance
feedback can lower or skip entries over time, so a path the priors missed but the
model consistently rates low is demoted on later builds.

Selection precedence. When candidate units exceed `max_entries`, units are kept in
a deterministic order: the mandatory `root_summary` is always reserved, then
root-level `album_summary` units, then companion units ranked by importance
descending, then `coverage_estimate` descending, then `summary_id`. Overflow units
are dropped but counted in the manifest and `route_trace`, never silently;
low-importance overflow may be rolled up into a single `negative_summary` instead
of dropped.

Payload and backend parity. Each unit stores the model prose in `summary_text` and
the deterministic facets (paths, titles, headings, captions, safe metadata) as
structured `routing_meta`; the searchable/embeddable text is the derived
`routing_payload = summary_text + flattened routing_meta`, assembled at projection
time by one shared function. The FTS and semantic global projections are built from
the identical current unit set and index or embed that same `routing_payload`. FTS
is mandatory and built first; the semantic projection is optional and built second
over the same units. Neither backend may add, drop, or reweight units relative to
the other.

Versioned and deterministic. A `representation_policy_version` covers the budget,
importance, and precedence rules; the projection manifest watermark covers unit
identity, payload, and this policy version, so a policy change forces a rebuild.

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
| `index` | `routing <path>` | `path` | Build or refresh document/media summaries and the global representative FTS map. `--semantic` also builds the optional semantic representative store. |
| `list` | `[path]` | none | List the representative `summary_nodes` hierarchy (bypass; no query, no model). |
| `search` | `text <query>` | `query` | Search text projections. Accepts `--budget low\|mid\|high` (default `mid`) and `--image PATH` (repeatable): an explicit cross-modal probe that engages the SigLIP visual route and returns image hits from the routed scopes. |
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
Sources describe what was supplied.
Evidence describes what was observed or generated.
Indexes describe rebuildable retrieval projections.
Entities describe standard reviewed or proposed meaning.
Knowledge describes curated human context and non-standard semantics.
```

Public engine rows describe Sources, Evidence, Indexes, and generic Entities.
Private or upper rows/files describe Knowledge, custom domain semantics, and
workflow-specific curation.

## Non-Goals

- No private source paths or personal facts in public repo fixtures.
- No public-engine dependency on private Knowledge repositories or private Git
  state.
- No generated chunks in SQLite.
- No command logs in SQLite.
- No direct public access to text/vector projection internals.
- No topic-manager abstraction in this repo.
- No handoff/export packaging in V1.
