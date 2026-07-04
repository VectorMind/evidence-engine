# Plan V2 Concept Draft: Global Routing Indexes With Media

Date: 2026-06-11
Status: Concept draft only. Not approved implementation scope.

## Purpose

This note records the media-specific routing ideas for a future full rework of
the global routing index plan.

The core question is how images, video, audio, and other media should
contribute to a global routing index when documents already use lossy summaries
from clustered text samples.

## Working Principle

Media should be treated as first-class routing material, but not forced into
the exact same representation as text documents.

```text
Media representatives route.
Root-scoped media indexes prove.
Generated captions and summaries are routing text, not truth.
```

The global index is a map of likely roots, folders, documents, clusters, and
media groups. It should not contain every image, frame, caption, transcript, or
embedding. It should contain representative signals that point downward into
root-scoped lower indexes.

## General Shape

A media item or media cluster can contribute several routing facets:

- filename, path, title, and surrounding document metadata;
- OCR text, if present;
- generated caption or visual summary;
- detected labels, objects, entities, or scene tags;
- visual embedding;
- transcript or audio-derived text for speech media;
- cluster membership;
- exemplar or medoid media object IDs;
- source document, page, frame, or timestamp references.

The global representative row should point to a route target rather than act as
final evidence.

Example:

```text
kind: image_cluster_summary
modality: image
root_id: research_archive
route_target: root/research_archive/images/cluster_17
routing_text: scanned receipts, handwritten notes, whiteboard photos, architecture diagrams
exemplar_object_ids: image_12, image_104, image_991
coverage_estimate: 340 images
confidence: medium
```

## Image Embeddings

Image embeddings make sense for global routing, but not as a global dump of all
image vectors.

Recommended pattern:

```text
per root or folder:
  cluster image embeddings
  keep selected centroid or medoid representatives globally
  keep full per-image embeddings only in the lower root-scoped media index
```

Search flow:

```text
text query, image query, or multimodal query
  -> global media representative index
  -> likely roots, folders, documents, or media clusters
  -> root-scoped image/media index
  -> actual media evidence
```

Do not mix unrelated embedding spaces. Text embeddings, image embeddings, audio
embeddings, and multimodal embeddings need separate profiles unless the chosen
model explicitly uses one shared embedding space.

## Generated Image Summaries

Generated captions and image summaries are useful, but should not be the only
media contribution to the global index.

Use generated text as one routing field among several:

```text
routing_text =
  path tokens
  filename tokens
  OCR text
  generated caption
  generated cluster summary
  detected labels
  selected metadata
```

A generated caption is lossy and can be wrong. It may route search toward a
candidate root or cluster, but it must not prove presence or absence.

Bad inference:

```text
The caption did not mention a signature, therefore no signature exists.
```

Good inference:

```text
The caption did not route strongly, so widen to nearby folders, sibling
clusters, OCR, filenames, or broader root-scoped media search.
```

## Media Version Of Lossy Summaries

The document plan uses clustered text samples to build lossy document or folder
summaries. For media, the equivalent is a lossy visual evidence pack.

Candidate sampling mix:

```text
40% visual cluster medoids or centroid-nearest media items
20% OCR-rich, entity-rich, or label-rich media items
15% filename, path, title, or metadata-rich items
15% random reservoir sample
10% recent, large, user-marked, or otherwise important items
```

The resulting summary describes the sampled media pack only. It is a routing
summary, not a complete statement about all media under the root.

## Routing Levels

Media can fit the same multi-resolution routing model:

```text
L0: root media summary
L1: folder, gallery, album, or collection summary
L2: document-level media summary, such as PDF figures or scanned pages
L3: visual cluster, scene group, screenshot group, or audio segment group
L4: actual image, frame, OCR block, caption, transcript, object, or timestamp
```

Candidate representative kinds:

- `root_media_summary`
- `folder_media_summary`
- `image_cluster_summary`
- `screenshot_cluster_summary`
- `diagram_cluster_summary`
- `scanned_document_summary`
- `video_scene_summary`
- `audio_transcript_summary`
- `archive_media_manifest`
- `negative_media_summary`

## Modality Notes

Images and photos:

- Use visual embeddings, captions, labels, EXIF-like metadata when allowed, and
  OCR where available.

Screenshots:

- OCR, UI text, filenames, app/window titles, and surrounding document context
  may be stronger than pure visual similarity.

Charts and diagrams:

- Keep OCR, figure captions, nearby document text, and source page references.
  Generated visual summaries are useful but risky as the only signal.

Video:

- Use transcript plus sampled keyframes and scene clusters. Route to video IDs
  and timestamp ranges, then search deeper within the root-scoped video index.

Audio:

- For speech, transcript is the primary routing text. Audio embeddings or
  sound-event labels can be later routing signals for non-speech media.

Archives:

- Use a manifest-level representative first. Do not unpack and index deeply
  unless policy allows it, the user opts in, or the manifest routes strongly.

## V1 Recommendation

The first media-aware version should keep global routing mostly textual:

```text
global representative FTS over media routing text:
  filenames
  paths
  OCR
  generated captions
  generated cluster summaries
  labels
  selected metadata
```

This avoids making global multimodal embeddings a prerequisite for the first
routing implementation. It also aligns with the existing recommendation that
global representative FTS should come before global representative LanceDB.

The proof layer remains root-scoped:

```text
root-scoped FTS:
  OCR
  captions
  transcripts
  metadata

root-scoped semantic/media indexes:
  image embeddings
  multimodal embeddings
  audio embeddings
  keyframe embeddings
```

## V2 And Later

After V1 proves useful, add global representative media embeddings:

- image cluster medoid or centroid embeddings;
- screenshot cluster representatives;
- video keyframe or scene representatives;
- audio segment representatives;
- multimodal representatives only when the selected model supports shared
  text-image or text-audio retrieval;
- image-to-image routing where the query itself is media.

The global embedding layer should stay representative-only. Full per-media
embeddings belong in lower root-scoped indexes unless repeated broad retrieval
justifies a materialized collection index.

## Search And Widening Behavior

The router should combine media and document representatives without pretending
their scores are directly comparable.

Recommended output shape should preserve route trace:

```text
query
  -> global representative hits
  -> selected roots/folders/media clusters
  -> lower root-scoped searches
  -> hydrated evidence hits
  -> widening status
```

Weak media routing should widen by:

- increasing representative top-k;
- including sibling clusters or parent folders;
- trying OCR/caption FTS if embedding routing is weak;
- trying visual embedding search if caption/OCR routing is weak;
- including more roots;
- falling back to broader root-scoped fanout.

## Design Consequences

- A summary node may need modality fields, such as `modality`, `media_kind`,
  `route_target_kind`, and exemplar media object IDs.
- Representative rows should be separate from lower chunk/media rows.
- Generated captions, OCR, transcripts, labels, and embeddings should record
  provenance and model/profile metadata.
- Generated summaries and captions must have confidence and coverage metadata.
- Media representatives must not prove absence.
- Privacy policy matters more for images because visual content, EXIF metadata,
  OCR, and generated labels can reveal sensitive information.

## Compact Rule

```text
For media, route with a fusion of filenames, metadata, OCR, captions, labels,
summaries, and representative embeddings. Prove with root-scoped media evidence.
```
