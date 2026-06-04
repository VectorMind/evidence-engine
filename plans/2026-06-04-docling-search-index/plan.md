# Plan: Docling Search Index

Date: 2026-06-04
Status: Not started. Survey review pending.

## Gate

Review `survey.md` before approving an implementation plan. This plan should
not commit to a storage backend, embedding provider, CLI surface, or indexing
schema until the survey findings are accepted or revised.

## Draft Scope

- Decide whether the first implementation should be a local LanceDB-backed
  hybrid index, a direct Tantivy FTS index paired with a vector store, or a
  smaller proof of concept.
- Define the chunk record schema, including source URI, document identity,
  page/section provenance, chunk text, FTS text, embedding vector, and Docling
  structure metadata.
- Define CLI commands for ingesting sources, rebuilding indexes, searching by
  FTS/vector/hybrid modes, and reporting index health.
- Define fixtures and proof commands for `test.md`.

## Exit Criteria

- An approved backend choice and schema.
- A concrete implementation sequence with dependencies.
- Test proof that covers ingestion, indexing, search, provenance, and rebuild or
  refresh behavior.
