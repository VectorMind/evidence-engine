# Plan v2 (CC notes): Mapping Media into Global Routing Indexes

Date: 2026-06-11
Status: Idea capture only. Not approved scope. Does not modify `plan.md` or the
hand-in. Records how media (images, video, 3D) maps onto the global routing
index concept so it can be folded into a future planning pass.

## Context

The global routing index is a cheap "map, not the territory" layer: every root
contributes one (or a small cluster of) representative(s) to a global index;
a query routes to the closest root/scope, then dives into that root's deep
index, iterating and widening as needed.

The document-side representative is a **lossy summary**: cluster the chunk
embeddings of a document, sample a few medoids, and summarize only from those
samples (lossy by design).

These notes answer: how does media map to that concept, and for images do we
route on embeddings or on a generated summary taken as-is? Anchored to the
current implementation:

- `src/even/media.py` — deterministic metadata + opt-in VLM captions/kinds in
  `media_observations` (local Ollama, `describe` is opt-in and expensive).
- `src/even/image_index.py` — SigLIP 2 joint image/text embeddings in a
  per-scope LanceDB `images` table; serves image->image and text->image.

## Core idea: image = chunk, album/folder = document

Media has the same shape as the document concept, one level up.

| Text world | Media world |
| --- | --- |
| chunk (text + text-embedding) | image (pixels + SigLIP vector) |
| document = many chunks | album / folder = many images |
| document summary = cluster chunk vectors, sample medoids, summarize | album summary = cluster SigLIP vectors, sample medoid images, caption/summarize |
| document-summary embedding -> global semantic routing | album centroid / medoid SigLIP vectors -> global routing |

Consequence: the **image is the chunk-level atom**, and the **folder/album is
what contributes a cluster-of-embeddings representative** to the global index.
A single important image (e.g. one scanned diagram in a text folder) is just the
n=1 case: its own vector + its own caption is the representative, no clustering
needed. The design degrades gracefully from album to single image.

Media is the clearest validation of the "cluster of embeddings" half of the
global-index idea, more so than text, because the embedding is natively lossy.

## Two representative routes: keep both, not either/or

Media offers two representations; they serve different query modalities, so the
global index should carry both.

1. **SigLIP vector route (primary for images/video).** The embedding *is* the
   lossy representation — no model summarization needed at index time,
   deterministic, and serves both image->image and text->image because SigLIP
   is a joint space. This is the purest form of "cluster of embeddings."
2. **Caption-text route (secondary, the common denominator).** The VLM caption
   in `media_observations` is a lossy textual projection of the image. Its value:
   it lets media share the **same global FTS index as document summaries**, so
   one broad text query can rank a PDF-root representative against a photo-album
   representative in a single lookup.

Why neither can be dropped:

- An **image->image** query has no caption fallback (the query is a photo).
- A **3D-model** query has no good embedding fallback (no joint encoder), so it
  leans entirely on generated description + metadata.

Different media classes have different strongest signals; the global index is
heterogeneous and each contributor submits its best representative.

## The lossy-summary recipe maps exactly — and gets cheaper

The hand-in's stratified destructive sampling for documents has a direct media
analog that also solves VLM caption cost:

> Do not VLM-caption every photo. Cluster the SigLIP vectors (already
> computable), pick the cluster medoids, caption **only the medoids**, then
> summarize those few captions into one album summary.

This is literally "summarize the content only from the samples," lossy by
design, and cheap because the expensive model runs only on cluster centers.
One sampling pass feeds both global routes:

- medoid SigLIP vectors -> the album's **semantic** representative;
- medoid captions (optionally summarized) -> the album's **FTS** representative.

## Notable inversion: media flips "FTS first, semantic later"

`plan.md` OP-008/OP-009 build global **FTS** routing first and defer global
semantic routing. That is right for text. For media it inverts:

- The **SigLIP semantic representative is primary** (embedding is the native
  signal and needs no model beyond the already-present encoder).
- The **caption-FTS representative is the optional add-on** (captions are
  opt-in and expensive via `describe`).

So media likely justifies pulling a **global image-representative LanceDB**
earlier than the text-side global semantic index. Not a contradiction: the
global index is a map and may mature at different speeds per modality.

## Caveat: SigLIP and text vectors cannot share one table

The global *semantic* representative index cannot be a single mixed LanceDB
table — document-summary text-embeddings and SigLIP image vectors live in
different vector spaces and their distances are not comparable. Realistic shape:

- **Global FTS** = the unifier: doc summaries + image captions co-ranked in one
  text index.
- **Global semantic** = split by embedding space: one representative table per
  space (e.g. `.../global_representatives/text/…` and `.../siglip/…`).
- **SigLIP text->image is the bridge**: a plain text query reaches image vectors
  without needing captions to exist.

A text query can therefore fan to three global entry points — FTS(doc+caption),
text-vector reps, and SigLIP-via-text->image — and the router merges. Decide
this deliberately rather than discovering it later.

## Multi-resolution levels (L0–L4) for media

- **L0 root rep** = centroid of all image vectors in the root + root caption
  rollup.
- **L1 album rep** = per-folder centroid + a few medoid vectors (the main media
  contribution).
- **L2 image rep** = single image vector + its caption (the "document" level for
  media).
- **L3** = mostly empty for images today; this is where "image made of
  region/object/tile chunks" would live if images are ever sub-divided. Future.
- **L4 proof** = the existing per-scope `images` LanceDB store, unchanged as the
  evidence layer.

Non-image classes slot in by strongest signal:

- **Video** -> keyframe sampling (sample frames -> SigLIP -> cluster -> medoids);
  same machinery with the timeline as the "folder."
- **3D** -> caption/metadata route only (no joint encoder); exactly why the
  caption route must exist.

## How this lands on the existing plan (no edits made)

Lightest touch when folded in later:

- Media reuses the proposed `summary_nodes` with new `kind`s
  (`album_summary` / `media_cluster_summary`).
- `source_object_ids_json` holds **asset_ids** (the medoids) instead of chunk
  ids.
- `coverage_estimate` = medoids ÷ total images.
- `sample_policy` = `"siglip_kmeans_medoids"`.

Touches existing open points:

- OP-002 — add media summary kinds.
- OP-009 — media wants global **semantic** routing earlier than text does.
- OP-010 / OP-011 — captions are the model-backed summary, already opt-in and
  local-only via Ollama; fits the "no default remote model" stance.

## One-line principle

For media, the cluster-of-embeddings half of the idea is the star — SigLIP
medoids route natively for both image and text queries — and the generated
caption is a cheap text shadow that lets images share the global FTS map with
documents. Use both; do not choose.

## Open questions to resolve before scope

- Clustering method and medoid count per album (k, or adaptive by image count).
- Whether L0 root reps store a centroid, a few medoids, or both.
- Caption-summarization: concatenate medoid captions vs. a second LLM rollup.
- Refresh/staleness: tie album reps to the image-store watermark already in
  `image_stores`, or a separate media summary watermark.
- Video keyframe sampling policy and cost ceiling (defer vs. first-class).
