# Plan v3 (CC): Mapping Media into Global Routing Indexes

Date: 2026-06-11
Status: Idea capture only. Not approved scope. Supersedes the media-routing
notes in `plan-v2-cc.md` and `plan-v2-cd.md` by merging the best of both. Does
not modify `plan.md` or the hand-in.

## What this merges

- From `plan-v2-cc.md`: tight grounding in the current code, the
  FTS-first/semantic-later inversion, n=1 graceful degradation, the
  vector-space-cannot-mix caveat, and concrete landing on the open points.
- From `plan-v2-cd.md`: OCR as a first-class routing facet, screenshots and
  diagrams as special cases, multi-facet routing-text fusion, audio as a
  modality, a per-modality widening ladder, and the heightened privacy surface
  of visual media.

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
chunk embeddings, sample a few medoids, summarize only from those samples
(lossy by design). These notes map media onto that concept.

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

## Core idea: image = chunk, album/folder = document

Media has the same shape as the document concept, one level up.

| Text world | Media world |
| --- | --- |
| chunk (text + text-embedding) | image (pixels + SigLIP vector) |
| document = many chunks | album / folder = many images |
| document summary = cluster chunk vectors, sample medoids, summarize | album summary = cluster SigLIP vectors, sample medoid images, summarize |
| document-summary embedding -> global semantic routing | album centroid / medoid SigLIP vectors -> global routing |

The **image is the chunk-level atom**; the **folder/album contributes the
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
  opt-in or a strong manifest hit.

## The lossy-summary recipe maps exactly — and gets cheaper

The hand-in's stratified destructive sampling for documents has a direct media
analog that also solves VLM cost:

> Do not VLM-caption every photo. Cluster the SigLIP vectors (already
> computable), pick the cluster medoids, run the expensive model (caption, and
> later OCR/labels) on **medoids only**, then summarize those few outputs into
> one album routing-text.

Candidate sampling mix (mirrors the document mix):

```text
40% visual cluster medoids / centroid-nearest items
20% OCR-rich, label-rich, or entity-rich items   (future facets)
15% filename / path / title / metadata-rich items
15% random reservoir sample
10% recent, large, or user-marked items
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
  building any global representative embedding store. This matches the existing
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

A text query can therefore fan to three global entry points —
FTS(doc + media routing-text), text-vector reps, and SigLIP-via-text->image —
and the router merges. Keep their scores separate; do not pretend cross-space
or cross-index scores are calibrated.

## Multi-resolution levels (L0–L4) for media

- **L0 root rep** = root-wide centroid + a root routing-text rollup.
- **L1 album rep** = per-folder centroid + a few medoid vectors + fused
  routing-text (the main media contribution).
- **L2 item rep** = single image/video/audio item: its vector + its routing-text
  (the "document" level for media).
- **L3** = visual cluster / scene group / screenshot group / audio segment group;
  also where "image made of region/tile chunks" would live if items are ever
  sub-divided. Mostly future for still images.
- **L4 proof** = the existing per-scope `images` LanceDB store (and future
  per-scope media/transcript indexes), unchanged as the evidence layer.

## Search and widening behavior

Combine media and document representatives without pretending their scores are
comparable. Preserve a route trace:

```text
query
  -> global representative hits (FTS + per-space vector reps)
  -> selected roots / folders / media clusters
  -> lower root-scoped searches (deep FTS / image LanceDB)
  -> hydrated evidence hits (refs to media_assets / document_objects)
  -> widening status
```

Widening ladder when media routing is weak:

- increase representative top-k;
- include sibling clusters / parent folders / more roots;
- if embedding routing is weak, try OCR / caption FTS;
- if caption / OCR routing is weak, try visual embedding search;
- fall back to broader root-scoped fanout.

## Privacy surface (higher for visual media)

Visual media leaks more than text representatives do. `media.py` already
extracts EXIF GPS (`gps_lat` / `gps_lon`); OCR, captions, and any future
detected labels can surface faces, names, locations, or document contents.
Routing-text, snippets, and route traces over media must be redaction-checked,
and EXIF location should be policy-gated before it enters any global
representative. Captions stay local-only (Ollama), consistent with the
no-default-remote-model stance.

## How this lands on the existing plan (no edits made)

- Reuse the proposed `summary_nodes` with a **small** kind set
  (`album_summary` / `media_cluster_summary`) plus `modality` and `media_kind`
  columns — not a separate kind per screenshot/diagram/scene. This matches the
  existing closed `MEDIA_KINDS` vocabulary rather than fragmenting routing.
- `source_object_ids_json` holds **asset_ids** (the medoids); point with the
  existing `corpus_cache.<table>.<row_id>` ref contract, not a new
  `route_target` string.
- `coverage_estimate` = sampled medoids ÷ total items; `sample_policy` =
  e.g. `"siglip_kmeans_medoids"`.

Touches existing open points:

- OP-002 — add `album_summary` / `media_cluster_summary` kinds + modality field.
- OP-006 — representative rows carry `modality`, `media_kind`, provenance, and
  per-facet model/profile metadata.
- OP-009 — text->media can stay FTS-first; image->media wants global semantic
  routing earlier (per-modality resolution above).
- OP-010 / OP-011 — captions/OCR/labels are model-backed, opt-in, local-only;
  fits the no-default-remote-model stance.
- OP-012 — generated captions/OCR/labels/summaries must record provenance,
  coverage, and confidence; representatives must not prove absence.

## Compact principle

For media, route with a fusion of filenames, paths, OCR, captions, labels,
metadata, and representative embeddings; prove with root-scoped media evidence.
The cluster-of-embeddings route is the star for image->image and is already
built; the routing-text route is the unifier that lets media share one global
FTS map with documents. Use both; do not choose.

## Open questions before scope

- Clustering method and medoid count per album (fixed k vs. adaptive by item
  count).
- Whether L0 root reps store a centroid, a few medoids, or both.
- Routing-text assembly: concatenate medoid facets vs. a second LLM rollup.
- When (if ever) OCR over media images is worth a new pipeline, given docling
  already does document OCR.
- Refresh/staleness: reuse the `image_stores` watermark or add a separate media
  summary watermark.
- Video keyframe + audio transcript sampling policy and cost ceilings (defer vs.
  first-class).
