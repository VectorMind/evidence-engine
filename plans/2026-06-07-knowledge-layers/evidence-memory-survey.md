# Evidence Memory Survey

Date: 2026-06-07  
Status: Research survey / architecture comparison  
Source architecture: `evidence_memory_consolidation_handover.md`

---

## 1. Scope

This survey maps state-of-the-art libraries, applications, and research directions against a proposed **local-first evidence memory system**.

The target architecture is not just a document indexer, RAG app, media manager, or personal wiki. The core product shape is:

```text
raw source authority
  -> rebuildable evidence cache
    -> normalized evidence objects
      -> search projections
        -> private semantic catalog
          -> curated knowledge base
            -> topic-specific consumers
```

The central architectural rule is:

```text
Lower schemas describe what was observed and generated.
Upper schemas describe what was believed, reviewed, promoted, or used.
```

This survey therefore evaluates systems by how well they support:

- source authority;
- rebuildable evidence caches;
- normalized evidence/document/media objects;
- full-text, structured, and vector search projections;
- private semantic entities, events, relationships, and facts;
- provenance and evidence references;
- review and promotion lifecycles;
- curated knowledge bases;
- topic-specific handoff manifests.

---

## 2. Executive Summary

No single current open-source application fully implements this architecture.

The closest state-of-the-art direction is a combination of four families:

| Family | Closest examples | What they cover | What they miss versus evidence memory |
| --- | --- | --- | --- |
| Document intelligence / evidence extraction | Docling, Unstructured, Apache Tika, Paperless-ngx | Parsing, OCR, metadata, layout, tables, text extraction, document objects | Weak private semantic catalog, weak cross-domain entity/event layer, limited handoff semantics |
| Personal/local-first archives | Dogsheep, HPI, Promnesia, Obsidian, Logseq, Zotero | Local ownership, personal data aggregation, notes, personal search, source maps | Usually no rigorous evidence refs, model-run provenance, review lifecycle, or multimodal RAG layer |
| RAG / agent-memory platforms | R2R, Cognee, Zep/Graphiti, Mem0, Letta, AnythingLLM, Khoj, Open WebUI | Ingestion, vector search, graph memory, agent memory, document chat | Often treat extracted memory as product truth too early; weaker source authority/cache/rebuild boundary |
| Research systems | GraphRAG, LightRAG, HippoRAG, RAPTOR, RAG-Anything | Hierarchical summaries, graph retrieval, multimodal retrieval, temporal/long-term memory | Usually papers/frameworks, not full local evidence-control-plane products |

The proposed architecture is best understood as:

```text
Paperless-ngx / Immich style personal archives
+ Dogsheep/HPI style local personal data warehouse
+ Docling/Unstructured style evidence extraction
+ SQLite/Tantivy/LanceDB search projections
+ Graphiti/GraphRAG style semantic entity/event graph
+ Obsidian/Zotero style curated knowledge
+ W3C PROV / RO-Crate style provenance and handoff packaging
```

The most accurate category name is:

```text
Local-first Evidence Memory
```

or, more technically:

```text
Evidence-Centered Personal Knowledge Infrastructure
```

---

## 3. Evaluation Lens

A system is close to the target architecture if it distinguishes these layers:

| Layer | Meaning | Desired property |
| --- | --- | --- |
| Source authority | Original folders, drives, emails, files, connector objects | Read-only, stable, private |
| Evidence cache | Machine-generated extraction artifacts | Rebuildable, disposable |
| Evidence catalog | Structured catalog of observed/generated objects | SQLite-friendly, provenance-rich |
| Search projections | FTS/vector/graph indexes | Rebuildable, hydrated back to evidence refs |
| Private semantic catalog | Reviewed entities, facts, events, links | Durable, private, provenance-backed |
| Knowledge base | Human-readable curated notes | Markdown or similar, not raw dumps |
| Topic workspace | Tax, vehicle, medical, rental, finance, family archive | Consumes handoff manifests, does not re-crawl everything |

The critical distinction is not “graph vs vector” or “SQLite vs vector DB”. The critical distinction is:

```text
observed/generated evidence != reviewed/promoted belief
```

Most current RAG systems blur this boundary.

---

## 4. Practical Libraries and Applications

### 4.1 Docling

**Type:** document intelligence library / pipeline  
**Main role:** lower evidence extraction

Docling is one of the strongest fits for the lower evidence layer. It converts complex documents into structured representations and supports PDF understanding, OCR, layout analysis, tables, formulas, and reading order. It also has integrations with GenAI frameworks.

**What to study:**

- document object representation;
- PDF layout extraction;
- table structure extraction;
- OCR integration;
- artifact generation;
- model profiles and parser configuration;
- output formats suitable for downstream indexing.

**Fit to evidence memory:**

| Target concept | Fit |
| --- | --- |
| `documents` | Strong |
| `docling_artifacts` | Strong |
| `document_objects` | Strong |
| `valuable_items` | Medium to strong |
| `chunks` | Usually downstream, not Docling's main role |
| private semantic catalog | Weak |
| review/promotion lifecycle | Weak |

**Design lesson:** Docling should be treated as a lower extraction producer. It should not own private semantic truth.

Source: https://www.docling.ai/

---

### 4.2 Unstructured

**Type:** document ingestion / partitioning library  
**Main role:** lower extraction and preprocessing

Unstructured partitions raw documents into typed elements such as titles, narrative text, list items, tables, and metadata. It supports many formats and can use OCR/layout strategies.

**What to study:**

- element typing;
- metadata conventions;
- partition strategies;
- document format coverage;
- chunking and element-to-RAG pipelines.

**Fit to evidence memory:**

| Target concept | Fit |
| --- | --- |
| typed evidence objects | Strong |
| cross-format extraction | Strong |
| OCR/layout fallback | Strong |
| provenance-rich evidence refs | Medium |
| private semantic review | Weak |
| topic handoff | Weak |

**Design lesson:** Unstructured is useful as a parser abstraction, especially for broad file coverage, but the evidence-memory system should own the provenance, cache, and review lifecycle.

Source: https://docs.unstructured.io/open-source/core-functionality/partitioning

---

### 4.3 Apache Tika

**Type:** text and metadata extraction toolkit  
**Main role:** fallback extraction baseline

Apache Tika detects and extracts metadata and text from a very large number of file types through a consistent interface.

**What to study:**

- broad file type detection;
- metadata extraction;
- fallback text extraction;
- integration as a cheap first pass before heavier parsing.

**Fit to evidence memory:**

| Target concept | Fit |
| --- | --- |
| source item classification | Strong |
| metadata extraction | Strong |
| lightweight text extraction | Strong |
| rich document object modeling | Weak to medium |
| semantic catalog | Weak |

**Design lesson:** Tika is valuable as a cheap, broad fallback extractor before expensive Docling/OCR/VLM processing.

Source: https://tika.apache.org/

---

### 4.4 Paperless-ngx

**Type:** self-hosted personal document management app  
**Main role:** practical document archive workflow reference

Paperless-ngx is one of the closest mature applications for personal document archiving. It provides OCR-backed full-text search, tags, correspondents, document types, custom fields, saved views, dashboards, and automatic matching.

**What to study:**

- ingestion UX;
- OCR queueing;
- document metadata;
- tags/correspondents/types;
- custom fields;
- saved views;
- document review workflows;
- storage path handling.

**Fit to evidence memory:**

| Target concept | Fit |
| --- | --- |
| personal document archive | Strong |
| OCR and full-text search | Strong |
| metadata/tagging | Strong |
| review UX | Medium |
| multimodal media/document evidence graph | Weak |
| evidence refs and handoff manifests | Weak |
| private semantic entities/events | Weak to medium |

**Design lesson:** Paperless-ngx is the best UX benchmark for a document control plane, but the proposed architecture goes deeper by separating extraction evidence, reviewed semantics, and topic handoffs.

Source: https://docs.paperless-ngx.com/

---

## 5. Search and Projection Components

### 5.1 SQLite

**Type:** embedded relational database  
**Main role:** evidence catalog and private catalog

SQLite is a strong default for the catalog/control layers because it is local, inspectable, durable, fast enough, and easy to back up.

**Best use in evidence memory:**

- source roots;
- source items;
- extraction state;
- object catalogs;
- parser/model run metadata;
- review queues;
- private semantic entities;
- fact evidence links;
- handoff sets;
- promotion state.

**Design lesson:** SQLite should hold control truth and reviewed state. It should not be treated merely as a cache if it stores private semantic catalog data.

Source: https://sqlite.org/

---

### 5.2 Tantivy

**Type:** Rust full-text search engine library  
**Main role:** rebuildable full-text projection

Tantivy is a Lucene-inspired search engine library. It is a good fit for fast local full-text indexing over extracted evidence objects and chunks.

**Best use in evidence memory:**

- exact term search;
- invoice numbers;
- contract clauses;
- OCR text;
- table text;
- fielded search;
- snippets;
- search over generated document/media descriptions.

**Design lesson:** Tantivy indexes should hydrate back to evidence refs. The index should never become the only place where truth exists.

Source: https://github.com/quickwit-oss/tantivy

---

### 5.3 LanceDB

**Type:** vector and multimodal data store  
**Main role:** semantic/multimodal search projection

LanceDB is a strong fit for semantic retrieval over text chunks, captions, image embeddings, table descriptions, and multimodal evidence.

**Best use in evidence memory:**

- semantic search over document chunks;
- semantic search over media descriptions;
- image/text multimodal search;
- local vector collections by index scope;
- model-versioned embedding profiles.

**Design lesson:** LanceDB should be treated as a projection store. It should store enough metadata to hydrate back to SQLite evidence refs, but not become the source of semantic truth.

Source: https://github.com/lancedb/lancedb

---

## 6. Personal Data Warehouse and Local-First Archive Precedents

### 6.1 Dogsheep

**Type:** personal analytics ecosystem  
**Main role:** personal data warehouse precedent

Dogsheep exports personal data from many services into SQLite databases and makes them explorable, often through Datasette.

**Why it matters:**

Dogsheep is one of the strongest precedents for a personal local data warehouse assembled from many private sources.

**Fit to evidence memory:**

| Target concept | Fit |
| --- | --- |
| many source adapters | Strong |
| local SQLite as substrate | Strong |
| personal data ownership | Strong |
| document/media extraction | Weak |
| evidence object model | Weak |
| review/promotion semantics | Weak |

**Design lesson:** Treat source importers as independent, inspectable, local-first pipelines. Use SQLite as a universal personal data substrate.

Source: https://github.com/dogsheep/dogsheep.github.io

---

### 6.2 HPI / Human Programming Interface

**Type:** Python interface for personal data  
**Main role:** personal source abstraction

HPI unifies access to personal data sources including social networks, notes, health, location, photos/videos, browser history, and messages.

**Why it matters:**

It demonstrates the idea of a personal information API written as code, where sources are adapted into a programmable interface.

**Fit to evidence memory:**

| Target concept | Fit |
| --- | --- |
| personal data source adapters | Strong |
| local-first data access | Strong |
| Pythonic data interface | Strong |
| extraction/cache/index projections | Medium |
| reviewed semantic catalog | Weak |

**Design lesson:** A source adapter layer can be code-first and personal without forcing all data into one central app.

Source: https://github.com/karlicoss/HPI

---

### 6.3 Promnesia

**Type:** browsing history / personal memory tool  
**Main role:** contextual source memory

Promnesia enhances browsing history and integrates with personal knowledge bases.

**Why it matters:**

It is a narrow but relevant precedent for remembering the context in which a source was encountered.

**Fit to evidence memory:**

| Target concept | Fit |
| --- | --- |
| source context | Strong |
| personal memory | Medium |
| evidence provenance | Medium |
| generalized document/media memory | Weak |

**Design lesson:** Provenance is not just file paths and hashes; it can include user interaction history and discovery context.

Source: https://github.com/karlicoss/promnesia

---

### 6.4 Obsidian

**Type:** local Markdown knowledge base  
**Main role:** curated upper knowledge base

Obsidian stores notes locally as Markdown files in a vault.

**Fit to evidence memory:**

| Target concept | Fit |
| --- | --- |
| curated knowledge base | Strong |
| local files | Strong |
| human-readable conventions | Strong |
| raw extraction store | Weak |
| structured private catalog | Weak |

**Design lesson:** Obsidian-style Markdown is excellent for curated source maps, decisions, conventions, and durable notes. It should not become a dump of OCR text.

Source: https://obsidian.md/help/data-storage

---

### 6.5 Logseq

**Type:** local-first outliner / knowledge graph  
**Main role:** curated knowledge and linked notes

Logseq emphasizes local files, privacy, longevity, user control, Markdown/Org files, PDF annotation, and linked notes.

**Fit to evidence memory:**

| Target concept | Fit |
| --- | --- |
| private local knowledge graph | Strong |
| linked notes | Strong |
| human review layer | Medium |
| source authority/cache boundary | Weak |

**Design lesson:** Logseq is a useful reference for user-controlled upper knowledge, not for lower extraction/cache mechanics.

Source: https://logseq.com/

---

### 6.6 Zotero

**Type:** research reference manager  
**Main role:** curated scholarly evidence and citation workflow

Zotero helps collect, organize, annotate, cite, and share research.

**Fit to evidence memory:**

| Target concept | Fit |
| --- | --- |
| source collection | Strong |
| annotations | Strong |
| citation/provenance UX | Strong |
| curated evidence | Strong |
| general personal documents/media | Medium |
| local evidence cache architecture | Weak |

**Design lesson:** Zotero is a strong reference for provenance UX, citation discipline, and curated evidence workflows.

Source: https://www.zotero.org/

---

## 7. Media Memory Systems

### 7.1 Immich

**Type:** self-hosted photo/video backup and management app  
**Main role:** media manager reference

Immich is one of the strongest open-source photo/video systems. It supports backup, albums, deduplication, EXIF/map metadata, and search by metadata, objects, faces, and CLIP.

**Fit to evidence memory:**

| Target concept | Fit |
| --- | --- |
| media assets | Strong |
| thumbnails/previews | Strong |
| EXIF metadata | Strong |
| faces/objects/search | Strong |
| personal media UX | Strong |
| cross-document evidence graph | Weak |
| reviewed topic handoff | Weak |

**Design lesson:** Immich is a strong reference for media ingestion, face/object search, and personal photo UX. The evidence-memory design can reuse the media concepts but should connect them to documents, entities, events, and topic workspaces.

Source: https://github.com/immich-app/immich

---

### 7.2 PhotoPrism

**Type:** self-hosted AI photo management app  
**Main role:** media catalog and search reference

PhotoPrism describes itself as an AI-powered decentralized photos app that tags and finds pictures automatically and supports search filters.

**Fit to evidence memory:**

| Target concept | Fit |
| --- | --- |
| photo catalog | Strong |
| automatic tagging | Strong |
| search/filter UI | Strong |
| private semantic catalog | Weak |
| multimodal evidence refs | Weak |

**Design lesson:** PhotoPrism is useful as a media catalog reference but less aligned with evidence/reference/promotion architecture.

Source: https://www.photoprism.app/

---

### 7.3 digiKam

**Type:** desktop digital asset management application  
**Main role:** long-term photo archive metadata reference

digiKam supports database-backed and file/sidecar metadata, advanced search by tags/labels/dates/geolocation, and face detection/recognition workflows.

**Fit to evidence memory:**

| Target concept | Fit |
| --- | --- |
| long-term photo archive | Strong |
| metadata durability | Strong |
| sidecar support | Strong |
| face workflows | Strong |
| RAG/agentic retrieval | Weak |

**Design lesson:** digiKam is a strong reference for long-term media metadata and sidecar strategy.

Source: https://docs.digikam.org/en/asset_management/organize_find.html

---

## 8. RAG and Agent-Memory Platforms

### 8.1 R2R

**Type:** production RAG platform  
**Main role:** RAG API and document-management reference

R2R advertises multimodal ingestion, hybrid search, knowledge graphs, document management, a REST API, and deep research over knowledge bases or the internet.

**Fit to evidence memory:**

| Target concept | Fit |
| --- | --- |
| document ingestion | Strong |
| hybrid search | Strong |
| knowledge graph | Strong |
| API surface | Strong |
| private source authority/cache separation | Medium |
| reviewed semantic promotion | Weak to medium |
| topic handoff manifests | Weak |

**Design lesson:** R2R is a useful comparison point for production RAG, but evidence memory should keep a stricter boundary between extraction, index projection, reviewed facts, and promoted knowledge.

Source: https://github.com/SciPhi-AI/R2R

---

### 8.2 Cognee

**Type:** memory platform / control plane for agents  
**Main role:** agent memory and knowledge graph reference

Cognee positions itself as an open-source memory platform/control plane for agents, combining documents, relational data, system context, embeddings, graphs, and evolving relationships.

**Fit to evidence memory:**

| Target concept | Fit |
| --- | --- |
| agent memory control plane | Strong |
| graph memory | Strong |
| semantic relationships | Strong |
| document/data ingestion | Medium to strong |
| local evidence-cache mechanics | Medium |
| source authority/cache/provenance discipline | Medium |

**Design lesson:** Cognee is close to the private semantic catalog and graph-memory layer, but evidence memory needs a more explicit lower evidence cache and rebuild boundary.

Source: https://www.cognee.ai/

---

### 8.3 Zep / Graphiti

**Type:** temporal knowledge graph memory  
**Main role:** temporal entity/fact memory

Graphiti builds temporal context graphs, tracks changing facts, maintains provenance to source data, supports learned or prescribed ontologies, and combines vector, full-text, and graph traversal retrieval.

**Fit to evidence memory:**

| Target concept | Fit |
| --- | --- |
| entities and relationships | Strong |
| temporal facts | Strong |
| fact invalidation/supersession | Strong |
| provenance to source data | Strong |
| hybrid graph/full-text/vector retrieval | Strong |
| lower document/media object cache | Weak to medium |
| local-first personal archive | Medium |

**Design lesson:** Graphiti is one of the most relevant systems for the upper private semantic catalog, especially if reviewed facts must change over time.

Source: https://github.com/getzep/graphiti

---

### 8.4 Mem0

**Type:** universal memory layer for LLM applications  
**Main role:** agent/application memory

Mem0 provides a memory layer for LLM applications and agents.

**Fit to evidence memory:**

| Target concept | Fit |
| --- | --- |
| application memory | Strong |
| memory retrieval | Strong |
| user/profile memory | Medium |
| provenance-rich evidence refs | Weak |
| lower evidence cache | Weak |

**Design lesson:** Mem0 is useful for memory read/write policies, but evidence memory needs stronger provenance and review.

Source: https://github.com/mem0ai/mem0

---

### 8.5 Letta / MemGPT

**Type:** stateful agent memory framework  
**Main role:** agent memory architecture

MemGPT frames memory as OS-like virtual context management across memory tiers. Letta builds on this lineage for stateful agents with persistent memory.

**Fit to evidence memory:**

| Target concept | Fit |
| --- | --- |
| long-running agent state | Strong |
| memory tiers | Strong |
| conversation memory | Strong |
| source evidence management | Weak |
| private document/media archive | Weak |

**Design lesson:** Useful for context-window and memory-tier thinking, but not enough for evidence-backed personal knowledge.

Sources:

- https://arxiv.org/abs/2310.08560
- https://www.letta.com/

---

### 8.6 AnythingLLM

**Type:** private chat/RAG application  
**Main role:** local/private RAG product reference

AnythingLLM bundles private chat, local/cloud LLMs, vector databases, document pipelines, agents, multi-user support, and local privacy defaults.

**Fit to evidence memory:**

| Target concept | Fit |
| --- | --- |
| private document chat | Strong |
| local/cloud flexibility | Strong |
| vector RAG | Strong |
| evidence lifecycle | Weak |
| semantic review and promotion | Weak |

**Design lesson:** Good UX/product reference for private chat with documents, but not a deep evidence-memory architecture.

Source: https://github.com/Mintplex-Labs/anything-llm

---

### 8.7 Khoj

**Type:** open-source personal AI assistant  
**Main role:** personal search/chat over notes and documents

Khoj searches notes/documents with natural language and supports sources such as PDF, plaintext, Markdown, Org, and Notion.

**Fit to evidence memory:**

| Target concept | Fit |
| --- | --- |
| personal AI search | Strong |
| notes/documents | Strong |
| local/personal workflow | Medium to strong |
| evidence refs/provenance | Weak to medium |
| review/promotion lifecycle | Weak |

**Design lesson:** Khoj is a useful product reference for personal AI over notes and documents.

Source: https://docs.khoj.dev/

---

### 8.8 Open WebUI Knowledge

**Type:** knowledge-base feature inside an AI interface  
**Main role:** document RAG UX reference

Open WebUI’s Knowledge feature lets AI search, read, and reason over uploaded document collections using RAG.

**Fit to evidence memory:**

| Target concept | Fit |
| --- | --- |
| knowledge collection UX | Medium |
| RAG over documents | Strong |
| local/self-hosted AI UI | Strong |
| evidence cache/private catalog separation | Weak |

**Design lesson:** Useful as a UX reference, but architecturally closer to ordinary RAG than evidence memory.

Source: https://docs.openwebui.com/features/workspace/knowledge/

---

## 9. Research Directions

### 9.1 GraphRAG

**Type:** graph-based retrieval-augmented generation  
**Main idea:** extract a knowledge graph from text, build a community hierarchy, generate community summaries, and use local/global retrieval.

**Relevance to evidence memory:**

GraphRAG supports the idea that flat chunk retrieval is insufficient for large, complex corpora. It validates graph extraction, community summaries, and multi-level retrieval.

**Fit:**

| Target concept | Fit |
| --- | --- |
| entity graph | Strong |
| community/hierarchical summaries | Strong |
| global vs local search | Strong |
| provenance/review lifecycle | Medium |
| local personal evidence system | Weak |

**Design lesson:** Use graph summaries as projections over evidence, not as unquestioned truth.

Source: https://www.microsoft.com/en-us/research/project/graphrag/

---

### 9.2 LightRAG

**Type:** graph + vector retrieval framework  
**Main idea:** combine low-level precise entity/relationship retrieval with high-level global/context retrieval and incremental updates.

**Relevance to evidence memory:**

LightRAG supports the idea that retrieval should operate at multiple semantic resolutions: entity-level, relationship-level, and global context.

**Fit:**

| Target concept | Fit |
| --- | --- |
| hybrid graph/vector retrieval | Strong |
| incremental updates | Strong |
| low-level/high-level search distinction | Strong |
| evidence provenance and review | Medium |

**Design lesson:** Evidence memory should expose retrieval across lower exact evidence, semantic entities, events, and summaries.

Source: https://arxiv.org/abs/2410.05779

---

### 9.3 RAPTOR

**Type:** hierarchical summarization and retrieval  
**Main idea:** recursively embed, cluster, and summarize chunks into a tree, retrieving from multiple abstraction levels.

**Relevance to evidence memory:**

RAPTOR is highly relevant to destructive/lossy folder summaries and multi-resolution search.

**Fit:**

| Target concept | Fit |
| --- | --- |
| hierarchical summaries | Strong |
| lossy abstraction layers | Strong |
| multi-resolution retrieval | Strong |
| source authority/review lifecycle | Weak |

**Design lesson:** Summaries are powerful search surfaces, but they should be marked as generated projections and linked back to evidence refs.

Source: https://arxiv.org/abs/2401.18059

---

### 9.4 HippoRAG

**Type:** long-term memory retrieval inspired by hippocampal indexing  
**Main idea:** combine LLMs, knowledge graphs, and Personalized PageRank for multi-hop retrieval.

**Relevance to evidence memory:**

HippoRAG validates graph-based long-term memory and multi-hop retrieval over large corpora.

**Fit:**

| Target concept | Fit |
| --- | --- |
| long-term memory retrieval | Strong |
| graph traversal | Strong |
| multi-hop reasoning | Strong |
| reviewed private catalog | Medium |
| local archive mechanics | Weak |

**Design lesson:** Entity/event graphs can act as long-term memory indexes over evidence caches.

Source: https://arxiv.org/abs/2405.14831

---

### 9.5 RAG-Anything

**Type:** multimodal RAG research  
**Main idea:** treat multimodal content as interconnected knowledge entities and use dual-graph construction plus cross-modal hybrid retrieval.

**Relevance to evidence memory:**

This is especially relevant for a document+media+tables+figures architecture.

**Fit:**

| Target concept | Fit |
| --- | --- |
| multimodal evidence | Strong |
| cross-modal retrieval | Strong |
| graph-based multimodal representation | Strong |
| personal/private review lifecycle | Weak |

**Design lesson:** Tables, images, figures, text, and media assets should be first-class evidence objects, not just text chunks.

Source: https://arxiv.org/abs/2510.12323

---

## 10. Provenance, Packaging, and Handoff Standards

### 10.1 W3C PROV

**Type:** provenance data model  
**Main idea:** model provenance through entities, activities, and agents.

**Relevance to evidence memory:**

W3C PROV maps naturally to:

- source items as entities;
- extraction runs as activities;
- parsers, OCR engines, embedding models, and agents as agents;
- derived artifacts as generated entities;
- evidence refs as provenance-backed identifiers.

**Design lesson:** The evidence reference contract should borrow the entity/activity/agent distinction.

Source: https://www.w3.org/TR/prov-dm/

---

### 10.2 RO-Crate

**Type:** research object packaging and metadata standard  
**Main idea:** package data, metadata, provenance, identifiers, relations, and annotations.

**Relevance to evidence memory:**

RO-Crate is relevant to topic handoff manifests. A handoff set can be thought of as a small evidence crate containing selected refs, metadata, provenance, roles, and review state.

**Design lesson:** Topic handoffs should be packaged evidence slices, not ad-hoc file copies.

Source: https://www.researchobject.org/ro-crate/

---

### 10.3 OpenLineage

**Type:** data lineage standard  
**Main idea:** track datasets, jobs, runs, and lineage events.

**Relevance to evidence memory:**

OpenLineage is useful for thinking about parser runs, embedding runs, index builds, cache watermarks, and reproducibility.

**Design lesson:** Extraction/indexing should record producer, version, config hash, source hash, run ID, and output artifact identity.

Source: https://openlineage.io/

---

### 10.4 PROV-AGENT

**Type:** agentic workflow provenance research  
**Main idea:** extend provenance modeling for agentic workflows where decisions, tool calls, and generated outputs need traceability.

**Relevance to evidence memory:**

If agents propose entities, links, facts, or summaries, the system needs to know which agent/model/tool produced the proposal and from which evidence.

**Design lesson:** Agent-generated semantic proposals should be stored as observations/proposals until reviewed.

Source: https://arxiv.org/abs/2508.02866

---

## 11. Historical and Conceptual Precedents

### 11.1 Memex

Vannevar Bush’s “As We May Think” imagined a personal machine for books, records, communications, annotations, and associative trails.

**Relevance:** conceptual ancestor of personal evidence memory.

Source: https://www.theatlantic.com/magazine/archive/1945/07/as-we-may-think/303881/

---

### 11.2 MyLifeBits

Microsoft Research’s MyLifeBits explored a lifetime personal database containing documents, papers, photos, videos, email, web browsing, and daily activity.

**Relevance:** one of the closest historical precedents for a personal database of everything.

Source: https://cacm.acm.org/research/mylifebits/

---

### 11.3 Haystack

MIT Haystack proposed RDF as a primary model for personal information across documents, email, appointments, tasks, and other personal data.

**Relevance:** semantic-desktop precedent for cross-application personal knowledge.

Source: https://ceur-ws.org/Vol-55/huynh.pdf

---

### 11.4 NEPOMUK

NEPOMUK aimed to help knowledge workers exploit personal information across application boundaries.

**Relevance:** semantic desktop and personal information management precedent.

Source: https://nepomuk.semanticdesktop.org/

---

### 11.5 Local-first software

The local-first software literature argues that the primary copy of user data should live on the user’s device, with servers used mainly for sync/collaboration.

**Relevance:** strongly supports the privacy/ownership assumptions of evidence memory.

Source: https://martin.kleppmann.com/papers/local-first.pdf

---

## 12. Enterprise Metadata and Lineage Systems

### 12.1 DataHub

**Type:** data catalog and metadata platform  
**Main role:** enterprise metadata graph reference

DataHub is useful for metadata graph, discovery, governance, lineage, and semantic context patterns.

**Relevance:** good inspiration for metadata graph and lineage, but too enterprise-oriented for personal local-first evidence memory.

Source: https://datahub.com/

---

### 12.2 OpenMetadata

**Type:** metadata platform  
**Main role:** enterprise data discovery, observability, governance

OpenMetadata uses a unified metadata graph for data discovery, observability, governance, and business semantics.

**Relevance:** useful for schema/lineage/governance vocabulary.

Source: https://open-metadata.org/

---

### 12.3 Dagster software-defined assets

**Type:** data orchestration model  
**Main role:** asset lifecycle and lineage thinking

Dagster treats persistent data assets as first-class objects defined by code, with observability and lineage.

**Relevance:** useful for thinking of extracted artifacts, indexes, and summaries as generated assets with dependencies.

Source: https://dagster.io/glossary/software-defined-assets

---

### 12.4 lakeFS and DVC

**Type:** data/model versioning systems  
**Main role:** versioned data artifacts

lakeFS brings Git-like operations to object storage. DVC provides Git-like data/model versioning for ML/data projects.

**Relevance:** useful if evidence cache artifacts grow beyond simple local folders, but probably too heavy for the first implementation.

Sources:

- https://github.com/treeverse/lakeFS
- https://dvc.org/

---

## 13. Comparative Gap Matrix

| System | Source authority | Evidence cache | Object model | FTS/vector | Private semantics | Review/promotion | Topic handoff | Multimodal |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Docling | Medium | Strong | Strong | Medium | Weak | Weak | Weak | Medium |
| Unstructured | Medium | Strong | Strong | Medium | Weak | Weak | Weak | Medium |
| Tika | Medium | Medium | Weak | Medium | Weak | Weak | Weak | Weak |
| Paperless-ngx | Strong | Strong | Medium | Strong | Medium | Medium | Weak | Weak |
| Immich | Strong | Strong | Strong for media | Strong | Medium | Medium | Weak | Strong |
| Dogsheep | Strong | Medium | Medium | Medium | Weak | Weak | Weak | Medium |
| HPI | Strong | Medium | Medium | Weak | Weak | Weak | Weak | Medium |
| Obsidian | Strong | Weak | Weak | Medium | Medium | Medium | Weak | Weak |
| Zotero | Strong | Medium | Medium | Strong | Medium | Strong | Medium | Weak |
| R2R | Medium | Medium | Medium | Strong | Medium | Medium | Weak | Strong |
| Cognee | Medium | Medium | Medium | Strong | Strong | Medium | Weak | Medium |
| Graphiti | Medium | Weak | Medium | Strong | Strong | Medium | Weak | Medium |
| Mem0 | Weak | Weak | Weak | Medium | Medium | Medium | Weak | Weak |
| Letta/MemGPT | Weak | Weak | Weak | Medium | Medium | Medium | Weak | Weak |
| GraphRAG | Medium | Weak | Medium | Strong | Medium | Weak | Weak | Weak |
| RAPTOR | Weak | Weak | Weak | Strong | Weak | Weak | Weak | Weak |
| RAG-Anything | Medium | Medium | Strong | Strong | Medium | Weak | Weak | Strong |
| Evidence memory target | Strong | Strong | Strong | Strong | Strong | Strong | Strong | Strong |

---

## 14. Main Architectural Gap in Existing Tools

Most systems choose one of these simplifications:

1. **Document management apps** treat extracted document metadata/tags as the main semantic layer.
2. **RAG apps** treat chunks and embeddings as the knowledge base.
3. **Agent memory apps** treat remembered facts as application memory.
4. **GraphRAG systems** treat extracted entity graphs and summaries as retrieval structures.
5. **Photo apps** treat media metadata, face clusters, and albums as the user-facing truth.
6. **Note apps** treat human Markdown notes as the main knowledge source.

The evidence-memory architecture is stronger because it separates all of these:

```text
raw source
!= extracted artifact
!= evidence object
!= search projection
!= model observation
!= proposed semantic fact
!= reviewed semantic fact
!= promoted note
!= topic-specific report
```

That separation is the main contribution.

---

## 15. Recommended Convergence Strategy

### 15.1 Keep the lower engine boring and public

The lower engine should own:

- source inventory;
- file fingerprints;
- extraction runs;
- parser artifacts;
- normalized evidence objects;
- search projection builds;
- result hydration;
- diagnostics;
- cache health.

It should not own:

- private identities;
- personal entities;
- family semantics;
- vehicle/tax/rental classifications;
- reviewed beliefs;
- topic reports.

### 15.2 Make evidence refs the stable kernel

Every upper-layer row should be able to point back to lower evidence refs:

```text
corpus_cache.document_objects:obj_123
media_manager.media_assets:asset_456
private_catalog.semantic_entities:entity_789
```

A richer evidence reference should include:

```yaml
evidence_ref:
  namespace: corpus_cache
  table: document_objects
  id: obj_123
  kind: table
  source_item_id: src_456
  artifact_id: art_789
  locator:
    page_start: 3
    page_end: 3
    bbox: null
    time_range: null
    byte_range: null
  provenance:
    producer: evidence-cli
    producer_version: 0.3.0
    profile: docling_ocr
    source_sha256: "..."
    config_hash: "..."
  confidence:
    value: 0.92
    basis: extraction
```

### 15.3 Treat search indexes as disposable projections

FTS/vector/graph indexes should hydrate back to SQLite/evidence refs.

They should store:

- evidence ref;
- source item ID;
- object ID;
- model/index profile;
- score metadata;
- snippet;
- projection build watermark.

They should not store the only copy of private semantic truth.

### 15.4 Keep semantic observations separate from reviewed facts

A model output such as:

```text
This image probably shows an Audi A3.
```

should be stored as an observation/proposal.

A reviewed fact such as:

```text
This media asset depicts my Audi A3.
```

belongs in the private semantic catalog and should link back to evidence.

### 15.5 Use topic handoff manifests

Topic managers should consume selected evidence slices:

```yaml
handoff_id: vehicle_2026_001
topic: vehicle
evidence:
  - ref: corpus_cache.documents:doc_123
    role: invoice
    confidence: reviewed
  - ref: media_manager.media_assets:asset_456
    role: visual_evidence
    confidence: proposed
  - ref: private_catalog.semantic_entities:entity_789
    role: vehicle_entity
    confidence: reviewed
```

This prevents topic managers from becoming duplicate crawlers.

---

## 16. Most Useful Systems to Inspect First

Recommended inspection order:

1. **Docling** — lower document object model and artifact generation.
2. **Paperless-ngx** — personal document workflow, OCR, tags, correspondents, custom fields, review UX.
3. **Immich / digiKam** — media asset model, face/object search, EXIF, albums, long-term photo metadata.
4. **Dogsheep + HPI** — personal data source adapters into local SQLite.
5. **Graphiti/Zep** — temporal entities, changing facts, hybrid graph/full-text/vector retrieval.
6. **Cognee** — agent memory control-plane vocabulary over documents/data/graphs.
7. **R2R** — production RAG API, hybrid search, multimodal ingestion, KG, document management.
8. **GraphRAG + LightRAG + RAPTOR + HippoRAG + RAG-Anything** — retrieval architecture patterns.
9. **W3C PROV + RO-Crate + OpenLineage** — evidence refs, model-run provenance, handoff manifests.
10. **Obsidian/Logseq/Zotero** — upper curated human-readable knowledge layer.

---

## 17. Practical Build Recommendation

The first vertical slice should be deliberately narrow.

### Suggested slice

```text
1. Scan one small source folder.
2. Parse a few documents with Docling.
3. Register lower evidence refs.
4. Ingest a few media files.
5. Create media assets and generated observations.
6. Build Tantivy full-text projection.
7. Build LanceDB vector projection.
8. Create one reviewed semantic entity.
9. Link document and media evidence to that entity.
10. Create one topic handoff manifest.
11. Promote one short Markdown source-map note.
```

### Example topic

```text
vehicle
```

### Example query

```text
Show all evidence related to the Audi sale.
```

### Expected result

The system should return:

- parsed document evidence;
- a relevant table or clause;
- a media asset or visual observation;
- a reviewed vehicle entity;
- an event grouping;
- provenance for each item;
- a handoff manifest for the vehicle topic;
- a short curated knowledge-base note.

This proves the architecture without prematurely building a giant system.

---

## 18. Final Conclusion

The evidence-memory idea is well supported by existing tools and literature, but no single tool implements it end-to-end.

The strongest implementation path is not to build a monolithic app. It is to build a set of layers connected by stable evidence references:

```text
lower public evidence engine
+ private control plane
+ media/domain extension
+ private semantic catalog
+ curated Markdown knowledge base
+ topic handoff manifests
```

The reusable technical kernel should be:

```text
source item
artifact
object
observation
projection
evidence ref
review state
promotion state
handoff item
```

The conceptual moat is the refusal to confuse machine-generated retrieval material with reviewed human knowledge.

That is what makes the architecture stronger than ordinary RAG, stronger than a document manager, and more extensible than a normal personal wiki.

---

## 19. Source Index

### Architecture source

- `evidence_memory_consolidation_handover.md` — local-first evidence memory architecture, layer split, evidence refs, private catalog, promotion lifecycle, and topic handoffs.

### Libraries and applications

- Docling: https://www.docling.ai/
- Unstructured partitioning docs: https://docs.unstructured.io/open-source/core-functionality/partitioning
- Apache Tika: https://tika.apache.org/
- Paperless-ngx: https://docs.paperless-ngx.com/
- SQLite: https://sqlite.org/
- Tantivy: https://github.com/quickwit-oss/tantivy
- LanceDB: https://github.com/lancedb/lancedb
- Dogsheep: https://github.com/dogsheep/dogsheep.github.io
- HPI: https://github.com/karlicoss/HPI
- Promnesia: https://github.com/karlicoss/promnesia
- Obsidian local data storage: https://obsidian.md/help/data-storage
- Logseq: https://logseq.com/
- Zotero: https://www.zotero.org/
- Immich: https://github.com/immich-app/immich
- PhotoPrism: https://www.photoprism.app/
- digiKam documentation: https://docs.digikam.org/en/asset_management/organize_find.html
- R2R: https://github.com/SciPhi-AI/R2R
- Cognee: https://www.cognee.ai/
- Graphiti: https://github.com/getzep/graphiti
- Mem0: https://github.com/mem0ai/mem0
- Letta: https://www.letta.com/
- AnythingLLM: https://github.com/Mintplex-Labs/anything-llm
- Khoj: https://docs.khoj.dev/
- Open WebUI Knowledge: https://docs.openwebui.com/features/workspace/knowledge/

### Research and standards

- GraphRAG: https://www.microsoft.com/en-us/research/project/graphrag/
- LightRAG: https://arxiv.org/abs/2410.05779
- RAPTOR: https://arxiv.org/abs/2401.18059
- HippoRAG: https://arxiv.org/abs/2405.14831
- RAG-Anything: https://arxiv.org/abs/2510.12323
- W3C PROV-DM: https://www.w3.org/TR/prov-dm/
- RO-Crate: https://www.researchobject.org/ro-crate/
- OpenLineage: https://openlineage.io/
- PROV-AGENT: https://arxiv.org/abs/2508.02866
- Vannevar Bush, “As We May Think”: https://www.theatlantic.com/magazine/archive/1945/07/as-we-may-think/303881/
- MyLifeBits: https://cacm.acm.org/research/mylifebits/
- Haystack paper: https://ceur-ws.org/Vol-55/huynh.pdf
- NEPOMUK: https://nepomuk.semanticdesktop.org/
- Local-first software paper: https://martin.kleppmann.com/papers/local-first.pdf
- DataHub: https://datahub.com/
- OpenMetadata: https://open-metadata.org/
- Dagster software-defined assets: https://dagster.io/glossary/software-defined-assets
- lakeFS: https://github.com/treeverse/lakeFS
- DVC: https://dvc.org/
