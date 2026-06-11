# Plan: Mapping Media into Global Routing Indexes

Date: 2026-06-11
Status: Decision record — all open points closed. Merges `plan-v2-cc.md` and
`plan-v2-cd.md`; supersedes `old-plan.md` for decision tracking (every
OP-001..OP-020 is mapped below). The first implementation slice — document-only
routing per **D0** — is unblocked. Does not modify the hand-in.

## Problem summary

The hand-in proposes a multi-resolution search architecture: SQLite as durable
truth, full FTS and semantic indexes scoped by root, a lightweight global
representative layer that routes queries to likely roots/scopes, and lossy
summaries used only for routing, never as proof. `old-plan.md` critiqued that
hand-in against the repo contracts and raised twenty open design points
(OP-001..OP-020).

This plan answers two things at once:

1. **Closes the design decisions** needed before the first routing slice can be
   implemented, including the OPs the earlier drafts did not touch.
2. **Maps media into the same architecture**: how images, albums, screenshots,
   video, audio, and 3D assets contribute representatives to the global routing
   layer, given the media primitives the repo already has (`media_assets`,
   `media_observations`, per-scope SigLIP LanceDB stores, the reference
   contract).

## Resolution summary

- **Schema cost is +1 table.** `summary_nodes` goes into SQLite as
  current-state representative metadata. The global FTS/semantic stores are
  derived projections at fixed cache paths — no registry rows, no further
  tables (F1, F2).
- **Vectors never enter SQLite.** Embeddings belong to LanceDB. Rebuild
  sources are therefore per profile: text reps rebuild from SQLite alone;
  SigLIP reps rebuild from `summary_nodes` medoid IDs **plus** the per-scope
  LanceDB image stores (F2).
- **Lossy summaries are LLM-written, local-only.** Sample medoid chunks/images,
  feed only those to local Ollama; deterministic facets are concatenated
  alongside (F3).
- **Scores stay uncalibrated; ranks merge.** Cross-route candidate merging uses
  reciprocal rank fusion; raw per-route scores survive in the route trace (F4).
- **An image container is a container, wherever it lives.** A media-bearing
  document (a PDF with figures) is treated like a folder of images; a folder
  rep aggregates its direct media plus the embedded images of its documents.
  `container_kind` differentiates them in the schema; routing treats them alike
  (S5).
- **Facets that are off stay defined, not broken.** With OCR and captions
  disabled by default, the sampling mix renormalizes and the widening ladder
  skips unavailable rungs, recording the skip (M7).
- **Document-only routing ships first; media facets follow** (D0).

## Decisions

Status: *Decided* = accepted for the first implementation slice · *Open* =
needs a pick before the affected work starts. Path: *Single* = one clear path ·
*Fork* = multiple equally-weighted options. Nothing below is Open.

### Foundational

| ID | Point | Decision | Confidence | Path | Status |
| --- | --- | --- | --- | --- | --- |
| F1 | Does `summary_nodes` go in SQLite? | Yes — current-state representative metadata only (no history, no chunk rows). | High | Single | Decided |
| F2 | Does the global representative index need its own catalog registration? | **No.** The only catalog addition is `summary_nodes` (F1) — the representative text/metadata, i.e. the truth. The global FTS/LanceDB stores are **derived projections** at fixed known cache paths; they need no registry row and add no table. Rebuild sources are **per profile**: the `text` profile rebuilds from SQLite alone (re-embed `summary_text`); the `siglip` profile rebuilds from `summary_nodes` medoid asset_ids **plus** the per-scope LanceDB image stores, because **vectors never live in SQLite — embeddings belong to LanceDB**. The siglip projection therefore carries a rebuild dependency on per-scope store health that the text profile does not; a rebuild must report missing per-scope stores rather than silently emit a partial projection. Optional: a sidecar watermark file next to each store (not in the catalog) to skip no-op rebuilds. Net schema change for the whole feature is **+1 table**. | High | Single | Decided |
| F3 | How are lossy summaries generated? | Sample representative/medoid chunks → feed those few to a **local LLM (Ollama)** → summary text. Deterministic facets (paths, filenames, labels, metadata) are concatenated alongside into routing-text. The LLM step is intrinsic, not deferred. (Reverses OP-010's extractive-first default — that *was* the separate decision OP-010 called for.) | High | Single | Decided |
| F4 | Cross-index score handling + `search` result contract | Keep router rank separate from deep score — no cross-index or cross-space score calibration, ever. When the router fans a query to multiple global entry points (FTS, text-vector reps, SigLIP text→image), merge their candidate lists by **reciprocal rank fusion (RRF)**: rank-based, so it needs no calibrated scores; per-route weights are tunable config, default uniform. Raw per-route scores remain visible in the route trace. Result contract: JSONL hits + route trace + hydrated refs + widening status. | High | Single | Decided |
| D0 | Sequencing | Build the document-only routing slice first; add media second. | High | Single | Decided |

### Schema / registry

| ID | Point | Decision | Confidence | Path | Status |
| --- | --- | --- | --- | --- | --- |
| S1 | `summary_nodes` kinds + modality | Small kind set — `root_summary` / `folder_summary` / `document_summary` / `album_summary` / `media_cluster_summary` / `negative_summary` — plus `modality` and `media_kind` columns. One naming scheme, used identically here and in the schema-landing section. | High | Single | Decided |
| S2 | Representative rows vs. chunk rows | Separate representative FTS template, distinct from chunk templates; representative rows carry provenance, coverage, and confidence, not chunk evidence fields. | High | Single | Decided |
| S3 | Global semantic split by embedding space | One global rep table per profile (`text`, `siglip`, …); never mixed. | High | Single | Decided |
| S4 | EXIF/GPS in global reps | Exclude EXIF location by default; opt-in flag to include; captions local-only. | High | Single | Decided |
| S5 | Image containers: folder vs media-bearing document | A **media-bearing document (e.g. a PDF with figures) is treated like a folder of images**: same album-level recipe (cluster embedded-image vectors → medoids → fused routing-text). A **folder's album rep aggregates its direct media assets plus the embedded images of the documents inside it**. Album-level `summary_nodes` rows carry a `container_kind` column (`folder` \| `document`) so provenance is distinguishable; routing treats both identically. | High | Single | Decided |

### Media-specific

| ID | Point | Decision | Confidence | Path | Status |
| --- | --- | --- | --- | --- | --- |
| M1 | Clustering method + medoid count per album | k-means on L2-normalized SigLIP vectors; medoid = nearest-centroid; adaptive `k = clamp(ceil(√(n/2)), 1, 16)`. | Medium (k tunable) | Single | Decided |
| M2 | L0 root rep: centroid, medoids, or both? | Both — one centroid (recall anchor) + a few medoids (precision exemplars). | Med-High | Single | Decided |
| M3 | Routing-text assembly | Content summary is LLM (per F3); deterministic facets concatenated; a *second* rollup-LLM pass over merged facets is deferred. | High | Single | Decided |
| M4 | OCR over media images | Plan it now, gated by a config flag (env var), **disabled by default**. Document the flag centrally (see *Configuration flags*). | High | Single | Decided |
| M5 | Refresh/staleness watermark | Separate media-summary watermark (depends on caption/OCR state, not just embeddings). | Medium | Single | Decided |
| M6 | Video keyframe + audio transcript | Defer transcript/keyframe **parsing** for V1. Audio & video stay **in scope for scanning + metadata extraction** (EXIF/container/codec/duration), so their path/metadata facets can feed routing-text; no embedding/transcript representative yet. | High | Single | Decided |
| M7 | Behavior when a facet is unavailable (OCR off, no captions) | Skip absent facets deterministically: their share of the sampling mix is **renormalized across the remaining strata**; widening-ladder rungs that depend on them are **skipped, and the widening status records which facets were unavailable**. Default-config V1 media routing is therefore fully defined: medoid vectors + filename/path/metadata + random reservoir + recency. | High | Single | Decided |

### Carried over from OP-001..OP-020

Open points from `old-plan.md` that the v2/v3 drafts never addressed. All
resolve by accepting the old plan's proposed defaults — none turned out to be a
real fork.

| ID | Point | Decision | Confidence | Path | Status |
| --- | --- | --- | --- | --- | --- |
| OP-007 | Explicit scope controls on `search text`? | Defer new flags; first implement default all-roots routing. Scope flags only after routed search exists and proves the need. | High | Single | Decided |
| OP-013 | Query usage tracking in SQLite? | Nothing in V1; raw query text is never persisted. Aggregate counters keyed by route/index/scope remain a separate later decision. | High | Single | Decided |
| OP-014 | Automatic child-scope suggestions from scan? | Suggestions are review output only; scopes are never auto-created. | High | Single | Decided |
| OP-015 | Negative summaries vs exclusion for generated folders? | Default excludes stay excluded; `negative_summary` only for included-but-low-value folders. | High | Single | Decided |
| OP-016 | Archive routing | Manifest-level representative first; deep unpack/index only on opt-in or a strong manifest hit. | High | Single | Decided |
| OP-017 | What does "good enough" mean for widening? | Thresholds on three signals: hit count, score gap, and hydrated-evidence availability. Exact values are config defaults set at implementation — tunables, not design forks. | Med-High | Single (values tunable) | Decided |
| OP-020 | When are materialized collection indexes created? | Explicit manual promotion only; not in V1; never automatic. | High | Single | Decided |

### Where every OP landed

Traceability from `old-plan.md`'s registry into this record:

| OP | Resolved by |
| --- | --- |
| OP-001 | F1 |
| OP-002 | S1 |
| OP-003 | F2 — no registry row (reverses old Phase-3's "register the global FTS index") |
| OP-004 | F2 — moot: no registry row means no synthetic root question |
| OP-005 | F2 — fixed cache path; template wiring is implementation detail |
| OP-006 | S2 |
| OP-007 | Carried-over table |
| OP-008 | D0 + *V1 ordering* section (global rep FTS routes to root-scoped FTS) |
| OP-009 | *V1 ordering* section — per query-modality: text→media stays FTS-first; image→media gets global semantic earlier |
| OP-010 | F3 — **reverses** the extractive-first default; LLM step intrinsic, local-only |
| OP-011 | F3 + S4 + *Remote models* policy row in the flags table |
| OP-012 | S2 + *How this lands on the schema* (provenance, coverage, confidence) |
| OP-013 | Carried-over table |
| OP-014 | Carried-over table |
| OP-015 | Carried-over table |
| OP-016 | Carried-over table (echoed in *Modality notes: Archives*) |
| OP-017 | Carried-over table |
| OP-018 | F4 — separate scores; RRF merge |
| OP-019 | F4 — JSONL + route trace + hydrated refs + widening status |
| OP-020 | Carried-over table |

## Lineage

- From `plan-v2-cc.md`: tight grounding in the current code, the
  FTS-first/semantic-later inversion, n=1 graceful degradation, the
  vector-space-cannot-mix caveat, and concrete landing on the open points.
- From `plan-v2-cd.md`: OCR as a first-class routing facet, screenshots and
  diagrams as special cases, multi-facet routing-text fusion, audio as a
  modality, a per-modality widening ladder, media-bearing documents as
  summary-bearing units (now S5), and the heightened privacy surface of visual
  media.

Deliberately dropped from `plan-v2-cd.md`: the `route_target` path-like
namespace (conflicts with the reference contract), the ten-plus per-modality
summary kinds (over-granular), and presenting unbuilt pipelines (object/label
detection, OCR) as if they already exist.

## Context

The global routing index is a cheap "map, not the territory": every root
contributes one (or a small cluster of) representative(s) to a global index;
a query routes to the closest root/scope, then dives into that root's deep
index, iterating and widening as needed.

The document-side representative is a **lossy summary**: cluster a document's
chunk embeddings, sample a few medoid chunks, and feed only those sampled chunks
to a local LLM to write the summary (lossy by design — the model never sees the
whole document). See **F3**. These notes map media onto that concept.

Current implementation anchors:

- `src/even/media.py` — deterministic metadata + opt-in VLM captions/kinds in
  `media_observations` (local Ollama; `describe` is opt-in and expensive).
  Extracts EXIF including `gps_lat` / `gps_lon`. Closed `MEDIA_KINDS` vocab.
- `src/even/image_index.py` — SigLIP 2 joint image/text embeddings in a
  per-scope LanceDB `images` table; already serves image->image and text->image.
- `src/even/references.py` — the reference contract:
  `corpus_cache.<table>.<row_id>`. Representatives point with this, not a new
  addressing scheme.

What does **not** exist yet (treat as future facets, never assume present):
OCR over media images, object/label/entity/scene detection, audio transcripts,
video keyframe extraction.

## Core idea: image = chunk, image container = document

Media has the same shape as the document concept, one level up.

| Text world | Media world |
| --- | --- |
| chunk (text + text-embedding) | image (pixels + SigLIP vector) |
| document = many chunks | image container = many images |
| document summary = cluster chunk vectors, sample medoids, summarize | container summary = cluster SigLIP vectors, sample medoid images, summarize |
| document-summary embedding -> global semantic routing | container centroid / medoid SigLIP vectors -> global routing |

An **image container** is anything that holds many images (S5):

- a **folder/album** of media files;
- a **media-bearing document** — a PDF or office document with embedded
  figures is, for routing purposes, a folder of images;
- a **folder rep aggregates both**: its direct media assets plus the embedded
  images of the documents inside it.

The same recipe applies to all of them; `container_kind` on the summary node
records which one it was.

The **image is the chunk-level atom**; the **container contributes the
cluster-of-embeddings representative**. A single important image (one scanned
diagram in a text folder) is the n=1 case: its own vector + its own routing text
is the representative, no clustering needed. The design degrades gracefully from
album to single image.

Media is the clearest validation of the "cluster of embeddings" half of the
global-index idea, because the embedding is natively lossy.

## A media representative is a fusion of facets, not one signal

The single most important upgrade over caption-only thinking: a media
representative blends every cheap routing signal available for that item or
cluster into one **routing-text** field, plus a **representative embedding**.

```text
routing_text =
  path tokens
  filename tokens
  OCR text            (future facet)
  generated caption   (opt-in, expensive)
  generated cluster summary
  detected labels     (future facet)
  selected metadata   (e.g. media_kind, capture date)
representative_vector = cluster medoid / centroid SigLIP vector(s)
```

Facets that are unavailable under the current configuration are skipped per
**M7** — never silently assumed present.

Two routes follow from this, and the global index should carry both — it is not
embedding *or* caption:

1. **SigLIP vector route (primary for photos/video).** The embedding *is* the
   lossy representation — deterministic, needs no model beyond the encoder
   already present, and serves both image->image and text->image (joint space).
2. **Routing-text / FTS route (the unifier).** Lets media share the **same
   global FTS index as document summaries**, so one broad text query can rank a
   PDF-root representative against a photo-album representative in one lookup.

Neither can be dropped: image->image queries have no text fallback; 3D models
have no joint encoder and lean entirely on text/metadata.

## Modality notes: text often beats pixels

Not all media route best on visual similarity. Pick the strongest signal per
modality.

- **Photos** — visual embedding primary; caption, EXIF (when policy allows),
  and OCR as support.
- **Screenshots** — OCR / UI text / window-and-app titles / surrounding context
  usually beat pure visual similarity. Screenshots cluster visually into
  "rectangles of text," which is non-discriminative in SigLIP space.
- **Charts / diagrams** — OCR, figure captions, nearby document text, and source
  page references. Generated visual summaries help but are risky as the only
  signal.
- **Scanned documents** — OCR is the primary route; treat closer to a document
  than to a photo.
- **Video** — sampled keyframe embeddings + scene clusters, plus transcript when
  available. Route to video ID + timestamp range, then dive. (Keyframe and
  transcript pipelines are future work.)
- **Audio** — for speech, transcript is the primary routing text. Audio
  embeddings / sound-event labels are later signals for non-speech. (`audio` is
  already a recognized `media_class`; transcript pipeline is future.)
- **3D models** — no joint encoder; route on metadata + a generated description.
  This is exactly why the routing-text route must exist alongside embeddings.
- **Archives** — manifest-level representative first; deep unpack/index only on
  opt-in or a strong manifest hit (OP-016).

## The lossy-summary recipe maps exactly — and gets cheaper

The hand-in's stratified destructive sampling for documents has a direct media
analog that also solves VLM cost:

> Do not VLM-caption every photo. Cluster the SigLIP vectors (already
> computable), pick the cluster medoids, run the expensive model (caption, and
> later OCR/labels) on **medoids only**, then summarize those few outputs into
> one container routing-text.

Candidate sampling mix (mirrors the document mix):

```text
40% visual cluster medoids / centroid-nearest items
20% OCR-rich, label-rich, or entity-rich items   (future facets)
15% filename / path / title / metadata-rich items
15% random reservoir sample
10% recent, large, or user-marked items
```

Strata whose facets are unavailable are dropped and the remaining shares
renormalized (M7). Under default config (no OCR, no captions) the effective mix
is therefore:

```text
50%   visual cluster medoids / centroid-nearest items
~19%  filename / path / title / metadata-rich items
~19%  random reservoir sample
~12%  recent, large, or user-marked items
```

One sampling pass feeds both routes: medoid vectors -> the semantic
representative; medoid routing-text -> the FTS representative. The result
describes the sampled pack only — a routing summary, never a complete statement
about all media under the root.

## V1 ordering: resolve per query-modality (the cc/cd disagreement)

`plan-v2-cc.md` argued media should pull semantic routing earlier;
`plan-v2-cd.md` argued V1 should stay textual and defer global media embeddings.
Both are partly right; the honest resolution is **per query-modality**:

- **text -> media** routing can go textual-first. Reuse the global FTS over
  media routing-text (filenames, OCR, captions, labels, metadata) before
  building any global representative embedding store. This matches the
  OP-008/OP-009 "FTS first" ordering and needs no new vector infra.
- **image -> media** routing has no text path and the per-scope SigLIP index
  **already exists**. Deferring it shelves an index you have already built, so
  for this query modality semantic global routing is not really deferrable —
  it just needs medoid extraction into a global representative table.

So the global index matures unevenly by modality, which is fine: it is a map,
not the territory.

## Caveat: embedding spaces cannot share one table

The global *semantic* representative index cannot be a single mixed table —
document-summary text-embeddings, SigLIP image vectors, and any audio vectors
live in different spaces and their distances are not comparable. Realistic
shape:

- **Global FTS** = the unifier: doc summaries + media routing-text co-ranked in
  one text index.
- **Global semantic** = split by embedding space / profile:
  `.../global_representatives/text/…`, `.../siglip/…`, etc.
- **SigLIP text->image is the bridge**: a text query reaches image vectors
  without needing captions to exist.

Rebuild sources differ by profile (F2): the text projection rebuilds from
SQLite alone; the siglip projection needs `summary_nodes` (which medoids) plus
the per-scope LanceDB stores (the vectors themselves), because embeddings never
enter SQLite.

A text query can therefore fan to three global entry points —
FTS(doc + media routing-text), text-vector reps, and SigLIP-via-text->image —
and the router merges their candidate lists by reciprocal rank fusion (F4).
Per-route scores stay separate in the trace; cross-space and cross-index scores
are never treated as calibrated.

## Multi-resolution levels (L0–L4) for media

- **L0 root rep** = root-wide centroid + a root routing-text rollup.
- **L1 container rep** = per-container (folder *or* media-bearing document, per
  S5) centroid + a few medoid vectors + fused routing-text — the main media
  contribution. Folder containers include the embedded images of their
  documents.
- **L2 item rep** = single image/video/audio item: its vector + its routing-text
  (the "document" level for media).
- **L3** = visual cluster / scene group / screenshot group / audio segment group;
  also where "image made of region/tile chunks" would live if items are ever
  sub-divided. Mostly future for still images.
- **L4 proof** = the existing per-scope `images` LanceDB store (and future
  per-scope media/transcript indexes), unchanged as the evidence layer.

## Search and widening behavior

Combine media and document representatives without pretending their scores are
comparable: rank-based RRF for the merge, raw scores in the trace (F4).
Preserve a route trace:

```text
query
  -> global representative hits (FTS + per-space vector reps, RRF-merged)
  -> selected roots / containers / media clusters
  -> lower root-scoped searches (deep FTS / image LanceDB)
  -> hydrated evidence hits (refs to media_assets / document_objects)
  -> widening status (incl. rungs skipped as facet-unavailable)
```

Widening ladder when media routing is weak:

- increase representative top-k;
- include sibling clusters / parent folders / more roots;
- if embedding routing is weak, try OCR / caption FTS — *only if those facets
  exist*; otherwise skip the rung and record `facet_unavailable` in the
  widening status (M7);
- if caption / OCR routing is weak, try visual embedding search;
- fall back to broader root-scoped fanout.

"Good enough" (OP-017) = thresholds on hit count, score gap, and
hydrated-evidence availability; values are config defaults at implementation.

## Privacy surface (higher for visual media)

Visual media leaks more than text representatives do. `media.py` already
extracts EXIF GPS (`gps_lat` / `gps_lon`); OCR, captions, and any future
detected labels can surface faces, names, locations, or document contents.
Routing-text, snippets, and route traces over media must be redaction-checked,
and EXIF location should be policy-gated before it enters any global
representative. Captions stay local-only (Ollama), consistent with the
no-default-remote-model stance. Raw query text is never persisted (OP-013).

## Configuration flags

All tunables this feature introduces live in **one** documented place. During
design that place is this section; at implementation it is mirrored into a single
`config/` reference (`config/README.md`) so there is no scattering. Flags default
to the cheapest, most private behavior; nothing model-backed or network-bound is
on by default.

**Naming convention (decided):** all environment flags use the `EVEN_` prefix.
The pre-rebrand `AGENTS_DOCS_OLLAMA_RERANK_MODEL` was renamed to
`EVEN_OLLAMA_RERANK_MODEL` in `src/even/hybrid.py` on 2026-06-11.

| Flag | Type | Default | Controls |
| --- | --- | --- | --- |
| `EVEN_MEDIA_OCR` | env bool | `0` (off) | Enable the OCR facet over media images (M4). Planned but opt-in. |
| `EVEN_SUMMARY_MODEL` | env / config | existing `DEFAULT_MODEL` | Local Ollama model that writes lossy summaries from sampled chunks (F3). |
| `EVEN_SUMMARY_OLLAMA_URL` | env / config | existing `DEFAULT_URL` | Local Ollama endpoint for summary/caption generation. |
| `EVEN_MEDIA_CLUSTER_K_MAX` | config | `16` | Upper clamp on medoids per container (M1). |
| `EVEN_GLOBAL_INCLUDE_EXIF_LOCATION` | env bool | `0` (off) | Allow EXIF GPS into global representatives (S4); off = location is dropped. |
| `EVEN_OLLAMA_RERANK_MODEL` | env | unset | Existing optional local rerank model (renamed from `AGENTS_DOCS_OLLAMA_RERANK_MODEL`). |
| RRF route weights | config | uniform | Per-route weights for reciprocal rank fusion (F4); tunable, not env-gated. |
| Widening thresholds | config | set at implementation | Hit count, score gap, hydrated-evidence availability (OP-017). |
| Remote models | policy | disabled | No remote model by default; any remote provider must be explicit caller policy (OP-011, S4). |

## How this lands on the schema

- Reuse the proposed `summary_nodes` with the **small** kind set from S1
  (`album_summary` / `media_cluster_summary` for media) plus `modality` and
  `media_kind` columns — not a separate kind per screenshot/diagram/scene. This
  matches the existing closed `MEDIA_KINDS` vocabulary rather than fragmenting
  routing.
- Album-level rows carry `container_kind` (`folder` | `document`) per S5: a
  media-bearing document's embedded images get the same `album_summary`
  treatment as a folder of files, distinguishable by provenance, identical for
  routing.
- `source_object_ids_json` holds **asset_ids** (the medoids); point with the
  existing `corpus_cache.<table>.<row_id>` ref contract, not a new
  `route_target` string.
- `coverage_estimate` = sampled medoids ÷ total items; `sample_policy` =
  e.g. `"siglip_kmeans_medoids"`.
- Vectors stay out: `summary_nodes` stores **which** medoids (IDs), never their
  embeddings; the vectors live in per-scope LanceDB and the derived global
  projections (F2).

## Compact principle

For media, route with a fusion of filenames, paths, OCR, captions, labels,
metadata, and representative embeddings; prove with root-scoped media evidence.
The cluster-of-embeddings route is the star for image->image and is already
built; the routing-text route is the unifier that lets media share one global
FTS map with documents. Use both; do not choose.
