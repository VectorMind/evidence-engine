# Plan: Global Routing Indexes

Date: 2026-06-14
Status: D0 and D1 implemented. Document root summaries, media album summaries,
and the global representative FTS route map are in place.

## Problem Summary

The hand-in proposes a multi-resolution search architecture:

- SQLite remains the durable current-state catalog.
- Full FTS, semantic, and image indexes remain scoped by root/scope and act as
  the proof layer.
- A lightweight global representative layer routes broad queries to likely
  roots/scopes before the search dives into deep root-scoped indexes.
- Lossy summaries are used only as routing hints. They are never proof.

The current repo already has catalog creation, source inventory, document parse,
media inspect/describe, root-scoped FTS, semantic search, hybrid RRF search, and
image search. This plan adds the missing routing map without exposing lower
index internals or storing generated chunk/vector rows in SQLite.

## Resolution Summary

- `summary_nodes` is the only new SQLite table. It stores current-state
  representative metadata and routing text, not vectors and not generated chunk
  rows.
- Global representative FTS/semantic stores are derived projections at fixed
  cache paths. They are not catalog-registered and do not add registry tables.
- D0 built document-only root summaries and a global representative FTS
  projection. D1 adds root-level media `album_summary` rows from existing media
  catalog facts.
- `even index routing <path>` is the explicit build command, so normal
  `index scope` behavior does not become model-bound.
- `search text` uses routed search when a current global representative FTS
  projection exists. If the projection is missing, stale, weak, or empty, it
  falls back to the existing all-current-FTS behavior and records that status.
- Cross-route candidate merging remains rank-based. The implemented path has
  one global route
  (representative FTS); later text-vector and SigLIP routes merge by RRF.
- Raw per-route scores stay visible in the route trace. Scores from different
  spaces are never treated as calibrated.

## Implemented Goal And Objectives

Goal: route broad text queries to likely document and media roots/scopes before
searching root-scoped FTS indexes, while preserving the existing search contract
and fallback behavior.

Objectives:

- add `summary_nodes` to `catalog.yaml` and bump catalog schema/user versions;
- add a representative FTS row template and fixed global FTS cache path;
- build one current `root_summary` row per active root scope from parsed
  document chunks when document chunks exist;
- build one current `album_summary` row per active root scope from existing
  media assets, inspect metadata, captions, media-kind labels, and filenames
  when media catalog facts exist;
- write local-LLM summaries from bounded sampled chunks/assets, with
  deterministic facets concatenated into `routing_text`;
- build the derived global representative FTS projection from current
  `summary_nodes`;
- make `search text` route through the global representative FTS when available,
  then search selected root-scoped FTS indexes;
- record route trace, selected scopes, widening/fallback status, and hydrated
  evidence refs in result JSON.

## Implemented Scope

In scope:

- document routing from `document_objects` through existing `chunks_for_root`;
- media routing from `media_assets`, typed metadata tables, and
  `media_observations`;
- `root_summary` and root-level `album_summary` rows, one per active root scope
  when each input family exists;
- global representative FTS only;
- local Ollama summary generation using configured localhost settings;
- deterministic rebuild watermarks and stale/deferred status;
- route trace and fallback-all-current-FTS behavior;
- tests with a fake summary generator, so CI does not require Ollama.

Non-goals:

- `media_cluster_summary` generation;
- global semantic representative stores;
- SigLIP representative routing;
- OCR, object detection, labels, audio transcript, or video keyframe pipelines;
- query usage tracking or persisted raw query text;
- auto-created child scopes;
- materialized collection indexes;
- replacing root-scoped FTS as the evidence/proof layer.

## Implementation Phases

### Phase 1: Schema And Contract

Deliverables:

- add `summary_nodes` to `catalog.yaml` after `index_scopes`;
- bump `catalog.yaml` `spec_version`, `CATALOG_SCHEMA_VERSION`, and
  `CATALOG_USER_VERSION`;
- document that beta catalogs require wipe/rebuild on this schema bump, matching
  the existing reset-required behavior;
- add `fts_summary_node` to `store_templates.yaml`;
- add fixed cache paths to `config/exposures.yaml`;
- add routing defaults to a single config reference, preferably
  `config/routing.yaml` plus `config/README.md`;
- update `specifications/corpus-cache-cli/spec.md` if the new table and routed
  search behavior become public contract in the same implementation pass.

Exit:

- `load_catalog_tables()` sees `summary_nodes`;
- `catalog create` creates the new table and indexes on a clean workspace;
- stale beta catalogs report reset-required rather than silently migrating;
- no generated chunk rows or vectors are added to SQLite.

### Phase 2: Document Summary Builder

Deliverables:

- add a summary builder module, expected shape `src/even/routing.py` or
  `src/even/summaries.py`;
- add `even index routing <path> [--force] [--limit]`;
- auto-run catalog ensure and source scan for the requested path, following the
  existing `index scope` pattern;
- use `chunks_for_root` for document summary inputs and existing media catalog
  rows for media summary inputs;
- sample bounded document chunks with policy `text_stratified_v1`;
- call a local Ollama text-generation endpoint using
  `EVEN_SUMMARY_MODEL` / `EVEN_SUMMARY_OLLAMA_URL` defaults;
- concatenate deterministic facets into `routing_text`: root label, relative
  paths, document titles, headings, object types, filenames, captions,
  media-kind labels, safe media metadata, and the LLM `summary_text`;
- upsert current `summary_nodes` rows and mark affected stale/deferred/failed
  rows predictably.

Exit:

- a parsed fixture root can produce one current `root_summary`;
- a media fixture root can produce one current `album_summary`;
- an unparsed root returns `deferred` with `no_summary_inputs`;
- unavailable Ollama returns `deferred` and does not create a current routing
  projection from deterministic facets alone;
- summary rows include inspectable source refs, coverage, producer/profile,
  source watermark, and status.

### Phase 3: Global Representative FTS

Deliverables:

- build `fts/global_representatives/{fts_profile}/` from current
  `summary_nodes` with non-empty `routing_text`;
- write a sidecar manifest next to the FTS store, not a catalog registry row;
- include manifest fields: `built_at`, `fts_profile`, `template_name`,
  `summary_watermark`, `row_count`, and `schema_version`;
- skip no-op rebuilds when the manifest watermark matches current rows unless
  `--force` is set.

Exit:

- a global representative FTS search can return likely `summary_id`, `root_id`,
  and `scope_id` values;
- missing or stale sidecars are reported as route-unavailable, never silently
  treated as current;
- no `fts_indexes` row is created for the global representative projection.

### Phase 4: Routed Search

Deliverables:

- update `search_text_indexes` or add a routed wrapper used by `search text`;
- search global representative FTS first when it is current;
- select unique `scope_id` values from representative hits, default max `4`;
- search only selected current root-scoped FTS indexes first;
- widen by increasing representative top-k, then fall back to all current FTS
  indexes if hit count, score gap, or hydration checks are weak;
- preserve current all-current-FTS behavior when routing is unavailable.

Current default thresholds:

| Setting | Default |
| --- | --- |
| Representative top-k | `12` |
| Max routed scopes | `4` |
| Minimum hydrated deep hits | `3` |
| Minimum representative score gap | `0.10` |
| Fallback candidate limit | existing `--limit` behavior |

Exit:

- `search text` returns the same top-level JSON shape plus `route_trace`;
- route-selected searches avoid blind fanout when confident;
- weak routing falls back to all current FTS indexes;
- no raw query text is persisted in SQLite.

### Phase 5: Tests And Proof

Deliverables:

- schema/table loader test for `summary_nodes`;
- catalog create/status test proving the user-version bump;
- summary builder unit test using fake chunks and fake local LLM output;
- global representative FTS build/search test with a small multi-root fixture;
- routed search test proving selected-scope search and fallback-all behavior;
- regression test that document summary prompts remain document-only while
  media summaries use media catalog inputs;
- media summary and media-routed text search tests;
- route trace shape test.

Exit:

- `uv run pytest` passes for the targeted tests or the whole suite;
- `test.md` records commands, fixtures, expected results, actual results, and
  any dependency skips.

## `summary_nodes` Catalog Proposal

Add one current-state table. Place it after `index_scopes` because it summarizes
catalog scopes and is a source for derived search projections.

```yaml
- name: summary_nodes
  description: Current lossy representative nodes used only for routing.
  exposures: [sqlite]
  columns:
    - {name: summary_id, type: text, description: "Stable summary node ID."}
    - {name: root_id, type: text, description: "Summarized source root.", ref: corpus_cache.source_roots.root_id}
    - {name: scope_id, type: text, description: "Summarized index scope.", ref: corpus_cache.index_scopes.scope_id}
    - {name: parent_summary_id, type: text, description: "Parent summary node when a hierarchy exists.", ref: corpus_cache.summary_nodes.summary_id}
    - {name: source_item_id, type: text, description: "Folder, file, or container item summarized when applicable.", ref: corpus_cache.source_items.source_item_id}
    - {name: doc_id, type: text, description: "Document summarized when applicable.", ref: corpus_cache.documents.doc_id}
    - {name: kind, type: enum, description: "Representative kind.", values: [root_summary, folder_summary, document_summary, album_summary, media_cluster_summary, negative_summary]}
    - {name: modality, type: enum, description: "Dominant modality represented.", values: [text, image, video, audio, model3d, mixed]}
    - {name: media_kind, type: text, description: "Closed media-kind label when applicable."}
    - {name: container_kind, type: enum, description: "Container shape when applicable.", values: [none, root, folder, document, item, cluster]}
    - {name: summary_level, type: integer, description: "Routing level, with 0 for root-level representatives."}
    - {name: title, type: text, description: "Short display title for the representative."}
    - {name: summary_text, type: text, description: "Local lossy LLM summary of sampled inputs."}
    - {name: routing_meta, type: json, description: "Structured deterministic routing facets; the searchable/embeddable payload is derived at projection time from summary_text plus these facets (RP1)."}
    - {name: source_refs_json, type: json, description: "Canonical refs sampled or represented by this node."}
    - {name: source_count, type: integer, description: "Total lower items considered for this representative."}
    - {name: sample_count, type: integer, description: "Lower items sampled into the summary prompt."}
    - {name: coverage_estimate, type: real, description: "sample_count divided by source_count when known."}
    - {name: sample_policy, type: text, description: "Sampling policy name, e.g. text_stratified_v1 or siglip_kmeans_medoids."}
    - {name: producer, type: text, description: "Producer implementation or local model family."}
    - {name: profile, type: text, description: "Summary/profile configuration used."}
    - {name: source_high_watermark, type: text, description: "Hash of source inputs, config, and producer profile."}
    - {name: summary_status, type: enum, description: "Current summary state.", values: [current, stale, deferred, failed, deleted]}
    - {name: confidence, type: real, description: "Optional producer confidence or quality estimate."}
    - {name: attrs_json, type: json, description: "Additional routing metadata and diagnostics."}
    - {name: created_at, type: timestamp, description: "UTC timestamp when first generated."}
    - {name: updated_at, type: timestamp, description: "UTC timestamp when last refreshed."}
  indexes:
    - name: pk_summary_nodes
      columns: [summary_id]
      unique: true
    - name: idx_summary_nodes_root_kind
      columns: [root_id, kind]
    - name: idx_summary_nodes_scope_kind
      columns: [scope_id, kind]
    - name: idx_summary_nodes_parent
      columns: [parent_summary_id]
    - name: idx_summary_nodes_status
      columns: [summary_status]
```

Notes:

- `source_refs_json` stores canonical refs such as
  `corpus_cache.document_objects.<object_id>` and
  `corpus_cache.media_assets.<asset_id>`. This is more precise than raw ID JSON
  because the same column can represent document objects, media assets, or
  mixed future source types without inventing a new addressing scheme.
- Document summaries write `kind=root_summary`, `modality=text`,
  `container_kind=root`, and `summary_level=0`.
- Media summaries write `kind=album_summary`, `container_kind=root`,
  `summary_level=0`, a dominant `modality` (`image`, `video`, `audio`,
  `model3d`, or `mixed`), and a dominant `media_kind` when available.
- `summary_text` is the LLM-written lossy summary; `routing_meta` holds the
  deterministic facets as structured json. The indexed/embedded `routing_payload`
  is derived from both at projection time (RP1), so facets participate in routing
  without pretending they are the model's summary, and the summary is not stored
  twice.
- Vectors never enter this table.

## Representative Store Templates And Paths

Add `fts_summary_node` to `store_templates.yaml`:

```yaml
- name: fts_summary_node
  backend: fts
  description: One generated FTS document per current summary node.
  columns:
    - {name: summary_id, type: text, description: "Catalog summary node ID."}
    - {name: root_id, type: text, description: "Summarized source root."}
    - {name: scope_id, type: text, description: "Summarized index scope."}
    - {name: kind, type: enum, description: "Summary node kind."}
    - {name: modality, type: enum, description: "Dominant modality."}
    - {name: title, type: text, description: "Display title."}
    - {name: summary_text, type: text, description: "Lossy summary text."}
    - {name: routing_payload, type: text, description: "Primary searchable payload derived from summary_text + routing_meta (RP1)."}
    - {name: source_refs_json, type: json, description: "Represented lower evidence refs."}
    - {name: metadata_json, type: json, description: "Compact route metadata."}
```

Add fixed derived paths to `config/exposures.yaml`:

```yaml
- name: global_representative_fts
  exposure: fts
  path_template: "fts/global_representatives/{fts_profile}/"
  description: Derived global FTS map over current summary_nodes. Not catalog-registered.
- name: global_representative_semantic
  exposure: semantic
  path_template: "semantic/global_representatives/{embedding_profile}.lancedb/"
  description: Future derived semantic map over current summary_nodes. Not catalog-registered.
- name: global_representative_siglip
  exposure: semantic
  path_template: "semantic/global_representatives/siglip/{image_profile}.lancedb/"
  description: Future derived SigLIP map over summary medoid asset refs. Not catalog-registered.
```

Only `global_representative_fts` is implemented. Semantic and SigLIP
representative projections remain future work.

## Decisions

Status: all items below are decided. No item blocks the implemented D0/D1 path.

### Foundational

| ID | Point | Decision | Confidence |
| --- | --- | --- | --- |
| F1 | Does `summary_nodes` go in SQLite? | Yes, current-state representative metadata only. No history, no chunk rows, no vectors. | High |
| F2 | Does the global representative index need catalog registration? | No. The only catalog addition is `summary_nodes`; global stores are derived fixed-path projections with sidecar manifests. | High |
| F3 | How are lossy summaries generated? | Sample bounded representative chunks/images, feed only those to a local Ollama model, then concatenate deterministic facets into `routing_text`. No remote model by default. | High |
| F4 | How are cross-index scores handled? | Do not calibrate scores across indexes or embedding spaces. Merge cross-route candidates with RRF; keep raw per-route scores in trace. | High |
| D0/D1 | Sequencing | Ship document-only root-summary routing first, then add root-level media album summaries from existing media catalog facts. | High |
| F5 | Is the global index per-root volume-budgeted? | Yes. The routing layer is built under a typed per-root budget envelope; the proof layer stays exhaustive and unbudgeted. | High |
| F6 | Does representation carry importance? | Yes. Every unit carries an importance signal in `[0, 1]` that drives hierarchical summarization; less important sources surface less in the next layer. | High |

### Global Representation Budget And Importance (O1)

Resolves open point O1 (implicit per-root budget). The global representative
layer must not let one large root flood the index; representation volume is a
function of the budget, not the file count. Hardened in the spec's
`Global Representation Contract`.

| ID | Point | Decision | Confidence |
| --- | --- | --- | --- |
| B1 | Budget shape | A typed per-root envelope, not a single count. Two decisive dimensions — `max_build_seconds` (cost) and `max_entries` (volume) — plus advisory/derived `embedding_units`, `local_llm_tokens`, `remote_llm_tokens`. | High |
| B2 | Entry ceiling | `1 ≤ entries(root) ≤ max_entries`, log-scaled vs source size. Default `max_entries = 20`; proposed curve `clamp(round(1 + 2·log10(source_items)), 1, max_entries)`. | High |
| B3 | Mandatory floor | At least one `root_summary` when inputs exist; it alone is a sufficient global representation. Companions are optional refinements added only while budget allows. | High |
| B4 | Embedding budget (corrected by DP1) | Explicit `embedding_units` dimension; model selectable, default fast. Text reps embed the derived `routing_payload` **fresh** — that text is not a proof chunk, so there is no vector to reuse. Marginal cost is low because the representative set is budget-bounded, not via reuse. Vector reuse applies only to the SigLIP medoid route. | High |
| B5 | Remote spend | `remote_llm_tokens` default `0` (local-only), matching existing policy. | High |
| B6 | Soft budgets | Budgets are soft and configurable: exhausting a dimension stops adding companions; it does not fail the build. | High |
| B7 | Lossy by budget | Large sources are sampled, or fully embedded then clustered down to the entry budget; loss recorded as `coverage_estimate`. | High |
| B8 | Importance | Per-unit importance in `[0, 1]`, emitted as a structured side output of the summary call alongside `summary_text` (no separate rationale field; the prompt surfaces the reason inside the summary only for extreme cases). Allocates entry/time budget and next-layer detail; advisory only, never suppresses proof. Generalizes OP-015 `negative_summary`. | Med-High |
| B9 | Layer scope | Budget and lossiness apply to the routing layer only. Root-scoped FTS/semantic/image stay exhaustive. | High |
| B10 | Versioning | `representation_policy_version` covers budget/importance/precedence; projection manifest watermark covers it so policy changes force a rebuild. | High |
| B11 | Time-primary budget (O3) | Wall-clock `max_build_seconds` per root, default `300` (5 min), is the primary cost limit. Token/embedding budgets derive from `max_build_seconds × tokens_per_sec`; `tokens_per_sec` is measured-and-cached on first summarization and self-corrected. | High |
| B12 | Selection precedence (O5) | When candidates exceed `max_entries`: reserve `root_summary`, then `album_summary`, then companions by importance desc → `coverage_estimate` desc → `summary_id`. Overflow is dropped but counted in manifest/`route_trace`; low-importance overflow may roll up into one `negative_summary`. | High |
| B13 | Importance priors (O7) | A deterministic low-importance prior list (`node_modules`, `.git`, `.venv`/`venv`, git-ignored paths, OS folders such as `Program Files`) seeds importance; the list is dynamic and is demoted/extended from model importance feedback over time. | Med-High |
| B14 | Importance source (O7) | Importance comes from the summarization side output, reusing the existing model call. The media `media_kind` describe step is the existing classifier; a general per-document classifier is a future option. | Med-High |
| RP1 | Payload model | Store model prose in `summary_text` and structured facets in `routing_meta` (json); the searchable/embeddable `routing_payload = summary_text + flattened routing_meta` is derived at projection time by one shared function (so FTS and the future semantic store consume the identical payload). Replaces the flat `routing_text` blob, removing the summary-stored-twice redundancy. Catalog bumped `0.8`/`8` → `0.9`/`9`. | High |

Implemented (steps 1–6, 2026-06-26 — D0 representation contract closed): the `real`
`summary_nodes.importance` column (catalog `0.8`/`8`); importance as a structured
summary side output with deterministic prior fallback and dynamic learned-prior
feedback; `representation_policy_version` in the global FTS watermark/manifest;
projection-time per-root budget enforcement (`_select_budgeted_rows`/`_entry_budget`)
with reserved L0 units, importance precedence, overflow counting, the identical
trimmed unit set feeding FTS and the staleness watermark, and `negative_summary`
overflow rollup; the decisive `max_build_seconds` time budget (skips companions,
keeps the mandatory root_summary) with measure-and-cache `tokens_per_sec`
calibration and a derived advisory token budget; the O6 sampling-policy rename
`text_stratified_v1` → `doc_roundrobin_v1`; and RP1 — the `routing_meta` (json) +
projection-time `routing_payload` model replacing the flat `routing_text` blob
(catalog `0.9`/`9`).

DP1 (resolved): the D2 text semantic representative store embeds `routing_payload`
**fresh** with a fast text model; "reuse existing vectors" is a SigLIP-medoid-only
concept. This corrects B4. The derived embedding budget itself and the FTS/semantic
parity it exercises still land with the D2 semantic projection.

### Schema / Registry

| ID | Point | Decision | Confidence |
| --- | --- | --- | --- |
| S1 | Summary node kinds | Use `root_summary`, `folder_summary`, `document_summary`, `album_summary`, `media_cluster_summary`, `negative_summary`, plus `modality` and `media_kind`. | High |
| S2 | Representative rows vs chunk rows | Use a separate representative FTS template. Representative rows carry provenance, coverage, and confidence, not chunk evidence fields. | High |
| S3 | Global semantic split by space | One derived global representative store per embedding/image profile. Never mix text vectors and SigLIP vectors. | High |
| S4 | EXIF/GPS in global reps | Exclude EXIF location by default. Include only behind explicit opt-in policy. | High |
| S5 | Image containers | Treat media-bearing documents like folders of images. Distinguish provenance with `container_kind`; route them identically. | High |

### Media-Specific Follow-On Decisions

| ID | Point | Decision | Confidence |
| --- | --- | --- | --- |
| M1 | Clustering method | k-means on L2-normalized SigLIP vectors; medoid = nearest centroid; `k = clamp(ceil(sqrt(n/2)), 1, 16)`. | Medium |
| M2 | L0 media root rep | Use both centroid and medoids: centroid for recall, medoids for exemplars. | Med-High |
| M3 | Routing-text assembly | LLM summary plus deterministic facets; defer a second rollup-LLM pass. | High |
| M4 | OCR over media images | Plan behind `EVEN_MEDIA_OCR=1`, disabled by default. | High |
| M5 | Media staleness | Use a media-summary watermark that includes caption/OCR state. | Medium |
| M6 | Video/audio | V1 scans metadata only. Transcript/keyframe parsing is deferred. | High |
| M7 | Missing facets | Renormalize sampling across available strata and record skipped widening rungs as `facet_unavailable`. | High |

### Carried Decisions From The OP Registry

| ID | Decision |
| --- | --- |
| OP-007 | Defer explicit `search text` scope flags until routed search proves a need. |
| OP-013 | Do not persist raw query text in SQLite. Aggregate route counters remain a later decision. |
| OP-014 | Scope suggestions are review output only; never auto-create scopes. |
| OP-015 | Default excludes remain excluded; use `negative_summary` only for included-but-low-value folders. |
| OP-016 | Archives route by manifest-level representative first; deep unpack/index only on opt-in or strong manifest hit. |
| OP-017 | Widening is based on hit count, representative score gap, and hydrated-evidence availability. Current defaults are listed above. |
| OP-020 | Materialized collection indexes require explicit manual promotion; not V1 and never automatic. |

## Decision Traceability

| OP | Resolved by |
| --- | --- |
| OP-001 | F1 |
| OP-002 | S1 |
| OP-003 | F2: no catalog registry row for global representative indexes |
| OP-004 | F2: no synthetic root is needed |
| OP-005 | F2 and fixed cache paths |
| OP-006 | S2 |
| OP-007 | Carried decision table |
| OP-008 | Global representative FTS routes to root-scoped FTS |
| OP-009 | V1 ordering: text-to-media stays FTS-first; image-to-media gets SigLIP representative routing in the media slice |
| OP-010 | F3: local LLM summary generation is intrinsic |
| OP-011 | F3, S4, and local-only model policy |
| OP-012 | S2 and `summary_nodes` provenance/coverage/confidence fields |
| OP-013 | Carried decision table |
| OP-014 | Carried decision table |
| OP-015 | Carried decision table |
| OP-016 | Carried decision table |
| OP-017 | Carried decision table and current thresholds |
| OP-018 | F4 |
| OP-019 | F4 and route trace |
| OP-020 | Carried decision table |

## D2: Global Semantic Representative Store

The next slice adds a text-vector representative route alongside the FTS route,
over the identical budgeted unit set. Decisions:

| ID | Point | Decision | Confidence |
| --- | --- | --- | --- |
| DP1 | Embedding source | Embed each unit's derived `routing_payload` **fresh** with the existing fast text embedding profile. It is not a proof chunk, so there is no vector to reuse; cost is low because the unit set is budget-bounded. Reuse is reserved for the SigLIP medoid route. Corrects B4. | High |
| DP2 | Store template | Add `semantic_summary_node` to `store_templates.yaml` (vector + `routing_payload` + provenance), built at `semantic/global_representatives/{embedding_profile}.lancedb/`. | High |
| DP3 | `embedding_units` mechanics | One embedding unit = one selected `summary_node` = one embedded `routing_payload`. Count is bounded by the per-root entry budget; embed all selected units. The dimension stays informational. | High |
| DP4 | Multi-route fusion | Run FTS-rep always and semantic-rep when its store is current; **always fuse** the two representative hit lists with RRF (uniform weights, `k=60`, reuse `hybrid._fuse_hits`); select scopes from the fused ranking. Semantic is optional by cost. Representative routes only select scopes; for `search text` deep search stays FTS. | High |
| DP5 | Manifest + parity | Semantic manifest carries `embedding_profile`, `representation_policy_version`, `summary_watermark`, `row_count`. A parity test asserts the FTS and semantic projections are built from the identical selected unit set. | High |

`route_trace` generalizes from a single `mode` to a `routes` list (one entry per
representative route) plus a `fused_selection` block; see the contract section.

Implemented (2026-06-26): DP1–DP5 are built. `build_global_representative_semantic`
embeds `routing_payload` fresh into `semantic/global_representatives/{profile}.lancedb/`
over the same budgeted unit set; `search_text_with_routing` fuses the FTS and
semantic representative routes with RRF and emits the multi-route trace; semantic
build is opt-in via `index routing --semantic`. Tests cover the RRF fusion and the
FTS/semantic parity count. The single-route trace shape is preserved when only the
FTS route is current.

## Retrieval Strategy / Auto Mode

A query-planning layer above the routes. Simple v1, expected to mature with real
usage. Two CLI surfaces:

- `list [path]` — bypass: walk the `summary_nodes` hierarchy
  (`summary_level`/`parent_summary_id`) and print roots → their summaries. No
  query, no model. Structural overview of the knowledge base.
- `search <query> [--budget low|mid|high]` (default `mid`) — the planner.

Query-time budget ladder (distinct from the build-time `max_build_seconds`):

| Budget | Behavior |
| --- | --- |
| low | Route (fused) → single best scope → deep search → hits. Minimal fanout. |
| mid (default) | Route → top-k scopes → deep search → fused hits, weak→fallback-all. Current behavior. |
| high | mid + recursive deepening into matched roots' lower summaries + a listing of the matched region. |

Cross-budget rule: when deep search returns no hits, fall back to the routing
result (relevant roots/summaries as suggestions) rather than empty.

Notes:

- `high` recursion needs lower summary nodes (folder/cluster companions, D2+); it
  degrades gracefully to "mid + listing" until those exist.
- Query budget is a separate concept from the representation build budget.
- First implementation: `list` (reads `summary_nodes` only) and the `--budget`
  knob with `mid` mapped to current routed behavior; `low`/`high` are increments.

## Current Implementation Anchors

- `src/even/chunks.py`: document summary inputs come from `chunks_for_root`;
  media proof chunks still come from `media_chunks_for_root` in scoped FTS.
- `src/even/fts.py`: routing can reuse Tantivy schema/build/search patterns but must
  not register the global representative index in `fts_indexes`.
- `src/even/hybrid.py`: existing RRF implementation is the model for later
  cross-route fusion.
- `src/even/ollama.py`: local-only Ollama access pattern.
- `src/even/references.py`: canonical refs are
  `corpus_cache.<table>.<row_id>`.
- `catalog.yaml`: schema and SQLite user-version source.
- `store_templates.yaml`: generated projection row templates.
- `config/exposures.yaml`: fixed generated storage paths.

## Search And Route Trace Contract

Routed `search text` adds `route_trace` when routing is attempted.
Existing top-level hit fields remain stable.

Single-route (current) shape — still emitted when only the FTS route is current:

```json
{
  "route_trace": {
    "mode": "global_representative_fts",
    "status": "used",
    "representative_index_uri": "fts/global_representatives/text_default_en",
    "representative_hits": [
      {"rank": 1, "score": 3.42, "summary_id": "sum_...", "root_id": "root_...",
       "scope_id": "scope_...", "kind": "root_summary", "title": "Example root"}
    ],
    "selected_scopes": [
      {"scope_id": "scope_...", "reason": "representative_hit", "rank": 1}
    ],
    "deep_searches": [
      {"scope_id": "scope_...", "fts_index_id": "fts_...", "status": "ok", "hits_returned": 4}
    ],
    "widening_status": {"status": "not_needed", "reasons": [], "skipped_rungs": []}
  }
}
```

Multi-route shape (D2 — DP4) — `mode` generalizes to a `routes` list plus a
`fused_selection` block:

```json
{
  "route_trace": {
    "budget": "mid",
    "routes": [
      {"mode": "global_representative_fts", "status": "used", "hits": [/* rep hits */]},
      {"mode": "global_representative_semantic", "status": "used", "hits": [/* rep hits */]}
    ],
    "fused_selection": [
      {"scope_id": "scope_...", "rrf_score": 0.031, "contributing_modes": ["fts", "semantic"], "rank": 1}
    ],
    "deep_searches": [
      {"scope_id": "scope_...", "fts_index_id": "fts_...", "status": "ok", "hits_returned": 4}
    ],
    "widening_status": {"status": "not_needed", "reasons": [], "skipped_rungs": []}
  }
}
```

If routing is unavailable, use:

```json
{
  "route_trace": {
    "mode": "fallback_all_current_fts",
    "status": "routing_unavailable",
    "reasons": ["global_representative_index_missing"],
    "widening_status": {"status": "fallback_all_scopes"}
  }
}
```

## Media Mapping

Media follows the same shape as document routing, one level up. D1 implements
the text-routable part of this shape; visual vector routing remains future work.

| Text world | Media world |
| --- | --- |
| chunk text plus text embedding | image/media metadata plus future SigLIP vector |
| document made of chunks | image container made of media assets |
| sampled chunks summarized into text | sampled media assets summarized into routing text |
| document/root summary routes to deep FTS | album/container summary routes to per-scope media text evidence |

An image container can be a folder/album, a media-bearing document, or the media
inside a folder. D1 implements root-level albums only. A single important image
is the n=1 case: its filename, observations, metadata, and routing text become
the representative.

Routing text for media is a fusion of available facets:

```text
path tokens
filename tokens
caption text          existing media_observations facet
generated album summary
OCR text              future facet
generated cluster summary future facet
detected labels       future facet
selected metadata     media_kind, capture date, duration, etc.
```

D1 consumes only existing media observations; it does not invoke OCR, object
detection, video keyframes, audio transcription, or SigLIP representative
routing. Facets disabled or unavailable under current config are skipped
deterministically and recorded in sampling/widening metadata.

## Privacy And Policy

- Visual media representatives have a higher privacy surface than text. EXIF
  GPS, OCR, captions, labels, and route traces can expose sensitive data.
- `EVEN_GLOBAL_INCLUDE_EXIF_LOCATION` defaults to off.
- Captions and summaries stay local-only. Remote model policy is out of scope
  for the minimal laptop setup.
- Raw query text is never persisted in SQLite.
- Summary text and route traces must avoid copying full source content; they are
  routing hints and diagnostics, not evidence.

## Configuration

All new flags use the `EVEN_` prefix. Implementation should document these in
`config/README.md` and keep non-env defaults in one routing config file.

| Flag / setting | Type | Default | Controls |
| --- | --- | --- | --- |
| `EVEN_SUMMARY_MODEL` | env/config | existing `DEFAULT_MODEL` | Local Ollama model for lossy summaries. |
| `EVEN_SUMMARY_OLLAMA_URL` | env/config | existing `DEFAULT_URL` | Local Ollama endpoint for summary generation. |
| `EVEN_MEDIA_OCR` | env bool | `0` | Future media OCR facet. |
| `EVEN_MEDIA_CLUSTER_K_MAX` | config | `16` | Future media medoid clamp. |
| `representation_budget.max_build_seconds` | config (dynamic) | `300` | **Primary** cost budget: wall-clock build time per root. |
| `representation_budget.max_entries` | config | `20` | **Volume** ceiling per root (log-scaled vs source size). |
| `representation_budget.tokens_per_sec` | calibrated | measured + cached | Machine throughput; derives token/embedding budgets from time. |
| `representation_budget.embedding_units` | derived | reuse proof-layer vectors | Items embedded for routing; model selectable, default fast. |
| `representation_budget.local_llm_tokens` | derived | from time × throughput | Local summarization token budget (advisory). |
| `representation_budget.remote_llm_tokens` | config | `0` | Remote summarization token budget (local-only default). |
| `importance_priors` | config (dynamic) | seed list, feedback-updated | Low-importance path priors (`node_modules`, `.git`, `.venv`, OS folders…). |
| `representation_policy_version` | config | bumped on rule change | Versions budget/importance/precedence; forces projection rebuild. |
| `EVEN_GLOBAL_INCLUDE_EXIF_LOCATION` | env bool | `0` | Allow GPS in global representatives. |
| `EVEN_OLLAMA_RERANK_MODEL` | env | unset | Existing optional local rerank model. |
| RRF route weights | config | uniform | Future cross-route fusion weights. |
| Routing thresholds | config | listed above | Hit count, score gap, and hydration widening thresholds. |
| Remote models | policy | disabled | No remote model by default. |

## Dependencies And Risks

Dependencies:

- current parse/index/search behavior from the existing CLI;
- Tantivy availability for FTS tests that exercise real indexes;
- fake local summary generator for CI tests;
- optional local Ollama only for manual/runtime summary generation.

Risks:

- Summaries can hide minority content if treated as proof. Mitigation: route
  only, then hydrate deep root-scoped evidence.
- Routing can reduce recall if confidence checks are too strict. Mitigation:
  fallback-all-current-FTS on weak hit count, weak score gap, or missing
  hydrated refs.
- Making summary generation implicit would surprise users with model cost.
  Mitigation: explicit `index routing` build command.
- Schema changes can strand beta catalogs. Mitigation: bump user version and use
  existing reset-required behavior; no silent migration.
- Route traces can leak summary snippets. Mitigation: keep traces compact and
  avoid full source text.

## Exit Criteria

D0/D1 is done when:

- `plan.md`, `implementation.md`, and `test.md` reflect the implemented scope;
- `catalog.yaml`, `store_templates.yaml`, configs, and durable spec are updated;
- `summary_nodes` exists with the schema above or a documented compatible
  equivalent;
- `even index routing <path>` can build current document root summaries, media
  album summaries, and a global representative FTS projection for small fixtures;
- `even search text <query>` routes through global representatives when current
  and falls back to all current FTS when unavailable or weak;
- result JSON includes hydrated refs and route trace/widening status;
- no vectors, generated chunks, raw queries, or global index registry rows are
  stored in SQLite;
- targeted tests and any required dependency-skipped tests are recorded in
  `test.md`.
