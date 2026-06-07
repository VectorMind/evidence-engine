# Merge Plan: `documents-manager` Consolidation

Status: Draft handover  
Purpose: Capture the intended repository cut, CLI shape, and layer consolidation strategy for merging the current `agents-cli`, `documents-manager`, and `media-manager` ideas into a simpler public/private structure.

---

## 1. Core Decision

The project should converge around one plain public engine name:

```text
documents-manager
```

This replaces the older `agents-cli` identity.

The name is intentionally not grand or abstract. It says what the tool does: it manages documents and related personal files. Even if the system later handles photos, screenshots, scans, emails, videos, tables, archives, and generated semantic layers, “documents” remains understandable and non-intimidating.

The goal is not to market a platform. The goal is to make a practical local file/document/media indexing and management CLI.

---

## 2. Main Repository Cut

The split should be based on privacy and runtime responsibility, not on over-theorized architecture.

```text
documents-manager
  public reusable engine, schemas, CLI, synthetic fixtures

personal-documents
  user workspace for document source scopes, private catalog, knowledge base, handoffs

personal-media
  user workspace for media source scopes, entities, review, and media knowledge

private knowledge repos
  only needed when committed Markdown contains personal facts
```

The important distinction:

- code and schema can be public;
- real data, indexes, generated captions, OCR text, embeddings, review decisions, and personal Markdown usually stay outside Git or in private repositories.

---

## 3. What Moves Into `documents-manager`

The current `agents-cli` lower indexing work should become the base of `documents-manager`.

It should own the reusable mechanics:

- source scanning;
- file inventory;
- source roots and source items;
- hashing/fingerprinting/freshness;
- Docling parsing;
- OCR integration points;
- artifact storage;
- SQLite catalog schema generation and migrations;
- document objects such as pages, sections, paragraphs, tables, figures, diagrams, and images;
- generic media source detection;
- thumbnail/artifact handling where generic;
- Tantivy indexing;
- LanceDB indexing;
- command reports and result folders;
- health/status commands;
- search and result hydration;
- stable provenance references.

This repo should not contain private assumptions about a specific person’s files, drives, taxonomy, family, vehicles, trips, or personal knowledge.

---

## 4. What Moves Out Into User Workspaces

The previous private `documents-manager` control-plane idea becomes a workspace pattern, not the core engine.

`personal-documents` owns user-specific configuration and durable private state:

- approved source roots;
- crawl/exclusion policies;
- operation config;
- private catalog extensions;
- reviewed annotations;
- semantic entities;
- personal notes;
- knowledge promotion rules;
- handoff manifests to topic-specific consumers;
- durable Markdown knowledge when appropriate.

`personal-media` owns media-specific private semantics:

- media review policies;
- people/entities/places/vehicles/trips;
- face clusters and reviewed identity links;
- duplicate review;
- visual event grouping;
- selected media knowledge notes;
- personal media-specific handoffs.

The workspaces should be thin. They should orchestrate and configure `documents-manager`, not reimplement indexing engines.

---

## 5. Public/Private Storage Rule

Public repositories may contain:

```text
schemas
CLI code
empty config examples
synthetic fixtures
migration logic
contract documentation
template folder structure
test data with no private facts
```

Private or uncommitted locations contain:

```text
real SQLite databases
Tantivy indexes
LanceDB stores
generated captions
OCR text
embeddings
real source manifests
personal knowledge_base Markdown
review decisions
face/entity links
handoff manifests with real paths or facts
```

The database layer does not need to live in Git. It can live in personal drives and caches.

Only repositories that intentionally store personal Markdown knowledge need to remain private.

---

## 6. CLI Shape

The CLI should expose several roots inside `documents-manager`.

A simple shape:

```bash
docs scan ...
docs parse ...
docs index ...
docs search ...
docs status ...

media scan ...
media describe ...
media dedupe ...
media review ...
media search ...

manage sources ...
manage catalog ...
manage policy ...
manage promote ...
manage handoff ...
manage status ...
```

### `docs`

Generic lower processing:

- scan folders;
- parse documents;
- extract document objects;
- build lexical/vector indexes;
- search indexed content;
- inspect parse/index status.

### `media`

Media-specific enrichment:

- inspect media files;
- extract metadata;
- generate descriptions;
- detect duplicates;
- manage visual observations;
- review media candidates;
- support media search.

### `manage`

Control-plane operations:

- source scopes;
- user policies;
- catalog status;
- private catalog migrations;
- review queues;
- knowledge promotion;
- handoff manifests;
- workspace health.

The `manage` root should not become vague magic. It should operate manifests, catalogs, review queues, source scopes, and handoffs.

---

## 7. Generic Folder Scanning

The system should not require users to choose between “document folder” and “media folder” too early.

A source folder is just a source scope. It may contain:

- PDFs;
- DOCX/PPTX/XLSX;
- Markdown;
- images;
- screenshots;
- videos;
- email exports;
- CSV/Parquet/SQLite;
- archives;
- sidecar metadata files.

The scanner should detect file types and propose or run suitable processors.

```text
source scope
  -> source items
    -> file type detection
      -> eligible processors
        -> generated artifacts / objects / observations
```

Example policy:

```yaml
sources:
  - path: ~/OneDrive/Documents
    policy:
      documents: parse
      media: metadata_only
      archives: list_only
      max_depth: 2
```

This lets a normal document folder contain photos, and a media folder contain PDFs or text files, without forcing a hard boundary.

---

## 8. Logical Layer Model

Keep the logical layers independent from repository layout.

```text
source authority
  -> source items
    -> typed assets and objects
      -> generated observations
        -> search projections
          -> reviewed semantic facts
            -> knowledge base / handoff
```

### Source Authority

Original files and connector objects.

Examples:

- local folders;
- OneDrive;
- Google Drive;
- Gmail exports or future connectors;
- photo libraries;
- archive files.

These remain the raw truth. They are read-only by default.

### Source Items

Generic inventory rows.

A source item can represent:

- a file;
- a connector object;
- an archive member;
- a sidecar file;
- a media item;
- a document.

This layer should not know personal meaning.

### Typed Assets and Objects

Domain-specific interpretations of source items.

Examples:

```text
document
document_object
media_asset
media_region
table_object
diagram_object
archive_member
```

A PDF becomes a document with pages, tables, figures, paragraphs, and images.

A photo becomes a media asset with EXIF, thumbnail, description, and possible regions.

### Generated Observations

Machine-produced facts or candidates.

Examples:

- OCR text;
- Docling objects;
- table extraction;
- image captions;
- object labels;
- face candidates;
- GPS observations;
- model-generated summaries;
- duplicate candidates.

These are useful but not necessarily durable truth.

### Search Projections

Fast indexes, not the source of truth.

Examples:

- Tantivy rows;
- SQLite FTS rows;
- LanceDB rows;
- chunk rows;
- denormalized metadata for retrieval.

These should be rebuildable.

### Reviewed Semantic Facts

Private meaning added by review or trusted rules.

Examples:

- “this file is a bank statement”;
- “this person/entity is X”;
- “this media item belongs to trip Y”;
- “this document is evidence for vehicle sale event Z”;
- “this table contains tax-relevant expenses.”

This is durable private knowledge.

### Knowledge Base / Handoff

Curated outputs.

The knowledge base contains human-readable conventions, decisions, and selected notes.

Handoff manifests transfer selected evidence to topic-specific workflows such as tax, vehicle, rental, medical, media curation, or flat-cost analysis.

---

## 9. Unifying Reference Model

The main technical stitching mechanism should be a universal evidence reference, not a giant merged schema.

A generic reference can look like:

```yaml
evidence_ref:
  table: document_objects
  id: obj_123
  kind: table
  source_item_id: src_456
  artifact_id: art_789
  page: 3
  confidence: extracted
```

Or:

```yaml
evidence_ref:
  table: media_assets
  id: asset_456
  kind: photo
  source_item_id: src_999
  region_ref: bbox:120,80,240,260
  confidence: reviewed
```

This lets a private catalog, media review queue, topic handoff, or knowledge note point back to exact source evidence without copying lower-layer rows.

The unifying primitive is:

```text
source_item_id + evidence_ref + provenance
```

Everything else should hang from that.

---

## 10. Media Integration Rule

Media should be integrated into generic scanning, but not all media semantics belong in the lower engine.

### Generic lower/media-capable layer

Good candidates for `documents-manager`:

- source item detection;
- file type detection;
- EXIF/container metadata extraction;
- thumbnail generation;
- generic media asset rows;
- generic captions/descriptions;
- OCR in images;
- object labels;
- embedding projections;
- duplicate candidate generation;
- media search result hydration.

### Private media workspace

Keep these in `personal-media`:

- person identity;
- family relationships;
- private aliases;
- reviewed face identity;
- vehicles owned by the user;
- trips and personal events;
- private places;
- personal review decisions;
- curated media knowledge.

The lower engine may expose candidates. The private workspace decides meaning.

---

## 11. Documents Integration Rule

Documents should also keep the same split.

### Generic lower layer

Good candidates for `documents-manager`:

- Docling parse output;
- normalized pages/sections/paragraphs/tables/figures/images;
- OCR;
- chunks;
- lexical/vector indexes;
- document-object search;
- parse/index freshness;
- provenance.

### Private document workspace

Keep these in `personal-documents`:

- approved source policies;
- private annotations;
- reviewed document classes;
- semantic entities;
- personal notes;
- topic-specific relevance;
- handoff manifests;
- Markdown knowledge base.

---

## 12. Repository Shape

Proposed public `documents-manager` shape:

```text
documents-manager/
  src/documents_manager/
    cli/
      docs.py
      media.py
      manage.py
    catalog/
    scan/
    parse/
    media/
    index/
    search/
    reports/
  schemas/
    catalog.yaml
    source_scope.schema.yaml
    policy.schema.yaml
    handoff.schema.yaml
  config/
    examples/
  fixtures/
    synthetic/
  docs/
    architecture.md
    cli.md
    storage.md
    public-private-split.md
```

Proposed `personal-documents` shape:

```text
personal-documents/
  README.md
  config/
    document-index.yaml
    source-scope.yaml        # real file usually gitignored
    policy.yaml              # real file usually gitignored
  catalog/
    private_catalog.schema.yaml
  knowledge_base/            # private or gitignored if personal
  handoffs/                  # gitignored if real
  .gitignore
```

Proposed `personal-media` shape:

```text
personal-media/
  README.md
  config/
    media-scope.yaml         # real file usually gitignored
    media-policy.yaml        # real file usually gitignored
  catalog/
    media_private.schema.yaml
  review/
    queues/                  # gitignored if real
  knowledge_base/            # private or gitignored if personal
  .gitignore
```

---

## 13. Migration Plan

### Step 1: Rename Conceptually

Treat `agents-cli` as the current implementation base for the future `documents-manager`.

Do not immediately break package names if that slows development. First update documentation and target structure.

### Step 2: Define CLI Roots

Introduce or document the target roots:

```text
docs
media
manage
```

Map current commands into `docs` first.

Then move media-specific commands under `media`.

Then expose source-scope, policy, catalog, promotion, and handoff operations under `manage`.

### Step 3: Move Generic Media Mechanics Into Engine

From `media-manager`, move or recreate only reusable mechanics:

- generic media scan;
- metadata extraction;
- thumbnail/artifact handling;
- description generation interface;
- duplicate candidate generation;
- media search projection;
- generic media schema.

Do not move personal entity/event assumptions into the public engine.

### Step 4: Move Private Semantics Into Workspaces

From the old private `documents-manager` and `media-manager` ideas, keep private or gitignored:

- real source scopes;
- personal paths;
- personal entities;
- reviewed relationships;
- personal knowledge Markdown;
- private handoffs;
- generated private databases.

### Step 5: Stabilize Shared Contracts

Promote stable contracts into public schema files:

- source scope manifest;
- catalog schema;
- policy manifest;
- evidence reference format;
- handoff manifest;
- review queue format;
- command report format.

### Step 6: Build One Vertical Slice

Do not migrate everything at once.

First useful slice:

```text
scan one mixed folder
  -> detect documents and media
  -> parse simple documents
  -> extract media metadata
  -> write SQLite catalog
  -> build one FTS or LanceDB index
  -> return search results with evidence refs
  -> create one handoff manifest
```

Only after this works should reviewed entities, media events, and knowledge promotion be layered on top.

---

## 14. First Implementation Slice

Recommended first slice:

```text
documents-manager docs scan <folder>
documents-manager docs parse <folder>
documents-manager docs index <folder>
documents-manager docs search "query"

documents-manager media scan <folder>
documents-manager media describe <folder>
documents-manager media search "query"

documents-manager manage sources status
documents-manager manage handoff create --topic vehicle --query "Audi invoice"
```

Minimum output requirement:

Every result must include:

- source item ID;
- source path or URI;
- type;
- evidence reference;
- score or status;
- match mode;
- provenance;
- generated artifact reference where applicable.

---

## 15. Design Rules

1. Do not store personal facts in public repo commits.

2. Do not duplicate lower catalog rows in private catalogs unless there is a concrete need.

3. Keep search projections rebuildable.

4. Keep reviewed semantic facts durable.

5. Keep generated observations addressable by stable IDs.

6. Keep public schemas synthetic and redaction-safe.

7. Treat source folders as mixed-content scopes.

8. Let file type and policy choose processors.

9. Use handoff manifests between generic manager and topic-specific workflows.

10. Keep `documents-manager` useful without requiring any private workspace.

---

## 16. Anti-Goals

Avoid:

- one huge monolithic private repo;
- a pretentious platform name;
- making users classify folders as only documents or only media;
- putting private entities into the generic lower schema;
- committing generated personal databases;
- treating LanceDB or Tantivy as authoritative truth;
- duplicating Docling/Tantivy/LanceDB logic in workspace repos;
- making `manage` a vague agent-only command group;
- turning `knowledge_base/` into a dump of extracted text.

---

## 17. Target Outcome

The target outcome is a practical local management system:

```text
documents-manager
  scans mixed personal folders
  parses and indexes documents
  understands media enough to search and enrich it
  exposes stable SQLite/search/provenance contracts
  supports private workspaces for personal knowledge
  lets topic-specific workflows receive selected evidence
```

The strongest product shape is:

```text
documents-manager = public engine

personal-documents / personal-media = thin user workspaces

private knowledge repositories = only when Markdown knowledge itself is personal
```

This gives a simple story:

> A public CLI manages local documents and media.  
> Private workspaces decide which sources are allowed, where generated data lives, what is reviewed, and what gets promoted into durable knowledge.

That is powerful without being overnamed.
