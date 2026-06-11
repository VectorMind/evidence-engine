# Plan: Repository Consolidation

Date: 2026-06-11
Status: Proposed — awaiting maintainer review
Inputs: [survey.md](./survey.md)

## Problem Summary

Three repositories carry one system. `evidence-engine` holds all the code
(layers 1–3). `private-documents` and `private-media` were created on the
assumption that private workflows need private code, but ended up holding only
generic layer-4 schema designs, stale scaffolding pointed at the dead
`agents-docs` surface, and two files of genuinely private markdown. Both are
dormant (no code, empty caches, 4–5 commits). The split fragments conventions,
lets docs drift, and divides the future knowledge base by content type even
though documents and media share the same entities.

## Resolution Summary

Consolidate to **two locations split by privacy of content, not by content
type**, plus repo-less workspaces:

```text
evidence-engine        public monorepo: all Python, all schemas (layers 1–5
                       capabilities), all generic docs, the branching `even` CLI
private knowledge base private: ONE place for source maps, real config values,
                       decisions, curated personal markdown (location: OP-001)
workspaces             not repos: any folder with .cache/even/ holding catalogs,
                       indexes, embeddings, and private layer-4 .db instances
```

Absorb the private repos' reusable designs into evidence-engine, move their
private content into the single knowledge base, then archive both repos
(forever private — their histories contain personal facts).

## Goal And Objectives

Goal: one public engine repo and one private knowledge base, with nothing of
value left in the two dormant repos.

Objectives:

1. The layer-4 catalog designs from both private repos survive as one
   reconciled upper-catalog schema contract inside evidence-engine.
2. Unique model/runtime documentation (face models, benchmark policy) lands in
   `docs/models.md`.
3. All genuinely private content lives in exactly one private knowledge base.
4. Both private repos are archived with pointer READMEs and stay private.
5. No personal fact enters the public repo at any step.

## Scope And Non-Goals

In scope:

- Schema reconciliation (design documents only — no runtime code).
- Documentation merges.
- Creation/structuring of the single private knowledge base.
- Archival steps for the two private repos.

Non-goals:

- Implementing layer-4 runtime code (entities, faces, events, review queues,
  promotions) — each is its own future plan packet.
- Adding face-recognition dependencies (`insightface`, `onnxruntime`) to
  pyproject — record the intended extra shape only.
- Migrating or wiping any `.cache/even/` workspace data (none exists in the
  private repos anyway).
- Touching the open `2026-06-06-global-routing-indexes` plan; the packets are
  independent.
- Renaming/rebranding anything. `evidence-engine` / `even` stays.

## Open Points

| ID | Question | Status | Resolution |
| --- | --- | --- | --- |
| OP-001 | Where does the single private knowledge base live: a private git repo (e.g. `VectorMind/private-knowledge`) or a OneDrive folder? | Open | Recommend a **private git repo**: agents work better with diffable markdown and decision history; OneDrive roots are read-only *sources* in this system, and writing the knowledge base into a source root muddies the read-only contract. The repo's working copy can still sit under a synced folder if backup is wanted. |
| OP-002 | Does the layer-4 upper catalog live as new tables in `catalog.sqlite` or as a separate durable database in the workspace? | Open | Recommend a **separate `knowledge.sqlite`** beside the lower catalog (e.g. `.cache/even/knowledge/`): layer 2–3 state is rebuildable and `even catalog wipe` may destroy it; layer 4 is durable and must never be wiped by a re-parse. Cross-references use the existing `corpus_cache.<table>.<row_id>` ref convention. |
| OP-003 | What CLI branch names expose layer 4 later (`even facts`, `even entities`, `even review`, `even promote`)? | Open | Defer to the layer-4 implementation packet. This plan only reserves the principle: new top-level branches, same JSON-first contract. |
| OP-004 | Reuse one of the existing private repos as the knowledge base instead of creating a new one? | Open | Recommend **no**: both carry stale scaffolding in history and a misleading content-type name. A fresh `private-knowledge` repo starts clean; the old repos archive as-is. |
| OP-005 | Do any plan packets from the private repos move into evidence-engine `plans/`? | Open | Recommend no — they describe the superseded architecture. The survey records what mattered; archived repos keep the history. |

## Implementation Phases

### Phase 1 — Upper-catalog schema absorption (public, design only)

Reconcile the two private `catalog.yaml` designs into one layer-4 schema
contract in evidence-engine, as a new contract file (e.g.
`knowledge_catalog.yaml`) or a `specifications/` spec:

- From `private-documents/catalog.yaml`: `annotations`, `entities`,
  `entity_aliases`, `entity_links`, `private_notes`, `knowledge_promotions`.
- From `private-media/catalog.yaml`: keep the upper tables —
  `entity_attributes`, `media_entity_links`, `face_observations`,
  `face_clusters`, `semantic_events`, `event_links`, `review_tasks`,
  `run_manifests`, `benchmark_results`.
- Drop the private-media tables already covered by the lower catalog:
  `source_items`, `media_assets`, `media_metadata` (→ `image_metadata` /
  `video_metadata`), `media_descriptions` (→ `media_observations`),
  `duplicate_candidates` (→ `media_dedupe_candidates`), `embeddings`
  (→ `image_stores` / `semantic_stores`), `geo_observations` (→ GPS columns
  in `image_metadata` / `video_metadata`; promote to a table only if needed),
  `model_observations` (→ `media_observations`; extend enum if needed).
- Merge the two `entities`/`entity_aliases` designs into one (the document
  and media variants differ only in enum values).
- Target refs at the current lower catalog (`corpus_cache.<table>.<row_id>`),
  replacing the dead `tantivy_indexes`/`lancedb_stores` names with
  `fts_indexes`/`semantic_stores`/`image_stores`.
- Mark durability explicitly: layer-4 rows are durable and excluded from any
  wipe/rebuild path (per OP-002).

### Phase 2 — Documentation absorption (public)

- Merge the unique parts of `private-media/models.md` into `docs/models.md`:
  the face-recognition model table (InsightFace ONNX CPU/GPU, dlib fallback,
  hosted face APIs excluded) and the benchmark-before-selection policy.
- Record the intended future pyproject extra shape (e.g. `faces =
  ["insightface", "onnxruntime"]`) in `docs/models.md` or
  `docs/dependencies.md` without adding the dependencies.
- Add a short "workspaces are folders, not repos" clarification to README's
  Public And Private Split section, stating that layers 4–5 capabilities are
  public code/schemas while their data instances live in workspaces and the
  private knowledge base.

### Phase 3 — Single private knowledge base (private)

- Create the knowledge base at the OP-001 location with a minimal shape:

  ```text
  private-knowledge/
    README.md            # what lives here, link back to evidence-engine
    sources/             # source maps (the real folder/path inventory)
    decisions/           # dated decision notes promoted from reviews
    topics/              # per-topic curated knowledge (trips, vehicle, tax, ...)
    config/              # real workspace config values (paths, scopes)
    scratch/             # one-off private scripts/notes; promote or delete
  ```

- Move into it: `private-documents/knowledge_base/data-sources.md` (the real
  source map), the real first-run source path from
  `private-documents/config/document-index.yaml`, and anything still useful
  from `private-media/knowledge_base/data-sources.md`.
- Rewrite the moved config fragment against the current `even` surface
  (workspace `.cache/even/`, `even sources scan` etc.) so the knowledge base
  starts correct, not stale.

### Phase 4 — Archive the private repos (maintainer git/GitHub actions)

- Replace each repo's README body with a short pointer: superseded by
  `evidence-engine` (code/schemas) and the private knowledge base (content),
  with the date and a link to this plan packet.
- Archive both repos on GitHub. **They must remain private permanently**:
  `private-documents` history contains the real folder map in every commit;
  `private-media` history predates its anonymization commit.
- Per WORKFLOW.md the maintainer owns all git operations; assistants prepare
  file changes only.

### Phase 5 — Follow-up packets (out of scope, listed for continuity)

- Layer-4 runtime: upper catalog creation, `even entities|review|promote`
  CLI branches (OP-003), durable-db handling (OP-002).
- Face pipeline: `faces` extra, detection/embedding/cluster commands writing
  `face_observations`/`face_clusters`.
- Events/trips: `semantic_events` grouping over capture time + GPS.

## Dependencies And Risks

- No dependency on the open `global-routing-indexes` packet; both can proceed
  independently.
- **Risk: leaking personal facts into the public repo** while moving content.
  Mitigation: Phase 1–2 touch only already-generic material; Phase 3 moves
  private files exclusively toward the private location; review the public
  diff for paths/names before commit.
- **Risk: losing design nuance when reconciling the two catalog schemas.**
  Mitigation: reconciliation is additive; the archived repos retain the
  originals; survey.md records the table-level mapping.
- **Risk: accidental future publication of archived repos.** Mitigation:
  pointer READMEs state explicitly that history contains personal facts and
  the repos must never be made public.

## Exit Criteria

1. A reconciled layer-4 schema contract exists in evidence-engine, with the
   redundant-table mapping documented, and contains no personal facts.
2. `docs/models.md` covers face models and the benchmark policy.
3. The single private knowledge base exists and contains the source maps and
   real config values formerly in the private repos, rewritten against the
   current `even` surface.
4. Both private repos carry pointer READMEs and are archived on GitHub,
   still private.
5. `plans/open.md` / `plans/closed.md` updated; implementation.md and test.md
   in this packet record what was done and how it was checked.
