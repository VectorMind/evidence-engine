# Survey: Repository Consolidation Assessment

Date: 2026-06-11
Scope: `evidence-engine` (this repo), `C:\dev\VectorMind\private-documents`,
`C:\dev\VectorMind\private-media`.
Question: should the three repositories merge into one, and what should move
where?

## Conclusion First

Merge — but it is an **absorption, not a three-way code merge**. The two
private repos contain **no code and no generated data**. They hold four kinds
of content, each with a different correct destination:

| Content | Where it is today | Correct destination |
| --- | --- | --- |
| Layer-4 catalog schema designs (entities, faces, events, annotations, promotions) | `catalog.yaml` in both private repos | `evidence-engine` (public — these are capabilities, not personal facts) |
| Model/runtime documentation (face models, benchmark policy) | `private-media/models.md` | `evidence-engine/docs/models.md` (mostly superseded already) |
| Genuinely private markdown (real source maps, real paths) | `knowledge_base/` + config in both private repos | One single private knowledge base (repo or folder — open point) |
| Stale scaffolding (workflow docs, specs, plans referencing `agents-docs`) | Everywhere in both private repos | Nowhere — superseded; keep only as archived history |

After absorption both private repos can be archived. The end state is **two
locations, split by privacy of content, not by content type**:

```text
evidence-engine     public:  all Python, all schemas, all generic docs, CLI
private knowledge   private: one knowledge base — source maps, decisions, real config values
workspaces          not repos: any folder with .cache/even/ holding .db, indexes, embeddings
```

## What Each Repository Actually Contains

### evidence-engine (public, active)

- ~8,400 lines of Python under `src/even/` + tests; 18 commits; active open
  plan (`2026-06-06-global-routing-indexes`).
- `even` CLI (argparse, branching subcommand groups): `catalog`, `health`,
  `sources scan`, `docs parse`, `media inspect|describe|dedupe`,
  `index scope [--semantic|--image]`, `search text|semantic|hybrid|image`.
- Owns layers 1–3 of the five-layer model: source inventory, Docling parse,
  media metadata/captions, FTS (Tantivy), semantic (LanceDB/FastEmbed), image
  embeddings (SigLIP 2), hybrid RRF search.
- Generated data lives workspace-local under `.cache/even/` — already outside
  git by design.
- The `2026-06-07-knowledge-layers` packet (closed) already absorbed the
  generic media mechanics that `private-media` had planned (metadata
  extraction, thumbnails, captions, dedupe candidates, image embeddings,
  media search). That merge plan's repository-cut decisions are partially
  superseded by this survey (see "What Changed Since the Knowledge-Layers
  Merge Plan" below).

### private-documents (4 commits, dormant)

- **No code.** No pyproject, no src.
- `catalog.yaml` (v0.2): private overlay catalog design — `annotations`,
  `entities`, `entity_aliases`, `entity_links`, `private_notes`,
  `knowledge_promotions`. **Generic, well-developed layer-4 design with zero
  personal facts.** Valuable; not yet represented in evidence-engine.
- `knowledge_base/data-sources.md`: **genuinely private** — real OneDrive and
  Google Drive folder map (banking, tax, health-insurance, family, identity
  folder names).
- `config/document-index.yaml`: stale lower-layer wiring (`agents-cli` repo,
  `agents-docs` CLI, `$HOME/.cache/agents-docs`) — none of which exist
  anymore — plus one real private source path (first-run scope).
- `specifications/codebase-shape/spec.md`, `WORKFLOW.md`, `AGENTS.md`,
  README mermaid workflow: all reference the dead `agents-docs` surface and a
  fixed home-cache layout that evidence-engine replaced with workspace-local
  `.cache/even/`. Stale.
- `memory/` and `.cache/`: empty. **No runtime data was ever produced.**

### private-media (5 commits, dormant, last commit "anonymized repo for the future")

- **No code despite a full pyproject.toml.** It declares a `media-manager`
  package (`media_manager.cli:app`) with heavy deps (insightface, open-clip,
  sentence-transformers, streamlit, onnxruntime, openai) but `src/` does not
  exist. The dependency design survives as documentation only.
- `catalog.yaml` (v0.1): the richest layer-4 design of the three repos —
  `source_items`, `media_assets`, `media_metadata`, `media_descriptions`,
  `geo_observations`, `entities`, `entity_aliases`, `entity_attributes`,
  `media_entity_links`, `face_observations`, `face_clusters`,
  `semantic_events`, `event_links`, `model_observations`, `embeddings`,
  `review_tasks`, `duplicate_candidates`, `run_manifests`,
  `benchmark_results`. Already anonymized (`${MEDIA_ROOT}`). Several of its
  lower tables are now redundant with evidence-engine's catalog
  (`source_items`, `media_assets`, `media_metadata`→`image_metadata`/
  `video_metadata`, `media_descriptions`→`media_observations`,
  `duplicate_candidates`→`media_dedupe_candidates`, `embeddings`→
  `image_stores`/`semantic_stores`). The upper tables (entities, faces,
  events, review, benchmarks) are **not** redundant — they are the missing
  layer 4.
- `models.md`: superseded by `evidence-engine/docs/models.md` except the face
  recognition model table (InsightFace CPU/GPU, dlib fallback) and the
  benchmark-before-selection policy.
- `knowledge_base/data-sources.md`: anonymized; near-zero unique content.
- `memory/` and `.cache/`: empty. **No runtime data was ever produced.**

## Why Separation No Longer Pays

The original reason for separate private repos was the assumption that
private workflows would need hard-coded personal facts in code and config.
That assumption did not survive contact:

1. **Capabilities are not private.** Face recognition, trip/event grouping,
   entity linking, review queues — the *code and schemas* are generic. Only
   the *data instances* (which face is whom, which trip happened) are
   private, and those live in `.db` files and indexes that never belong in
   git anyway. Both private catalog.yaml files prove this: they were written
   without a single personal fact in them.
2. **The runtime data already escaped git.** evidence-engine's workspace
   model (`.cache/even/` in any caller folder) means the private state
   attaches to a *folder*, not a *repository*. A private workspace does not
   need to be a git repo at all.
3. **The private repos never accumulated anything.** Empty `.cache/`, empty
   `memory/`, 4–5 commits, no code. Two years of standard monorepo
   counterarguments (release cadence, access control, team boundaries, CI
   weight) all evaluate to zero here: one maintainer, no releases, no CI, no
   data.
4. **Three repos triple the convention surface.** Each repo carries its own
   AGENTS.md/WORKFLOW.md/specs/plans that already drifted (both private repos
   still describe the dead `agents-docs` layer). One repo means one
   convention set that stays current.
5. **The knowledge base fragments by content type for no reason.** Document
   knowledge and media knowledge link to the same entities (a trip has photos
   *and* booking PDFs). One private knowledge base serves both.

## What Remains Genuinely Private

Only two files plus history:

- `private-documents/knowledge_base/data-sources.md` — real folder map.
- `private-documents/config/document-index.yaml` — one real source path.
- **Git history**: private-documents history contains the real folder map in
  all 4 commits; private-media history before the anonymization commit may
  contain real paths. Both repos must therefore stay private even after
  archival — never flip them public.

## What Changed Since the Knowledge-Layers Merge Plan

`plans/2026-06-07-knowledge-layers/merge-plan.md` listed "one huge monolithic
private repo" as an anti-goal and proposed thin `personal-documents` /
`personal-media` workspace repos. Two updates:

- The anti-goal stands for *private data* — nothing here proposes committing
  databases or personal markdown to one big repo. What changed is the
  realization that the **workspace repos have no content of their own**: their
  schemas are public-grade, their runtime state is workspace-local, and their
  knowledge is better unified. So they collapse to (a) schema contributions to
  the public engine and (b) one private knowledge base.
- The merge plan's steps 3–5 ("move generic media mechanics into engine",
  "move private semantics into workspaces", "stabilize shared contracts") are
  exactly what happened / what this consolidation completes — with the
  correction that "workspaces" are folders + one knowledge base, not two
  per-content-type repos.

## Future Private Python Scripts

Question raised: will vibe-coded higher layers need a private code repo?
Assessment: default no.

- Higher-layer orchestration with no personal facts → public, in
  evidence-engine (new CLI branches or `scripts/`).
- One-off truly personal scripts → scratch area of the private knowledge
  base, untracked or tracked there; promote the generic core to
  evidence-engine when it stabilizes.
- A real application on top (UI, service) → its own repo **when it exists**,
  consuming `even` as a dependency. Do not pre-create it.

## Inputs Reviewed

- evidence-engine: README.md, AGENTS.md, WORKFLOW.md, pyproject.toml,
  catalog.yaml, docs/models.md, src/even/cli.py, plans/open.md,
  plans/closed.md, plans/2026-06-07-knowledge-layers/merge-plan.md.
- private-documents: full tree (19 files), git log, git status.
- private-media: full tree (20 files), git log, git status.
