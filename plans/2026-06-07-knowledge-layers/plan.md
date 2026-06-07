# Plan: Knowledge Layers Merge

Date: 2026-06-07
Status: Draft decision plan. Updated after OP/DD review.

## Problem Summary

The repo has a working lower document cache CLI under the old `documents-manager` /
`documents-manager` identity. It already owns scan, parse, FTS, semantic, hybrid
search, result folders, and the current-state SQLite catalog.

The broader architecture now needs a clearer merge target:

```text
documents-manager
  public reusable evidence engine for documents, generic media, indexes, and provenance

private-documents
  private workspace for source policy, private catalog, review, and curated knowledge

private-media
  private workspace for media entities, places, family context, faces, events, and media knowledge
```

This is still beta/pre-development work with no deployed compatibility burden.
Existing command names, generated catalogs, cache layout, and old `.db` files
may be reset if that keeps the new design clean.

The risk is over-merging: putting private semantics, personal source choices,
media identity review, topic logic, and lower extraction/indexing into one
unclear repository or one unclear CLI.

The plan also has to leave room for
`plans/2026-06-06-global-routing-indexes`: broad search should later use
document, folder, root, or cluster-level representative indexes for routing,
while chunk-level FTS/vector indexes and catalog evidence remain the proof
layer.

## Resolution Summary

Converge on `documents-manager` as the public repo and CLI direction. In
technical language, this repo is the reusable **evidence engine**.

Accepted direction:

- Start fresh. Do not preserve `documents-manager` as a compatibility alias unless a
  future real deployment creates that need.
- No migration burden for old beta catalogs. Wiping generated catalogs/indexes
  during the rename and schema reset is acceptable.
- Current `documents-manager` behavior becomes the implementation base of
  `documents-manager`, but the public CLI should be renamed and simplified.
- Generic media mechanics move into `documents-manager`: file detection,
  metadata, thumbnails/artifacts, shallow generated descriptions, duplicate
  candidates, media search projections, and evidence refs.
- The current media-manager role is reduced and renamed to `private-media`.
  It keeps private media meaning: entities, places, family context, face
  review, same-face yes/no decisions, reviewed identity, trips, events, albums,
  and curated media knowledge.
- `private-documents` keeps source manifests, policies, private annotations,
  reviewed semantic rows, review results, promotion choices, and curated
  Markdown knowledge. The exact split between private DB knowledge and
  versioned Markdown knowledge is deferred to private repo planning.
- Catalogs are open data APIs to each other. The public engine exposes schema,
  SQLite `.db` data, result JSON, and search access. Higher layers read that
  data directly.
- Dependencies are one-way: private workspaces may know public catalog/schema
  contracts; the public engine must not know private catalogs. If a concept is
  needed by the public engine, it moves into the public code/schema contract.
- Public means public code, schemas, templates, and synthetic fixtures. Real
  data is private, including generated OCR, captions, embeddings, indexes,
  catalogs, paths, review decisions, and knowledge.
- Search is the exception to direct open-data access: higher layers should not
  know FTS/vector projection internals, so they use the public search CLI/API
  and hydrated JSON results.
- Search backend names should be abstracted at the public surface. The public
  vocabulary is `text`, `semantic`, and `hybrid`; implementation names such as
  Tantivy and LanceDB stay internal or diagnostic.
- Command results and reports should move to the caller workspace root instead
  of one shared home-cache `results/` and `reports/` tree.
- Search projections are rebuildable. Reviewed semantic facts and review
  results are private durable state.
- Generated summaries and descriptions are generated observations or routing
  material only. They are never evidence and never proof of absence.
- `handoff` is deferred. It is too speculative for V1 because topic consumers
  and their logic are out of scope. This repo should expose evidence links,
  open catalog data, and search; higher layers can decide how deeply to
  investigate.
- A future command schema/transport layer is deferred. It must not commit to
  MCP compatibility. It can be MCP-inspired at most, and a safer future shape
  is likely normal CLI arguments by default with optional `--input <json-file>`
  for larger structured calls.

Best lessons from the surveyed systems:

- Docling, Unstructured, and Tika: lower extraction producers, not semantic
  truth owners.
- Paperless-ngx: practical source/document workflow, tags, custom fields, and
  review UX are useful references.
- Immich and digiKam: media assets, EXIF, thumbnails, faces, duplicates, and
  sidecar durability are useful media references.
- Dogsheep and HPI: local SQLite and source adapters are a strong model for
  private personal data control.
- Graphiti, GraphRAG, LightRAG, RAPTOR, HippoRAG, and RAG-Anything:
  multi-resolution graph/vector/summary retrieval is useful as projection and
  routing, not as unreviewed truth.
- W3C PROV, RO-Crate, and OpenLineage: evidence refs and producer runs need
  explicit provenance. Packaging standards can be revisited later if topic
  exports become real.
- Obsidian, Logseq, and Zotero: Markdown knowledge should be curated,
  human-readable, and citation/provenance aware, not a raw OCR dump.

## Analysis

### Current CLI Surface

Current executable: `documents-manager`

| Command | Subcommands | Main purpose |
| --- | --- | --- |
| `catalog` | `create`, `migrate`, `status` | Create, upgrade, and inspect the fixed SQLite catalog. |
| `health` | none | Check paths and optional dependencies. |
| `scan` | `folder <path>` | Inventory a folder tree into source roots/items and stats. |
| `parse` | `folder <path>` | Auto-scan, parse documents through Docling, and store artifacts/objects. |
| `index` | `folder <path>` | Build root-scoped FTS; `--semantic` builds vector search. |
| `search` | `text`, `semantic`, `hybrid` | Search current lower indexes and hydrate chunk provenance. |

Current behavior to replace or revise:

- executable name should become `documents-manager`;
- `scan folder` should move to `sources scan`;
- generated `results/` and `reports/` should move under the caller workspace,
  not a shared home cache;
- old catalog migration compatibility is not required;
- public command output should become schema-compliant JSON rather than compact
  human summaries when called as an API surface.

Current constraints worth preserving:

- current-state SQLite catalog;
- no generated chunk tables in SQLite;
- lower search rows hydrate back to catalog object refs;
- FTS/vector implementation details are hidden behind search commands.

### Proposed CLI Surface

Target executable: `documents-manager`

No V1 backward compatibility alias is required.

Proposed rule: avoid a vague catch-all `manage` root. Use direct nouns for the
things users operate.

| Command | Subcommands | Scope | Main purpose |
| --- | --- | --- | --- |
| `catalog` | `create`, `status`, `wipe` | Public engine | Create, inspect, or reset the generated catalog. No old beta migration burden. |
| `health` | none | Public engine | Check local runtime, workspace paths, and optional dependencies. |
| `sources` | `scan <path>`, `status` | Public engine | Treat folders as mixed-content source scopes before choosing processors. |
| `docs` | `parse <scope-or-path>` | Public engine | Run document extraction and normalize document objects. |
| `media` | `inspect <scope-or-path>`, `describe <scope-or-path>`, `dedupe <scope-or-path>` | Public engine | Run generic media evidence work without private identity semantics. |
| `index` | `scope <scope-or-path>`, `global`, `status` | Public engine | Build deep chunk indexes per scope and later high-level representative routing indexes. |
| `search` | `text <query>`, `semantic <query>`, `hybrid <query>` | Public engine | Search available evidence projections and hydrate catalog/evidence refs. |
| `schema` | `list`, `show <command-or-contract>` | Public engine | Return JSON schemas for CLI inputs, outputs, catalog contracts, and result payloads. |

Notes:

- No `manage` root in V1.
- No `handoff` root in V1. Future export or packaging flows can be planned
  after real private/topic use cases exist.
- `sources scan` replaces `scan folder`.
- `media scan` should not exist. Source discovery stays under `sources scan`;
  media commands inspect, enrich, dedupe, and search media evidence.
- `docs` and `media` are processors over source scopes, not separate source
  authorities.
- `search` is shared. Avoid duplicate `docs search` and `media search` unless a
  later UX test proves modality-specific aliases are needed.
- `index global` is reserved for the routing-index plan. It should build
  document/folder/root-level representative FTS first, and semantic
  representatives later.

### Public Data Contract

The public contract is not primarily a functional transfer API. It is open
local data plus a search access surface:

| Surface | Access | Purpose |
| --- | --- | --- |
| Schema files | Public schema files and `schema` command | Define catalog, command input/output, result, and evidence-ref contracts. |
| Catalog `.db` | Readable local SQLite database | Lets private repos inspect source, document, object, media, index, and provenance state. |
| Result JSON | Workspace-local result files | Gives run-level proof, status, diagnostics, and links. |
| Reports | Workspace-local report files | Optional human reports generated for the caller workspace. |
| Search CLI/API | Public command/API with JSON output | Lets higher layers query FTS/vector/hybrid projections without knowing projection internals. |
| Evidence refs | Data shape in catalog/results | Lets private rows and search hits point back to concrete public evidence rows. |

No private repo should need a public-engine callback just to read catalog state.
It can open the SQLite database read-only and query the schema. Search is
different because FTS/vector projection internals are implementation details.

### Command Output And Future Schema Surface

V1 should start with CLI commands that return schema-compliant JSON and write
bounded result files in the caller workspace when persistence is useful.

The command shape should be close to MCP-style function calls:

```text
schema describes input and output
command receives explicit CLI arguments by default
command returns JSON on stdout
result file stores larger run proof when needed
optional future --input reads structured JSON from a file
```

Future direction:

- optionally add JSON schema discovery if private callers need validation;
- optionally add `--input <json-file>` for larger structured requests;
- only later consider a long-lived stdio transport if process startup and
  result files become expensive;
- keep any future transport schema-compatible with the CLI;
- do not expose FTS/vector backend internals through either transport;
- prefer JSON schema contracts before adding any richer RPC machinery.

This is deferred and should not distract from the current implementation.

### Private Workspace Scope

| Workspace | Owns | Does not own |
| --- | --- | --- |
| `private-documents` | Source manifests, policies, private annotations, reviewed rows, review results, promotion choices, curated Markdown knowledge. | Docling, OCR internals, chunking, FTS/vector internals, generic scan/index/search code. |
| `private-media` | Entities, places, family context, private aliases, face review, same-face yes/no decisions, trips, events, albums, curated media knowledge. | Generic file inventory, EXIF/container extraction, thumbnails, generic captions, duplicate candidate generation, FTS/vector mechanics. |

The split between private DB knowledge, versioned Markdown knowledge, and any
future user-specific knowledge repo is deferred to private repo planning.

### Layer Contract

Use the same layer rule everywhere:

```text
Lower schemas describe what was observed and generated.
Upper schemas describe what was believed, reviewed, promoted, or used.
```

Target layers:

```text
source authority
  -> source items
    -> typed evidence objects
      -> generated observations
        -> search projections
          -> private review and semantic facts
            -> curated knowledge
```

The stable stitching primitive is:

```text
catalog row identity + evidence_ref + provenance
```

### Global Routing Fit

The global routing index plan stays separate. It should plug into `index
global` and `search` without changing the core knowledge-layer boundary.

Routing indexes should contain high-level representatives such as:

- root summaries;
- folder summaries;
- document summaries;
- media cluster summaries;
- optional negative summaries for included but low-value areas.

Routing rules:

- representatives route;
- deep FTS/vector indexes prove;
- summaries cannot prove absence;
- weak routing widens to more scopes;
- representative rows hydrate back to catalog refs and source scopes;
- global semantic routing waits until global FTS routing is useful.

## Scope

This planning packet covers:

- repository role split;
- public/private storage boundary;
- target CLI surface;
- JSON-first CLI direction;
- workspace-local results and reports;
- open catalog/search data contract;
- private-document and private-media scope;
- evidence ref as the merge kernel;
- relationship to global routing indexes;
- first implementation slice and remaining open points.

## Non-Goals

- No code implementation in this packet.
- No private source paths, facts, entities, images, OCR text, or embeddings in
  public repo files.
- No media identity, face identity, trip, vehicle, family, tax, medical, or
  rental semantics inside the public lower engine.
- No handoff/export CLI in V1.
- No topic-manager abstraction in this repo.
- No answer synthesis before search hit retrieval and evidence refs are stable.
- No global vector routing as a prerequisite for the next slice.
- No refactor of `private-documents` or `private-media` inside this public repo
  plan.

## First Slice

The smallest useful merge slice:

1. Rename the public command/package direction from `documents-manager` /
   `documents-manager` to `documents-manager`.
2. Use "evidence engine" as the technical description of this public repo.
3. Remove backward-compatibility assumptions and allow generated beta catalog
   reset/wipe.
4. Move `scan folder` to `sources scan`.
5. Define workspace-local output locations for result JSON and reports.
6. Define the public data contract: schema files, readable SQLite `.db`, result
   JSON, and search CLI/API.
7. Make search CLI output schema-compliant JSON and abstract all backend
   details behind `text`, `semantic`, and `hybrid`.
8. Defer schema discovery and any `--input <json-file>` shape until the core
   CLI is settled.
9. Define a minimal evidence-ref shape that points to public catalog rows and
   carries locator/provenance fields.
10. Add generic media detection and shallow media description planning without
    private identity.
11. Cross-link global routing as a separate plan and reserve `index global`.

## Milestones

### Phase 0: Decision Review

- Record accepted design decisions from this review.
- Confirm `documents-manager` as the public repo/CLI direction.
- Confirm "evidence engine" as the technical description.
- Confirm no compatibility alias and no old beta migration burden.
- Confirm `manage` and `handoff` are not V1 command roots.

Exit: no blocking DD remains for naming, dependency direction, and CLI shape.

### Phase 1: Contract Documentation

- Update README/spec language from document corpus cache toward public evidence
  engine.
- Define the open data contract: schema, SQLite `.db`, result files, and search
  access.
- Define evidence refs as data references into the catalog, not as a
  functional transfer API.
- Document that public code/schemas are publishable while real generated data
  stays private.

Exit: docs describe the public/private split without requiring code changes.

### Phase 2: CLI And Workspace Output Reset

- Rename the executable direction to `documents-manager`.
- Replace `scan folder` with `sources scan`.
- Move results/reports to caller workspace output.
- Treat existing beta catalogs and indexes as disposable.

Exit: commands follow the new top-level CLI shape and output locations.

### Phase 3: JSON CLI Surface

- Make command stdout JSON-first for API use.
- Keep result files for larger run proof and reports.
- Keep human summaries as optional presentation, not the primary API payload.
- Defer schema discovery, `--input <json-file>`, and any long-lived transport.

Exit: higher layers can call commands and validate outputs without scraping
terminal text.

### Phase 4: Generic Media Lower Layer

- Add media source classification from existing source inventory.
- Add generic media asset/artifact/observation contracts.
- Allow shallow generated descriptions as observations.
- Keep identities and reviewed personal meaning out of the public schema.

Exit: a mixed folder can show document and media evidence rows with refs.

### Phase 5: Private Overlay Boundaries

- Define the private overlay boundary without implementing private repos here.
- Define the one-way dependency rule: private knows public, public does not
  know private.
- Define review results as private scope.
- Defer DB-vs-Markdown knowledge split to private repo planning.

Exit: private workspaces can reference public catalog rows without copying
them and without circular dependencies.

### Phase 6: Search Access Contract

- Keep deep projection internals hidden.
- Ensure search results hydrate to catalog rows and evidence refs.
- Define the minimum result shape higher layers can rely on.

Exit: higher layers can combine direct SQLite reads with JSON search results.

### Phase 7: Global Routing Alignment

- Reconcile this plan with `plans/2026-06-06-global-routing-indexes`.
- Decide summary-node schema and representative index registry behavior in that
  separate packet.
- Keep representative global indexes at document/folder/root level, not chunk
  truth.

Exit: `index global` and `search hybrid` have a clear routing contract.

## Open Points

Only implementation-shape points remain here. Most former OPs are now accepted
design decisions.

| ID | Point | Proposal | Proposal confidence | Option shape |
| --- | --- | --- | --- | --- |
| OP-001 | Exact caller-workspace output layout for catalog, results, reports, and generated indexes. | Use a workspace-local hidden folder such as `.documents-manager/` with `catalog/`, `results/`, `reports/`, `fts/`, `semantic/`, and `blobs/` beneath it. | Medium | Several viable options. |
| OP-002 | Future structured input shape. | Defer. If needed, prefer optional `--input <json-file>` over stdin by default. | Medium | Several viable options. |
| OP-003 | Future schema/transport surface. | Defer. Not MCP-compatible; MCP-inspired at most. First keep CLI JSON and result files clean. | High | One obvious option. |
| OP-004 | Default behavior for shallow media descriptions. | Allow a cheap one-sentence class-aware description as a generated observation, but keep deeper entity/location/face analysis in private layers. Decide default-on versus profile-only during implementation. | Medium | Several viable options. |

## Design Decisions

| ID | Decision | Resolution | Status |
| --- | --- | --- | --- |
| DD-001 | Is `documents-manager` the public engine name? | Yes. Use `documents-manager` as the public repo/CLI direction and "evidence engine" as the technical term. | Accepted |
| DD-002 | Should a `manage` root remain in the CLI? | No. Use direct command nouns instead. | Accepted |
| DD-003 | What belongs in public media support? | Generic media evidence only: metadata, artifacts, shallow descriptions, duplicate candidates, and search projections. | Accepted |
| DD-004 | What belongs in `private-media`? | Entities, places, family context, faces, same-face yes/no review, reviewed identity, trips, events, albums, and media knowledge. | Accepted |
| DD-005 | What belongs in `private-documents`? | Source policy, private annotations, review results, reviewed rows, promotion choices, and curated knowledge. Details can be refined later. | Accepted |
| DD-006 | Should private catalogs copy lower catalog rows? | No. Catalogs are open data APIs to each other. Private repos reference public catalog rows; they do not copy lower rows by default. | Accepted |
| DD-007 | What is the public contract? | The full catalog/schema/SQLite `.db`, result files, and evidence refs are open local data. Search is provided through an API/CLI because projection internals are hidden. | Accepted |
| DD-008 | Are global routing summaries evidence? | No. Summaries are routing material only and must never be treated as evidence or proof of absence. | Accepted |
| DD-009 | Should global semantic routing be part of this plan? | No. Defer to the separate global-routing-indexes plan. | Accepted |
| DD-010 | Should review logic and review results live in public engine tables? | No. Personal review logic and results belong to private scope. | Accepted |
| DD-011 | Should this repo define what topic managers do? | No. This repo exposes search, catalog data, and evidence links. Higher layers are free to lead deeper investigations. | Accepted |
| DD-012 | Should Markdown knowledge duplicate extracted text? | No. Knowledge is curated and much smaller in volume, especially for hard-to-index material. | Accepted |
| DD-013 | Should `handoff` be V1 scope? | No. Defer handoff/export packaging until real consumer logic exists. | Accepted |
| DD-014 | Should `documents-manager` remain as backward compatibility alias? | No. This is beta/pre-development work; use a clean rename without compatibility burden. | Accepted |
| DD-015 | Are old generated catalogs/indexes migration targets? | No. Wipe/reset is acceptable during the rename and schema cleanup. | Accepted |
| DD-016 | Should `scan folder` remain? | No. Move source inventory to `sources scan <path>`. | Accepted |
| DD-017 | Should `media scan` exist? | No. Source scanning stays under `sources scan`; media gets `inspect`, `describe`, `dedupe`, and related enrichment commands. | Accepted |
| DD-018 | Should search expose backend names? | No. Public search names are `text`, `semantic`, and `hybrid`; engine names stay internal or diagnostic. | Accepted |
| DD-019 | Where should results and reports be written? | Caller workspace root, not a shared home-cache results/reports tree. | Accepted |
| DD-020 | Should private repo plans start now? | No. Do as little private planning as possible for now; focus public implementation first, then refactor private repos against real public contracts. | Accepted |
| DD-021 | Should generated media descriptions exist in the public engine? | Yes, as shallow generated observations. Deep analysis, identity, locations, and review belong in private layers. | Accepted |

## Exit Criteria

- The CLI surface is approved or amended.
- `private-documents` and `private-media` roles are clearly separated from the
  public evidence engine.
- The media-manager reduction path is accepted: generic mechanics move into
  `documents-manager`; private meaning stays in `private-media`.
- The public data contract is clear: readable catalog/schema/SQLite/result
  files plus search access for projection-backed retrieval.
- Search output is planned as schema-compliant JSON.
- Evidence refs are accepted as the merge kernel.
- `handoff` is clearly deferred and does not drive V1 implementation.
- The global routing index plan remains separate and compatible: high-level
  routing indexes route to lower proof indexes.
- Later implementation packets can start without re-litigating repository
  boundaries.
