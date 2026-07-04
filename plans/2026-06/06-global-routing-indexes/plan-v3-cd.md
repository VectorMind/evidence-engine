# Plan V3 Concept Draft: Global Routing Indexes With Media

Date: 2026-06-11
Status: Concept draft only. Not approved implementation scope.

## Purpose

This draft combines the broader media-routing contract from `plan-v2-cd.md`
with the stronger repo-specific image ideas from `plan-v2-cc.md`.

The goal is to describe how images, screenshots, video, audio, 3D assets, and
other media should contribute to a global routing index without weakening the
core rule from the global routing plan:

```text
Representatives route.
Root-scoped indexes prove.
Lossy summaries and captions never prove absence.
```

## Current Repo Anchors

The repository already has media primitives that should shape the plan:

- `media_assets`, `image_metadata`, `video_metadata`, `model3d_metadata`,
  `media_artifacts`, `media_observations`, and `image_stores` exist in the
  catalog schema.
- `media_observations` can hold opt-in local Ollama captions and media-kind
  observations.
- `image_stores` registers root/scope-level SigLIP 2 LanceDB image stores.
- `search image` already supports image-to-image and text-to-image queries over
  the SigLIP joint image/text space.

These facts make image routing different from generic document routing: the
repo already has a useful root-scoped visual evidence layer.

## Working Principle

Media is first-class routing material, but it should not be forced into one
text-document shape.

```text
Media representatives route.
Root-scoped media indexes prove.
Generated captions and summaries are routing text, not truth.
```

The global index is a map of likely roots, folders, documents, media groups,
and clusters. It should not contain every image, frame, caption, transcript, or
embedding. It should contain representative signals that point downward into
root-scoped lower indexes.

## Mental Model

For image collections, this analogy is useful:

| Text world | Image/media world |
| --- | --- |
| Text chunk | Image or keyframe |
| Document | Album, folder, gallery, or media-bearing document |
| Document summary | Cluster/medoid summary of media items |
| Chunk embedding | Image or keyframe embedding |
| Root-scoped document index | Root-scoped media index |

The analogy is not universal. A screenshot, scanned page, or chart may behave
more like a document page than a photo. Still, the model is useful:

```text
image = chunk-level atom
album/folder/media-bearing document = summary-bearing unit
```

A single important image is the `n = 1` case: its own vector, caption, OCR,
metadata, and path signals can become the representative.

## Representative Facets

A media item, folder, or cluster may contribute multiple routing facets:

- filename, path, title, and surrounding document metadata;
- deterministic media metadata, such as size, format, duration, dimensions, or
  model geometry counts;
- OCR text, if present;
- generated caption or visual summary;
- generated or deterministic media kind;
- detected labels, objects, tags, entities, or scene text;
- transcript or audio-derived text for speech media;
- visual, audio, or multimodal embedding;
- cluster membership;
- exemplar or medoid media asset IDs;
- source document, page, frame, timestamp, or artifact references.

The representative row should point to a route target rather than act as final
evidence.

Example:

```text
kind: image_cluster_summary
modality: image
root_id: research_archive
route_target_kind: media_cluster
route_target_id: cluster_17
routing_text: scanned receipts, handwritten notes, whiteboard photos, architecture diagrams
exemplar_asset_ids: image_12, image_104, image_991
population_count: 340
sample_count: 8
cluster_count: 12
selection_policy: siglip_kmeans_medoids
confidence: medium
```

## Two Routes: Vector And Text

Media should normally have two representative routes. They solve different
retrieval problems, so the plan should keep both.

### Vector Route

For images, the SigLIP vector route is a native media signal.

It supports:

- image-to-image queries;
- text-to-image queries in the same SigLIP space;
- representative medoids without requiring VLM captions;
- cheap routing to likely roots, albums, folders, and image clusters.

Recommended pattern:

```text
per root or folder:
  cluster image embeddings
  keep selected medoid vectors globally
  optionally keep weak centroid metadata for diagnostics
  keep full per-image embeddings only in the lower root-scoped media index
```

Prefer medoids over a single centroid for routing. A heterogeneous root can
average into a meaningless centroid. If a centroid is stored, treat it as a
weak auxiliary signal, not the main representative.

### Text Route

The text route is the common denominator across documents and media.

It can include:

- paths and filenames;
- OCR;
- captions;
- media-kind observations;
- labels and tags;
- transcript snippets;
- deterministic metadata rendered as text;
- cluster or album summaries.

This route lets media participate in the same global FTS map as document
summaries. It is especially important for screenshots, scanned documents,
charts, diagrams, filenames, labels, and exact terms.

Generated captions are useful, but they are not inherently cheap. They are
model-backed, opt-in, non-deterministic observations. Captioning medoids is much
cheaper than captioning every image, but still requires explicit policy.

## Do Not Mix Vector Spaces

The global semantic layer cannot be one undifferentiated vector table.

Text embeddings, SigLIP image vectors, audio vectors, and any future multimodal
vectors live in separate spaces unless the selected model explicitly shares one
embedding space.

Realistic shape:

```text
global FTS:
  document summaries
  media captions
  OCR
  transcripts
  path and metadata text

global semantic/text:
  document and text-summary representatives

global semantic/siglip:
  image, screenshot, keyframe, and visual-cluster representatives

global semantic/audio:
  future audio representatives, if implemented
```

A text query may fan into more than one global entry point:

```text
query text
  -> global FTS
  -> global text representative embeddings
  -> global SigLIP text-to-image representatives
  -> routed root-scoped evidence searches
```

The router must keep route scores separate by backend/profile and merge them as
routing evidence, not as globally calibrated proof scores.

## Lossy Media Summary Recipe

The document plan uses clustered text samples to build lossy document or folder
summaries. For media, use a lossy visual evidence pack.

For images, the preferred recipe is:

```text
1. Build or reuse root-scoped image embeddings.
2. Cluster image vectors per root, folder, album, or media-bearing document.
3. Pick medoids or centroid-nearest exemplars.
4. Optionally caption only those medoids.
5. Summarize medoid captions, paths, OCR, labels, and metadata into routing text.
6. Store medoid vectors as global visual representatives.
7. Store routing text as global FTS representatives.
```

Candidate sampling mix:

```text
40% visual cluster medoids or centroid-nearest media items
20% OCR-rich, entity-rich, label-rich, or caption-rich media items
15% filename, path, title, or metadata-rich items
15% random reservoir sample
10% recent, large, user-marked, or otherwise important items
```

The resulting summary describes the sampled media pack only. It is a routing
summary, not a complete statement about all media under the root.

## Coverage And Provenance

Do not represent coverage as `medoids / total images`; that is only sampling
fraction.

Prefer explicit fields:

- `population_count`: total items represented;
- `sample_count`: total selected exemplars;
- `cluster_count`: clusters produced by the representative build;
- `represented_cluster_count`: clusters with at least one exemplar;
- `selection_policy`: for example `siglip_kmeans_medoids`;
- `source_refs_json`: typed references to source objects, media assets,
  pages, frames, or timestamps;
- `exemplar_asset_ids_json`: image/video/audio/model asset exemplars when
  applicable;
- `content_hash` or generation watermark;
- `producer`, `profile`, and model information for captions and embeddings;
- `confidence`: summary or representative confidence.

Coverage should explain what was sampled and what route target it represents.
It must not imply that unsampled content was inspected.

## Routing Levels

Media can use the same multi-resolution routing model:

```text
L0: root media summary or multiple root-level medoids
L1: folder, album, gallery, or collection summary
L2: media-bearing document summary, PDF figure/page group, or single image rep
L3: visual cluster, scene group, screenshot group, object/region group, or audio segment group
L4: actual image, frame, OCR block, caption, transcript, object, timestamp, or asset
```

Candidate representative kinds:

- `root_media_summary`
- `folder_media_summary`
- `album_summary`
- `media_cluster_summary`
- `image_cluster_summary`
- `single_image_summary`
- `screenshot_cluster_summary`
- `diagram_cluster_summary`
- `scanned_document_summary`
- `video_scene_summary`
- `audio_transcript_summary`
- `model3d_metadata_summary`
- `archive_media_manifest`
- `negative_media_summary`

## Modality Notes

Images and photos:

- Use SigLIP representative medoids, captions, labels, filenames, path tokens,
  EXIF-like metadata when policy allows, and OCR where available.

Screenshots:

- OCR, UI text, filenames, app/window titles, and surrounding document context
  may beat pure visual similarity. Keep text routing strong.

Scans:

- OCR and source document/page context are often the best route. Visual
  embeddings are still useful for layout, signatures, forms, and visual
  similarity.

Charts and diagrams:

- Keep OCR, figure captions, nearby document text, source page references, and
  visual representatives. Generated visual summaries are useful but risky as
  the only signal.

Video:

- Future video routing should use transcript plus sampled keyframes and scene
  clusters. Route to video IDs and timestamp ranges, then search deeper in a
  root-scoped video index. Treat global video SigLIP representatives as future
  work until keyframe extraction and cost policy are accepted.

Audio:

- For speech, transcript is the primary routing text. Audio embeddings and
  sound-event labels can be later routing signals for non-speech media.

3D models:

- Current deterministic metadata can route through filenames, format, vertex
  counts, face counts, dimensions, and other parsed fields. Generated 3D
  descriptions are future work unless a local, explicit producer is added.

Archives:

- Use a manifest-level representative first. Do not unpack and index deeply
  unless policy allows it, the user opts in, or the manifest routes strongly.

## V1 Recommendation

Use a two-lane V1 so media can take advantage of existing image stores without
forcing global semantic routing for all text.

### Shared V1: Global FTS Representatives

Build global representative FTS over text-like routing material:

```text
document summaries
folder/root summaries
filenames
paths
OCR
captions
media-kind observations
labels
transcripts
selected deterministic metadata
```

This remains the broad unifier across document and media routing.

### Image-Native V1 Candidate: Global SigLIP Representatives

If root-scoped `image_stores` are already current, add a small global
representative LanceDB for SigLIP medoids earlier than the general text
semantic global index.

This is not a contradiction of "FTS first" for documents. It is a
media-specific optimization because:

- SigLIP vectors are already the native lower image evidence signal;
- medoid vectors avoid captioning every image;
- image-to-image queries cannot rely on FTS;
- text-to-image routing works through SigLIP text embeddings.

The global SigLIP store should remain representative-only. Full per-image
embeddings stay in root-scoped image stores.

## V2 And Later

Later work can add:

- global text semantic representatives for document summaries;
- richer global media representative embeddings by modality;
- video keyframe and scene representatives;
- audio segment representatives;
- region/object/tile-level image routing;
- materialized collection indexes for repeated broad retrieval;
- learned or evaluated route-fusion policies.

Only add global per-item media indexes when repeated broad retrieval proves
that a materialized collection is worth the extra physical store.

## Search And Widening Behavior

The router should preserve route trace:

```text
query
  -> global representative hits by backend/profile
  -> selected roots, folders, media clusters, or route targets
  -> lower root-scoped searches
  -> hydrated evidence hits
  -> widening status
```

Weak media routing should widen by:

- increasing representative top-k;
- including sibling clusters or parent folders;
- trying OCR/caption FTS if visual routing is weak;
- trying SigLIP visual routing if caption/OCR routing is weak;
- including more roots;
- falling back to broader root-scoped fanout.

The result contract should distinguish:

- router score;
- lower evidence score;
- backend/profile used;
- route target;
- hydrated asset/document/object references;
- widening steps taken.

## Design Consequences

- `summary_nodes` or its successor should support modality, representative
  kind, route target, source references, exemplar media assets, generation
  profile, and sampling metadata.
- Representative rows should be separate from lower chunk/media rows.
- Generated captions, OCR, transcripts, labels, and embeddings should record
  provenance and model/profile metadata.
- Captions and summaries need confidence and provenance, but should not be
  treated as proof.
- Privacy policy matters more for media because images, OCR, EXIF, thumbnails,
  captions, and generated labels can reveal sensitive information.
- Root-scoped media stores remain the evidence layer.
- Global media representatives remain a routing layer.

## Explicit Non-Claims

- A missing caption does not mean the visual concept is absent.
- A single centroid does not adequately represent a heterogeneous root.
- Vector distances from different embedding profiles are not comparable.
- Captioning medoids is cheaper than captioning every image, but not free.
- 3D and video descriptions are not assumed current capabilities unless the
  repo adds explicit local producers for them.

## Compact Rule

```text
For media, route with a fusion of paths, metadata, OCR, captions, labels,
transcripts, summaries, and representative embeddings. For images, SigLIP
medoids are a strong native route. Prove with root-scoped media evidence.
```
