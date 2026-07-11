# Evidence Engine — Improvement Recommendations Handoff

## Purpose

This handoff captures the main architectural and implementation improvements recommended for `VectorMind/evidence-engine`.

The project has a strong core idea:

> Separate sources, machine-produced evidence, rebuildable retrieval projections, reviewed meaning, and curated knowledge.

That separation is worth preserving. The main work is not to redesign the project from scratch, but to make the implementation and persistence model fully honor the architecture it already claims.

---

## Executive Summary

The repository is directionally strong and differentiated from a typical RAG framework. Its most defensible position is:

> A local, provenance-aware evidence substrate that agents, humans, search systems, graphs, and domain knowledge layers can build on without confusing retrieval artifacts with reviewed truth.

The highest-priority improvements are:

1. **Introduce immutable evidence occurrences or revisions.**
2. **Separate durable Layer-4 review state from rebuildable Layers 1–3 state.**
3. **Materialize the full parsed document structure instead of one preview object per document.**
4. **Implement real recursive retrieval, not only routed fanout plus trace output.**
5. **Fix cross-index score fusion and global image-search scaling.**
6. **Make review operations transactional and historically auditable.**
7. **Build a retrieval and provenance evaluation harness before adding more retrieval modes.**

The most serious architectural defect is the current reference model:

> A durable accepted Layer-4 link can point to a mutable current-state Layer-2 row whose content changes after reparsing.

That must be fixed before the project can credibly support governed or certifiable workflows.

---

# 1. Preserve the Existing Layer Model

The current conceptual model should remain:

```text
Layer 5 — Knowledge
    Curated human and domain context

Layer 4 — Entities
    Proposed and reviewed meaning

Layer 3 — Indexes
    Rebuildable retrieval projections

Layer 2 — Evidence
    Machine-produced observations

Layer 1 — Sources
    Original supplied material
```

The key rule should remain:

```text
Sources describe what was supplied.
Evidence describes what was observed or generated.
Indexes describe rebuildable retrieval projections.
Entities describe reviewed or proposed meaning.
Knowledge describes curated human context and domain semantics.
```

This is the strongest part of the architecture.

The implementation work should therefore focus on enforcing these boundaries more strictly.

---

# 2. P0 — Fix the Evidence Identity Model

## Problem

Current evidence references point to mutable current-state rows, for example:

```text
corpus_cache.document_objects.obj_123
```

The same logical row ID can survive a source change while the underlying evidence content is replaced during reparsing.

This creates a dangerous sequence:

```text
1. Source revision A is parsed.
2. Evidence row obj_123 contains claim A.
3. A human accepts an entity link to obj_123.
4. The source changes.
5. The document is reparsed.
6. obj_123 is replaced with claim B.
7. The accepted entity link still resolves to obj_123.
8. The reviewed meaning has changed without a Layer-4 review event.
```

This violates the intended durability boundary between Layer 2 and Layer 4.

## Recommendation

Introduce two distinct identities.

### A. Logical current object identity

Represents the current conceptual location:

```text
logical_ref:
  corpus_cache.document_objects.obj_123
```

Use this when the caller explicitly wants to follow the latest current state.

### B. Immutable evidence occurrence identity

Represents the exact evidence that was reviewed:

```yaml
evidence_occurrence_id: evo_...
source_item_id: src_...
source_sha256: abc123...
producer: docling
producer_version: ...
profile: docling_ocr
object_fingerprint: def456...
locator:
  page_start: 17
  page_end: 17
  bbox: [...]
content_hash: ...
created_at: ...
```

Accepted Layer-4 links should normally pin an immutable evidence occurrence.

## Recommended model

```text
source_item
    │
    ├── current source state
    │
    └── source revisions
            │
            ▼
      extraction activity
            │
            ▼
   immutable evidence occurrence
            │
            ├── logical object mapping
            └── reviewed Layer-4 links
```

## Acceptance Criteria

- Reparsing a changed source cannot silently change the evidence resolved by an accepted Layer-4 link.
- A test exists for:
  - create source;
  - parse;
  - accept evidence link;
  - modify source;
  - reparse;
  - verify accepted link still resolves to the original reviewed evidence occurrence.
- Callers can explicitly choose:
  - exact historical evidence;
  - current logical object.
- Provenance includes enough information to reproduce or explain the occurrence.

---

# 3. P0 — Separate Durable Layer 4 from Rebuildable Layers 1–3

## Problem

Layers 1–4 currently share one SQLite catalog.

Yet:

- Layers 1–3 are explicitly rebuildable.
- Layer 4 is explicitly durable reviewed meaning.
- `catalog wipe` removes the whole database.

This means the physical persistence model contradicts the semantic architecture.

## Recommendation

Prefer a physical split:

```text
.even/
├── cache/
│   ├── evidence.sqlite
│   ├── fts/
│   ├── semantic/
│   └── routing/
└── state/
    └── entities.sqlite
```

Suggested responsibility:

### `evidence.sqlite`

Contains:

- sources;
- source revisions;
- extraction activities;
- evidence occurrences;
- index scopes;
- index registries;
- routing summaries.

May be wiped and rebuilt.

### `entities.sqlite`

Contains:

- entities;
- aliases;
- classifications;
- attributes;
- relationships;
- evidence bindings;
- review tasks;
- review decisions.

Must not be wiped by cache cleanup.

## Alternative

A single database can remain temporarily if all of the following exist:

- proper schema migrations;
- protected durable tables;
- backup before destructive operations;
- export/import of reviewed state;
- refusal to wipe when accepted rows exist unless explicitly forced.

The physical split is cleaner and better aligned with certifiable environments.

## Acceptance Criteria

- Rebuilding all evidence and indexes does not remove accepted Layer-4 state.
- Cache cleanup cannot delete reviewed meaning.
- Schema migration for Layer 4 is supported independently from evidence rebuilds.
- Durable state is backupable without copying transient index data.

---

# 4. P0 — Fully Materialize Parsed Document Structure

## Problem

The architecture advertises typed document evidence such as:

```text
page
section
paragraph
table
figure
diagram
image
chart
formula
codeblock
list
caption
```

But the current parser path effectively creates one synthetic paragraph object per document and indexes a short text preview.

The rich parser artifact is stored, but the normalized evidence and retrieval path do not yet expose its structure.

This makes the current implementation substantially weaker than the architectural promise.

## Recommendation

Build a real normalization pipeline:

```text
DoclingDocument
    │
    ▼
normalization adapter
    │
    ├── pages
    ├── sections
    ├── paragraphs
    ├── tables
    ├── figures
    ├── captions
    ├── formulas
    ├── code blocks
    └── hierarchy and locators
            │
            ▼
immutable evidence occurrences
            │
            ▼
multiple index projections
```

Each normalized object should preserve, when available:

- reading order;
- parent-child hierarchy;
- page span;
- bounding boxes;
- parser confidence;
- language;
- object type;
- source hash;
- producer and producer version;
- normalized content hash.

## Chunking

Do not make the evidence model equal to the chunk model.

Use:

```text
typed evidence objects
        │
        ├── lexical chunk projection
        ├── semantic chunk projection
        ├── table projection
        ├── figure/caption projection
        └── visual page projection
```

Chunks remain Layer-3 implementation details.

## Acceptance Criteria

- A multi-page PDF produces multiple typed evidence objects.
- Tables, figures, captions, formulas, and paragraphs remain distinguishable.
- Search results resolve to exact evidence objects, not only a document-level preview.
- Page and region locators survive hydration.
- A parser upgrade can rebuild evidence without changing accepted historical evidence occurrences.

---

# 5. P0 — Remove Review Semantics from Rebuildable Evidence

## Problem

The Layer-2 `valuable_items` concept includes review states such as:

```text
accepted
rejected
deferred
```

That mixes human judgment into a supposedly rebuildable layer.

## Recommendation

Layer 2 may contain:

```text
extraction_status
detection_confidence
quality_status
parser_status
```

Layer 4 should contain:

```text
review_status
accepted as important
rejected as irrelevant
promoted
deferred
```

Options:

1. Remove `review_status` from `valuable_items`.
2. Treat `valuable_items` as machine-generated candidates only.
3. Represent human decisions as:
   - classifications;
   - evidence links;
   - review tasks;
   - promotion decisions.

## Acceptance Criteria

- Rebuilding Layer 2 cannot destroy or overwrite a human decision.
- All human review decisions live in durable Layer 4.
- Machine confidence and human acceptance are represented separately.

---

# 6. P1 — Implement Actual Recursive Retrieval

## Problem

The architecture describes hierarchical deepening, but the current high-budget behavior is closer to:

```text
route to roots
    │
    ▼
search more roots
    │
    └── expose lower summaries in diagnostics
```

A true recursive system should be:

```text
root representatives
    │
    ▼
select roots
    │
    ▼
folder / album / cluster representatives
    │
    ▼
select regions
    │
    ▼
document / page / evidence retrieval
```

## Recommendation

Implement a routing ladder.

Example:

```text
L0 — root summaries
L1 — folder, album, cluster summaries
L2 — document or region summaries
L3 — evidence search
```

At each rung:

1. retrieve representatives;
2. select regions under budget;
3. record route trace;
4. recurse only into selected regions;
5. fall back or widen when confidence is weak.

## Query budgets

Suggested semantics:

### Low

```text
L0 → best scope → evidence
```

### Mid

```text
L0 → top scopes → optional L1 → evidence
```

### High

```text
L0 → L1 → L2 → evidence
+ controlled widening
+ complete diagnostics
```

## Acceptance Criteria

- High-budget queries perform additional retrieval decisions, not only produce additional trace data.
- A benchmark can compare:
  - exhaustive search;
  - root-only routing;
  - recursive routing.
- Route quality is measured independently from final retrieval quality.

---

# 7. P1 — Fix Cross-Island Ranking

## Problem

Separate FTS indexes use local BM25 statistics.

Raw scores from independent indexes should not be assumed to be globally comparable.

Current behavior effectively does:

```text
scope A raw BM25 score
scope B raw BM25 score
scope C raw BM25 score
        │
        ▼
global raw-score sort
```

## Recommendation

Use rank fusion or calibrated scoring.

Preferred first implementation:

```text
scope A ranking ─┐
scope B ranking ─┼─ RRF
scope C ranking ─┘
```

This is consistent with the project's existing hybrid-search approach.

Possible later improvements:

- z-score normalization per index;
- score calibration;
- learned fusion;
- corpus-size-aware ranking.

## Acceptance Criteria

- Independent FTS islands are combined by rank fusion or calibrated scores.
- Tests cover tiny versus large indexes.
- Retrieval evaluation compares current raw-score pooling with the new method.

---

# 8. P1 — Fix Global Image Search Scaling

## Problem

The current "central image union" is logically central but physically federated.

A query searches every compatible per-scope image store and merges the results.

Therefore:

```text
query fanout ≈ number of image stores
```

This is acceptable for a small number of roots but may become a bottleneck in a large multi-domain deployment.

## Recommendation

Choose one of three paths.

### Option A — True global image index

```text
global image store
  vector
  asset_id
  scope_id
  source metadata
```

Best for simple global similarity search.

### Option B — Visual router plus local proof stores

```text
global medoid index
        │
        ▼
select scopes
        │
        ▼
search selected local image stores
```

This best matches the current architecture.

### Option C — Hybrid threshold

Use all-store fanout below a configured store count and routed search above it.

## Recommendation

Option B is the most coherent continuation because the project already has medoid representatives.

## Acceptance Criteria

- Query fanout does not grow linearly without bound with store count.
- Pure visual recall is benchmarked against exhaustive federation.
- Routing loss is measurable.
- Scope count, latency, and recall trade-offs are visible in diagnostics.

---

# 9. P1 — Tighten the Conceptual Language Around Image Embeddings

## Problem

The architecture sometimes describes image embeddings as if they were the proof representation.

That weakens the otherwise strict evidence model.

## Recommendation

Use this terminology:

```text
Source:
    original image bytes

Evidence:
    media asset
    hash
    deterministic metadata
    generated observations

Projection:
    image embedding

Retrieval result:
    evidence reference to media asset
```

An embedding is a lossy Layer-3 retrieval projection.

It can locate evidence. It is not itself the evidence.

## Acceptance Criteria

- Documentation consistently distinguishes media evidence from vector projections.
- Search results always hydrate to evidence identities.
- Layer 4 never binds directly to a vector-store row.

---

# 10. P1 — Make Review Operations Transactional and Auditable

## Problem

A proposed evidence link and its review task can evolve independently.

Possible inconsistent state:

```text
review task: accepted
evidence link: proposed
```

The current status fields also represent only current state, not review history.

## Recommendation

Introduce an append-only review decision model.

Example:

```yaml
review_decision:
  decision_id: dec_...
  target_ref: layer4.entity_evidence_links.link_...
  decision: accepted
  reviewer: ...
  rationale: ...
  created_at: ...
```

Then update the target status in the same transaction.

Review commands should operate on a target, not independently on a task shadowing a target.

Suggested flow:

```text
proposal created
    │
    ▼
review task opened
    │
    ▼
review decision recorded
    │
    ├── target lifecycle updated
    └── task closed
```

## Acceptance Criteria

- A review action atomically:
  - records the decision;
  - updates the target;
  - closes or updates the task.
- Review history is append-only.
- Current status can be reconstructed from decision history.
- Reviewer identity and rationale can be retained when required.

---

# 11. P1 — Add Explicit Provenance Activities

## Problem

The current model contains useful hashes, producer names, profiles, and timestamps, but provenance is mostly represented as row columns.

For governed workflows, changed sources and extraction pipelines need clearer lineage.

## Recommendation

Introduce lightweight activity records.

Example:

```text
source revision
    │
    ▼ used by
extraction activity
    │
    ▼ generated
evidence occurrence
    │
    ▼ projected by
index build activity
```

Minimal activity fields:

```yaml
activity_id: act_...
activity_kind: parse | inspect | describe | index | summarize
producer: ...
producer_version: ...
profile: ...
config_hash: ...
started_at: ...
completed_at: ...
status: ...
```

Evidence rows then reference the generating activity.

This does not require adopting a large formal provenance framework. The goal is to preserve the useful distinctions:

- entity;
- activity;
- generation;
- usage;
- derivation;
- revision.

## Acceptance Criteria

- Every generated evidence occurrence can identify:
  - source revision;
  - generating activity;
  - producer;
  - profile/config.
- Rebuild diagnostics can explain why two evidence revisions differ.
- Provenance survives index rebuilds.

---

# 12. P2 — Add a Real Evaluation Harness

## Problem

The project has useful implementation tests but no demonstrated proof that the retrieval architecture improves quality, cost, or latency.

Without evaluation, routing remains a plausible hypothesis rather than a demonstrated advantage.

## Recommendation

Build an evaluation package before adding many new retrieval modes.

Suggested layout:

```text
evaluation/
├── datasets/
├── queries/
├── judgments/
├── runners/
├── metrics/
└── reports/
```

## Retrieval Metrics

At minimum:

```text
Recall@5
Recall@20
nDCG@10
MRR
```

## Routing Metrics

Measure:

```text
correct scope recall@1
correct scope recall@N
routing fanout
routing latency
routing token cost
```

Most important:

```text
routed recall
-------------
exhaustive recall
```

and:

> How much query cost is saved for each percentage point of recall lost?

## Compare Architectures

```text
A. exhaustive search
B. root routing
C. recursive routing
D. lexical only
E. semantic only
F. hybrid
G. hybrid + reranking
```

## Multimodal Evaluation

Measure separately:

```text
image → image
text → media metadata/caption
text + example image → routed multimodal evidence
visual document page retrieval
```

## Provenance Integrity Tests

Automate:

```text
accept evidence
change source
reparse
verify exact reviewed evidence remains stable
```

## Scale Tests

Measure:

```text
number of roots
number of files
number of FTS islands
number of vector stores
number of image stores
query p50
query p95
indexing throughput
storage overhead
routing token cost
```

## Acceptance Criteria

- Every retrieval architecture change is benchmarked.
- Routing quality and final retrieval quality are reported separately.
- Performance reports include quality/cost trade-offs.
- Regression thresholds can run in CI on a small deterministic benchmark.

---

# 13. P2 — Strengthen Schema Invariants

## Problem

Many schema semantics are expressed in YAML and Python conventions but not enforced strongly by SQLite.

For governed use, application discipline alone is not enough.

## Recommendation

Add where appropriate:

```text
NOT NULL
CHECK constraints
UNIQUE constraints
foreign keys
lifecycle invariants
```

Examples:

```text
confidence BETWEEN 0 AND 1

object_entity_id IS NOT NULL
OR object_value IS NOT NULL

accepted Layer-4 link requires immutable evidence occurrence

review task target must resolve

one current logical object mapping per logical object ID
```

Also add proper migrations instead of wipe/recreate once the beta phase ends.

## Acceptance Criteria

- Invalid lifecycle states cannot be written by direct database access.
- Schema upgrades preserve Layer-4 state.
- Migrations are versioned and tested.

---

# 14. Recommended Execution Order

## Phase 1 — Repair the trust model

```text
1. Immutable evidence occurrences
2. Source revision model
3. Durable Layer-4 storage boundary
4. Review decision history
```

Do not add major agentic extraction features before this foundation is stable.

## Phase 2 — Deliver the typed evidence core

```text
5. Full Docling structure normalization
6. Exact locators and provenance
7. Evidence-aware chunk generation
8. Table/figure/page evidence retrieval
```

This is the point where the implementation begins to match the architecture.

## Phase 3 — Make hierarchical retrieval real

```text
9. Cross-island rank fusion
10. Real recursive deepening
11. Visual routing at scale
12. Better fallback and widening policies
```

## Phase 4 — Prove it

```text
13. Evaluation harness
14. Retrieval quality baselines
15. Routing quality/cost benchmarks
16. Provenance integrity tests
17. Large multi-root scale tests
```

## Phase 5 — Add higher-level producers

Only after the evidence substrate is stable:

```text
18. Model-driven entity proposals
19. Graph extraction producers
20. Domain-specific promotion workflows
21. ALM ontology integration
```

All of these should write through the same Layer-4 review contract rather than bypassing it.

---

# 15. Suggested Target Architecture

```text
                         ┌──────────────────────────────┐
                         │ Layer 5 — Knowledge          │
                         │ curated Markdown/YAML        │
                         │ domain ontologies            │
                         └──────────────▲───────────────┘
                                        │ promotion
                         ┌──────────────┴───────────────┐
                         │ Layer 4 — Durable Meaning    │
                         │ entities                     │
                         │ relationships                │
                         │ reviewed evidence bindings   │
                         │ review decisions             │
                         └──────────────▲───────────────┘
                                        │ immutable refs
                         ┌──────────────┴───────────────┐
                         │ Layer 3 — Projections        │
                         │ FTS                          │
                         │ dense vectors                │
                         │ image vectors                │
                         │ routing summaries            │
                         │ medoids                      │
                         └──────────────▲───────────────┘
                                        │ generated from
                         ┌──────────────┴───────────────┐
                         │ Layer 2 — Evidence           │
                         │ immutable occurrences        │
                         │ typed document objects       │
                         │ media observations           │
                         │ extraction activities        │
                         └──────────────▲───────────────┘
                                        │ derived from
                         ┌──────────────┴───────────────┐
                         │ Layer 1 — Sources            │
                         │ logical source items         │
                         │ immutable source revisions   │
                         └──────────────────────────────┘
```

---

# 16. Positioning

The project should avoid positioning itself as:

> another RAG framework.

A stronger position is:

> Evidence Engine is a local evidence substrate for turning heterogeneous source material into provenance-rich, typed, rebuildable evidence that can be searched, reviewed, bound to durable entities, and promoted into domain knowledge without confusing retrieval artifacts with truth.

That position remains compatible with:

- Docling for document understanding;
- Tantivy for lexical retrieval;
- LanceDB or other vector stores;
- graph extraction pipelines;
- GraphRAG-like producers;
- visual document retrieval;
- domain ontologies such as ALM models;
- agentic workflows;
- human review.

The engine should remain the evidence and promotion substrate, not the owner of every domain workflow.

---

# 17. Immediate Next Actions

Recommended concrete next steps:

```text
[ ] Write an architectural decision record for immutable evidence identity.
[ ] Add a failing regression test for accepted-link drift after source change.
[ ] Design source_revision and evidence_occurrence tables.
[ ] Decide physical Layer-4 persistence boundary.
[ ] Replace single-preview document normalization with typed Docling objects.
[ ] Add rank fusion across FTS islands.
[ ] Define real recursive routing semantics and acceptance tests.
[ ] Create the first small retrieval benchmark corpus.
```

The first milestone should be considered complete when:

> An accepted entity-evidence link can be proven to remain tied to the exact reviewed evidence even after source changes, reparsing, reindexing, routing rebuilds, and parser upgrades.

That is the foundational trust property on which the rest of the architecture depends.
