# Handoff: Consumer Contract And Skills Wrappers

Date: 2026-06-05
Status: Draft. Scope corrected.

## Purpose

Clarify the boundary between `agents-cli`, manager repositories, and central
skills for corpus-cache work.

## Corrected Boundary

`agents-cli` owns the reusable CLI implementation for the corpus cache:

- source manifest ingestion;
- Docling parsing and artifact registration;
- SQLite catalog migrations and read/query/export behavior;
- Tantivy FTS build, refresh, search, status, rebuild, and deletion;
- LanceDB semantic build, refresh, search, status, rebuild, and deletion;
- hybrid search routing and result hydration;
- health checks and redaction-safe diagnostics;
- structured JSON/JSONL command reports.

Central `.agents/skills` may wrap these commands, choose when to call them, and
manage dependency installation. They do not own the indexing internals.

Manager repositories are the customers. They provide private source scope,
policy, and output paths. They should not need to understand Tantivy directories
or LanceDB table layouts.

## What Manager Repositories Provide

Manager repositories provide explicit inputs:

- source manifest;
- corpus cache root;
- privacy and redaction policy;
- include/exclude rules;
- parse, FTS, semantic, SQL, and embedding profiles;
- budget caps;
- approval state for OCR, remote services, and expensive local models;
- desired output format.

No command should require a personal default from this repository.

## What `agents-cli` Returns

Commands return structured output:

- command name and schema version;
- tool versions and config hash;
- run ID and cache root;
- created, changed, skipped, deferred, failed, and stale counts;
- stable IDs for source roots, documents, versions, objects, valuable items,
  search units, FTS indexes, semantic stores, and runs;
- fatal errors separated from retryable, deferred, stale, or policy-denied work;
- redacted paths and text by default.

## CLI Capability Groups

The CLI must cover:

- initialization;
- inventory/inspection;
- Docling parsing;
- SQL catalog migration, status, import, export, and read-only query;
- FTS build, refresh, search, status, rebuild, and deletion;
- semantic build, refresh, search, status, rebuild, and deletion;
- lexical, semantic, and hybrid search;
- health diagnostics;
- manager handoff export.

## Dependency Expectations

It is acceptable for this repository to install and test dependencies locally
while developing the CLI. Later, central skills can depend on package extras.

Expected dependency groups:

- base CLI/runtime: `pydantic`, `typer` or `click`, `rich`, `orjson`,
  `zstandard`;
- document parsing: `docling`;
- FTS: `tantivy`;
- semantic indexing: `lancedb`, `pyarrow`, `numpy`;
- local embeddings: `fastembed` as the first lightweight candidate;
- optional heavy embeddings: `sentence-transformers`;
- optional SQLite support: `apsw` only if stdlib `sqlite3` is insufficient.

External OCR tools are opt-in and checked by health commands.

## Skills Wrapper Role

Central skills may:

- gather user approval;
- write source manifests;
- choose budget and policy flags;
- call this CLI;
- parse JSON/JSONL reports;
- summarize results;
- help manager repositories consume handoff exports.

Central skills should not:

- derive stable IDs;
- manage SQLite migrations;
- define Tantivy schemas;
- define LanceDB layout;
- implement hybrid score fusion;
- store private defaults for this public package.

## Open Boundary Questions

- Which public command name should be stabilized?
- Should manager repos call the CLI only through subprocess, or should a Python
  facade be supported for direct package use?
- Should handoff exports be JSONL only, or should SQLite views be considered a
  first-class interface?
- Which dependency extras should central skills install by default?
