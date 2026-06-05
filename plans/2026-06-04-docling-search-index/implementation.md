# Implementation: Docling Search Index

Date: 2026-06-04
Status: Planning revised. No runtime implementation started.

## Notes

- Created the dated planning packet.
- Added `survey.md` as the review gate before implementation planning.
- Reviewed the documents-manager handoff for expected public lower-layer
  responsibilities.
- Revised `plan.md` around a split architecture: central SQLite metadata
  catalog, Tantivy FTS shards, scoped LanceDB vector stores, and preserved
  Docling artifacts.
- Added `handoff.md` for lower-layer expectations from `.agents/skills` and
  likely Python dependency groups.
- Read the `documents-manager` workflow and personal document index plan.
- Corrected the scope: `agents-cli` owns the reusable corpus-cache CLI
  implementation, while central skills are wrappers and manager repositories
  are customers.
- Added `WORKFLOW.md` with the repository's spec-driven process and plan shape.
- Added `specifications/corpus-cache-cli/spec.md` for binding corpus-cache CLI
  contracts.
- Rewrote `plan.md` around problem summary, resolution summary, objectives,
  open points, and implementation phases.
- Rewrote `handoff.md` as a consumer contract and skills-wrapper boundary.
- No search-index code, dependency changes, package scaffolding, or CLI behavior
  changes have been made for this work.
- Read the 2026-06-05 reference handoff from
  `C:\dev\wassfila\documents-manager\plans\2026-06-05-personal-document-index\handoff.md`.
- Reviewed the `MicroWebStacks/content-structure` repository, especially its
  root catalog, README, `src/blob_manager.js`, `src/structure_db.js`, and CLI.
- Added root `catalog.yaml` as the draft schema review surface for all SQLite,
  file, Tantivy, and LanceDB exposures.
- Updated `catalog.yaml` so dataset metadata is represented as direct entries
  (`dataset_role`, `durability`) instead of nested `fields`.
- Rewritten `catalog.yaml` table `columns` entries as one-line YAML maps in the
  form `{name: ..., type: ..., description: ...}`.
- Reworked `plan.md` with the user answers to OP-001 through OP-015, concrete
  `agents-docs` command examples, a root layout scope table, Docling mapping,
  blob-storage analysis, embedding profile candidates, and new open points.
- Rewrote `specifications/corpus-cache-cli/spec.md` to align with the reviewed
  decisions: stdlib `sqlite3`, no SQL data-access wrapper, chunk-only lower
  indexes, thresholded blob storage, and SQLite registry rows for file-based
  database islands.
- Applied the catalog review:
  removed `schema_migrations`, `database_exposures`, `document_versions`,
  `chunk_records`, `chunk_object_links`, `embedding_profiles`,
  `tantivy_indexes`, `tantivy_documents`, `lancedb_stores`, `lancedb_chunks`,
  `index_jobs`, `command_runs`, and `command_messages` from `catalog.yaml`.
- Replaced `document_versions` with current-state `documents`.
- Removed `chunk` from `document_objects.object_type`.
- Added `valuable_items` as a catalog table for current high-value document
  items.
- Added `config/exposures.yaml`, `config/embeddings.yaml`, and
  `store_templates.yaml` so backend settings and lower-index row shapes are not
  modeled as catalog tables.
- Rewrote `specifications/corpus-cache-cli/spec.md` and `plan.md` around the
  reviewed split: current-state catalog, config files, lower-index templates,
  and `.results/` command output.
- No runtime CLI/package implementation has been started.

## Pending Decisions

- Confirm blob thresholds and compression defaults.
- Confirm first Docling parser profiles.
- Define the exact generated chunking profile and copied lower-index metadata
  set for `store_templates.yaml`.
- Confirm whether LanceDB defaults to one store per folder or one store per
  root for the first proof.
- Choose the first embedding default.
- Decide when search commands enter scope after build/refresh/status commands.
- Pin dependency versions in `pyproject.toml`.
- Define the synthetic fixture set for first proofs.
