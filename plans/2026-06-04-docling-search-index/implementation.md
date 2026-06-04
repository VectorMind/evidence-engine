# Implementation: Docling Search Index

Date: 2026-06-04
Status: No implementation started.

## Notes

- Created the dated planning packet.
- Added `survey.md` as the review gate before implementation planning.
- No search-index code, dependency changes, or CLI behavior changes have been
  made for this work.

## Pending Decisions

- Backend: LanceDB-native hybrid search, direct Tantivy plus a vector store, or
  another local search stack.
- Embedding provider and default model.
- Chunking strategy and metadata schema.
- Whether this belongs in this repository's central `uv` tooling or in a
  first-class external CLI package consumed by skills.
