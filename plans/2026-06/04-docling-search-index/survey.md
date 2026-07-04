# Survey: Docling Documents To FTS And Semantic Search

Date: 2026-06-04
Status: Draft for review before planning

## Goal

Survey existing local and upstream work for converting Docling output into a
searchable index with both full-text search and semantic/vector retrieval. The
main candidate stack from this survey is Docling for conversion and chunking,
LanceDB for local vector plus FTS plus hybrid search, and Tantivy as either a
lower-level FTS alternative or an implementation detail behind older LanceDB
FTS paths.

## Local Inventory

The current workspace has no existing search-index implementation. A repository
scan found:

- `skills/document-ingest/SKILL.md`, which defines when to escalate document
  extraction to Docling.
- `skills/document-ingest/references/docling.md`, which documents basic Docling
  CLI and Python conversion usage.
- No local code or docs for LanceDB, Tantivy, vector search, FTS, hybrid search,
  embeddings, or indexed retrieval.

If the intended target is a separate `agents-cli` repository outside this
workspace, the local inventory should be rerun there before implementation
planning.

## Existing Upstream Work

### Docling first-party path

Docling already provides the document conversion and chunking half of the
pipeline. It converts many source formats into a `DoclingDocument`, can export
Markdown/HTML/text/lossless JSON, and has native chunkers that operate directly
on the document model. Its chunking docs describe two approaches: export to
Markdown and split later, or use native chunkers that stream text chunks with
metadata from the `DoclingDocument`.

Docling also has official or first-party-adjacent integration paths for:

- LangChain via `langchain-docling` and `DoclingLoader`, with export modes for
  document chunks or Markdown and support for custom chunkers.
- LlamaIndex via Docling Reader and Docling Node Parser. The reader can populate
  LlamaIndex documents from Docling output, and the node parser turns those
  documents into nodes/chunks for downstream indexing.
- Haystack via a Docling converter component for pipeline-based ingestion.

Docling examples include RAG flows using Azure AI Search, Milvus, OpenSearch,
Weaviate, Qdrant, MongoDB plus VoyageAI, LangChain, LlamaIndex, and Haystack.
This is useful precedent for chunking and provenance, but I did not find a
first-party Docling example that specifically standardizes on LanceDB plus local
FTS as the canonical backend.

### LanceDB

LanceDB is the strongest single-backend candidate for a first implementation
because it supports:

- Vector search over embedding columns.
- BM25 full-text search over text columns.
- Hybrid search that combines vector and FTS results, with reciprocal-rank
  fusion as the default reranking approach and optional other rerankers.
- SQL-style filtering over metadata fields.
- Local embedded storage for a CLI workflow.

The current LanceDB docs distinguish vector indexes, FTS indexes, and hybrid
search. Important implementation implications:

- For LanceDB OSS, vector indexes are managed manually with `create_index()`.
- FTS indexes are created on text columns with `create_fts_index(...)`.
- New rows after index creation can remain in unindexed fragments until
  optimization/index refresh behavior catches up. A CLI should expose an index
  health or optimize/rebuild command instead of hiding this.
- Current LanceDB docs describe Lance-native FTS. Older Tantivy-based FTS docs
  exist and mention limitations such as Python synchronous API only, local
  filesystem limitations, and no incremental index build on object storage.
  Prefer LanceDB native FTS unless a specific requirement needs Tantivy.

### Tantivy

Tantivy is a lower-level Rust full-text search library inspired by Lucene. It
supports schemas, tokenizers, BM25 scoring, phrase queries, facets, incremental
indexing, and commits/reloads to make indexed documents searchable. It is a good
fit when the CLI itself is Rust or when we need fine control over lexical search
behavior.

Tantivy alone does not solve semantic search. A direct-Tantivy architecture
would still need a vector store, embedding pipeline, result fusion, and metadata
store. That makes it more flexible but also more work than a LanceDB-first
implementation.

### Concrete existing project: haiku.rag

`haiku.rag` is the closest matching open-source project found in this survey. It
is an agentic RAG system built on Docling, LanceDB, and Pydantic AI. Its docs
describe:

- Local-first embedded LanceDB storage.
- Docling-based document processing, including stored `DoclingDocument`
  structure.
- Vector, FTS, and hybrid search modes.
- Reciprocal-rank fusion for hybrid search.
- CLI commands for adding sources, searching, asking questions, inspecting
  chunks, creating vector indexes, rebuilding, and migrations.
- Provenance and citations using page numbers and section headings.

This is strong evidence that the Docling + LanceDB shape is workable. It also
suggests features worth considering or deliberately deferring: full stored
DoclingDocument blobs, migration support, visual grounding, file watching,
continuous ingestion, and MCP exposure.

## Candidate Architectures

### Option A: LanceDB-first hybrid index

Use Docling for conversion/chunking and LanceDB for a single local table of
chunks. Store chunk text, FTS text, embedding vector, source metadata, page and
heading provenance, content type labels, and enough Docling references to
rebuild or expand context.

Pros:

- One backend for vector, FTS, metadata filters, and hybrid search.
- Good fit for Python CLI tooling already used by this repository.
- Fewer moving parts than pairing Tantivy with a separate vector store.
- Existing `haiku.rag` validates the shape.

Cons:

- Need to track LanceDB index lifecycle and version-specific FTS behavior.
- LanceDB dependency weight is larger than pure FTS.
- Hybrid quality still depends heavily on embedding model, chunking, reranking,
  and evaluation fixtures.

### Option B: Direct Tantivy plus vector store

Use Tantivy for FTS and pair it with LanceDB, SQLite vector extensions, or
another vector backend for embeddings. Fuse results in the CLI.

Pros:

- Strong lexical control and Rust-native performance if the CLI is Rust.
- Clear ownership over tokenizers, fields, scoring, and commits.
- Can be made independent of LanceDB FTS changes.

Cons:

- Requires more glue code: metadata store, vector store, result fusion, index
  rebuild semantics, and health reporting.
- Python-only workflows would need Tantivy bindings or a Rust CLI package.
- More surface area to test before it becomes reliable.

### Option C: Framework-mediated RAG

Use LangChain, LlamaIndex, or Haystack adapters around Docling and a vector
store/search backend.

Pros:

- Fastest prototype path if the goal is only RAG.
- Existing Docling integrations already handle part of conversion/chunking.

Cons:

- Framework abstractions can hide index schema and lifecycle details.
- Less ideal for a reusable CLI contract where files, stdout, exit codes, and
  reproducible test proof matter.
- May add dependency and version churn without solving local search ownership.

## Recommended Direction

Start with Option A: a LanceDB-first local hybrid index. Keep Tantivy in the
survey as a fallback or future optimization, not the initial backend. This keeps
the first implementation close to the current Python/uv environment and gives
one storage engine for FTS, vectors, filters, and hybrid ranking.

The first implementation plan should be deliberately narrow:

- Convert source documents through Docling.
- Chunk with Docling native chunkers first, likely `HybridChunker` or
  hierarchical chunking depending on fixtures.
- Store one row per searchable chunk in LanceDB.
- Include stable chunk IDs, source URI/path, document title if known, page
  numbers, headings, content labels, text for display, text for FTS, embedding
  vector, and Docling references or serialized structure as needed.
- Provide CLI commands for ingest, search, index status, optimize/rebuild, and
  export/debug of stored chunks.
- Test on a tiny fixture corpus before adding continuous ingestion or MCP.

## Questions For Review

- Is the target repository this workspace or a separate `agents-cli` repo?
- Should the first CLI be Python to fit the current central `uv` environment, or
  Rust to make direct Tantivy more natural?
- Should embeddings be local-only by default, remote-capable, or configurable
  with no default?
- How much Docling structure should be stored: chunk metadata only, full
  `DoclingDocument` JSON, or compressed full-document blobs?
- Should visual grounding/page-image support be in scope for v1, or deferred?

## Sources

- Docling repository: https://github.com/docling-project/docling
- Docling usage: https://docling-project.github.io/docling/usage/
- Docling chunking: https://docling-project.github.io/docling/concepts/chunking/
- Docling integrations: https://docling-project.github.io/docling/integrations/
- Docling LangChain integration: https://docling-project.github.io/docling/integrations/langchain/
- Docling LlamaIndex integration: https://docling-project.github.io/docling/integrations/llamaindex/
- Docling Haystack integration: https://docling-project.github.io/docling/integrations/haystack/
- LanceDB FTS: https://docs.lancedb.com/search/full-text-search
- LanceDB hybrid search: https://docs.lancedb.com/search/hybrid-search
- LanceDB vector search: https://docs.lancedb.com/search/vector-search
- LanceDB vector indexes: https://docs.lancedb.com/indexing/vector-index
- LanceDB FTS indexes: https://docs.lancedb.com/indexing/fts-index
- Legacy LanceDB Tantivy FTS docs: https://lancedb.github.io/lancedb/fts_tantivy/
- Tantivy repository: https://github.com/quickwit-oss/tantivy
- Tantivy docs: https://docs.rs/tantivy/latest/tantivy/
- haiku.rag repository: https://github.com/ggozad/haiku.rag
- haiku.rag Python API: https://ggozad.github.io/haiku.rag/python/
- haiku.rag CLI: https://ggozad.github.io/haiku.rag/cli/
