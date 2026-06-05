# Test: Docling Search Index

Date: 2026-06-04
Status: Planning proof only. No implementation to test yet.

## Proof So Far

- Read the existing plan packet:
  `plans/2026-06-04-docling-search-index/{survey.md,plan.md,implementation.md,test.md,deep-research-report.md}`.
- Read the upstream consumer handoff:
  `C:\dev\wassfila\documents-manager\plans\2026-06-05-personal-document-index\handoff.md`.
- Read the upstream workflow:
  `C:\dev\wassfila\documents-manager\WORKFLOW.md`.
- Read the upstream personal document index plan:
  `C:\dev\wassfila\documents-manager\plans\2026-06-05-personal-document-index\plan.md`.
- Listed repository files with `rg --files`; this workspace currently contains
  planning/specification scaffolding only and no Python package metadata.
- Checked `git status --short`; only `deep-research-report.md` was already
  untracked before this planning update.
- Added planning/specification files only; no runtime commands or dependency
  installation were run.
- Read the 2026-06-05 reference handoff:
  `C:\dev\wassfila\documents-manager\plans\2026-06-05-personal-document-index\handoff.md`.
- Reviewed `MicroWebStacks/content-structure` via GitHub and fetched its
  `catalog.yaml`, `src/blob_manager.js`, `src/structure_db.js`, and `cli.js`
  for the thresholded blob-storage analysis.
- Added root `catalog.yaml` for schema review.
- Rewrote `plans/2026-06-04-docling-search-index/plan.md` with OP-001 through
  OP-015, concrete `agents-docs` examples, root layout scope, Docling mapping,
  blob-storage analysis, embedding candidates, and new open points.
- Rewrote `specifications/corpus-cache-cli/spec.md` so the durable spec matches
  the updated decisions.
- Tried to parse `catalog.yaml` with default Python:
  `python -c "import yaml, pathlib; ..."`. This failed because PyYAML is not
  installed.
- Tried to parse `catalog.yaml` with bundled Codex Python at
  `C:\Users\wassi\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe`.
  This also failed because PyYAML is not installed.
- Tried to parse `catalog.yaml` with bundled Node using `require('yaml')`. This
  failed because the `yaml` package is not installed.
- Before the catalog review rewrite, ran structural checks with `rg` confirming
  the former schema shape contained `exposure_kinds`, `storage_profiles`,
  `database_exposures`, `document_objects`, `chunk_records`,
  `embedding_profiles`, `tantivy_indexes`, `lancedb_stores`, and
  `command_runs`.
- Ran structural checks with `rg` confirming `catalog.yaml` no longer contains
  nested `fields:`, malformed empty `values: }`, or accidental table entries
  formatted as column maps.
- Ran a read-only Python structural scanner confirming
  `old_style_column_entries=0` under `columns:` blocks.
- Tried to parse the updated `catalog.yaml` with Python `yaml`; this could not
  run because PyYAML is not installed in the active Python environment.
- Ran cross-file checks with `rg` confirming the plan/spec mention
  `agents-docs`, stdlib `sqlite3`, no SQL data-access wrapper, `one_per_folder`,
  and the new open points.
- Ran ASCII/no-tab checks with Python. `catalog.yaml`,
  `plans/2026-06-04-docling-search-index/plan.md`, and
  `specifications/corpus-cache-cli/spec.md` are ASCII-only; `catalog.yaml` has
  no tab characters.
- Updated catalog review split and added `config/exposures.yaml`,
  `config/embeddings.yaml`, and `store_templates.yaml`.
- Removed catalog tables for migration history, database exposure registry,
  document versions, catalog chunks, chunk/object links, embedding profiles,
  lower-index row internals, index jobs, command runs, and command messages.
- Ran `rg` against `catalog.yaml` for the removed table names and stale catalog
  fields; no matches were found.
- Ran a read-only Python structural scanner confirming
  `old_style_column_entries=0` for both `catalog.yaml` and
  `store_templates.yaml`.
- Ran ASCII/no-tab checks on `catalog.yaml`, `config/exposures.yaml`,
  `config/embeddings.yaml`, `store_templates.yaml`,
  `specifications/corpus-cache-cli/spec.md`, and
  `plans/2026-06-04-docling-search-index/plan.md`; all are ASCII-only and have
  no tab characters.

No runtime proof is expected before the revised schema plan is accepted and an
implementation starts.

## Future Proof Targets

- Convert at least one PDF or Markdown source through Docling.
- Persist Docling artifacts and SQLite catalog records for source items,
  current documents, objects, valuable items, blobs, and index scopes.
- Build or refresh Tantivy FTS indexes over generated chunks derived from
  catalog objects.
- Build or refresh scoped LanceDB vector stores over generated chunks derived
  from catalog objects.
- Query in FTS, vector, and hybrid modes.
- Show expected versus actual search hits for a small fixture corpus.
- Show that search results hydrate provenance through SQLite instead of relying
  on lower indexes as the catalog.
- Record index health, rebuild, refresh, and deletion commands.
- Prove the manager-repository contract with a synthetic source manifest and
  structured JSON/JSONL outputs under `.results/`.
