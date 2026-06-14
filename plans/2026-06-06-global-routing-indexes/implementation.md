# Implementation Log: Global Routing Indexes

Date: 2026-06-06
Status: D0 implemented. Media representative routing remains a follow-on slice.

## Changes Made

- Added `survey.md` with local repo inventory and critique of the hand-in.
- Added `plan.md` with problem summary, fit assessment, constrained scope,
  open design points, phases, risks, and exit criteria.
- Added this implementation log to satisfy the dated plan packet workflow.
- Added `test.md` with planning-review proof.

## Important Decisions

- Treated `handing-in.md` as architecture input, not approved implementation
  scope.
- Kept generated chunks and lower-index backend rows out of SQLite in the
  proposed direction.
- Framed global representative indexes as a later accepted slice after open
  design points are resolved.
- Recommended global representative FTS before global representative LanceDB.

## Deviations

- The user asked mainly for a new `plan.md`; this packet also adds
  `survey.md`, `implementation.md`, and `test.md` because repository workflow
  requires every dated plan folder to contain `plan.md`, `implementation.md`,
  and `test.md`, and discovery-heavy planning should include `survey.md`.

## 2026-06-11: Decision record closed

- Rewrote `plan.md` as a full decision record (Problem summary / Resolution
  summary first, then decision tables). All F/S/M/D points marked Decided.
- Carried the seven previously untouched open points (OP-007, OP-013..OP-017,
  OP-020) into the plan's tracking table and resolved them.
- Added an OP-001..OP-020 traceability table; noted that F3 reverses OP-010's
  extractive-first default and F2 rejects catalog registration for global
  representative indexes.
- New decisions: S5 (media-bearing documents treated as folders of images,
  `container_kind` column), M7 (absent-facet renormalization + skipped widening
  rungs), RRF as the V1 cross-route merge rule (F4).
- Clarified F2: vectors never enter SQLite; per-profile rebuild sources (text
  from SQLite alone; siglip from `summary_nodes` medoid IDs + per-scope
  LanceDB stores).
- Runtime change: renamed `AGENTS_DOCS_OLLAMA_RERANK_MODEL` to
  `EVEN_OLLAMA_RERANK_MODEL` in `src/even/hybrid.py` (pre-rebrand leftover);
  decided the `EVEN_` prefix as the env-flag convention.
- Updated `plans/open.md` status row.

## 2026-06-14: Implementation readiness pass

- Rewrote `plan.md` into a self-contained implementation plan for D0, so active
  implementation scope no longer depends on archived drafts.
- Added D0 goal, scope, non-goals, implementation phases, dependencies, risks,
  exit criteria, and test expectations.
- Sharpened the `summary_nodes` catalog proposal with concrete columns,
  indexes, nullable media fields, current-state status fields, canonical
  `source_refs_json`, and schema-version/reset expectations.
- Added the expected representative FTS template and fixed global projection
  paths while preserving the decision that global representative stores are not
  registered in catalog tables.
- Added the explicit `even index routing <path>` build-command proposal so
  normal `index scope` behavior does not become model-bound.
- Added routed `search text` behavior, route trace shape, D0 thresholds, and
  fallback-all-current-FTS behavior.
- Refreshed `test.md` to reflect the repo's current parse/index/search
  implementation state.
- Updated `plans/open.md` to point only at the active implementation-ready plan.

## 2026-06-14: D0 implementation

- Added `summary_nodes` to `catalog.yaml` and bumped the catalog schema/user
  version to `0.7` / `7`.
- Added the `fts_summary_node` store template, fixed global representative
  exposure paths, `config/routing.yaml`, and `config/README.md`.
- Added routing config loading and packaged the new config files in
  `pyproject.toml`.
- Implemented `src/even/routing.py` for document-only root summaries, local
  Ollama summary generation, fixed-path global representative FTS builds,
  sidecar manifest watermarks, routed `search text`, route traces, and fallback
  behavior.
- Added `even index routing <path>` with `--force`, `--limit`,
  `--summary-model`, and `--summary-ollama-url`.
- Updated FTS search to route by default for `search text`; `search hybrid`
  explicitly keeps the existing all-current-FTS candidate behavior.
- Updated README and the durable CLI spec for `summary_nodes`, `index routing`,
  fixed-path global representative projections, and routed `search text`.
- Added `tests/test_routing.py` covering catalog schema/version, parser surface,
  fake-summary indexing, media exclusion from D0 summaries, and routed search
  over a multi-root fixture.

## Follow-Up Risks

- Media representatives are not implemented in D0.
- Manual Ollama proof was not run; automated tests use a fake summary generator
  so CI does not require a local model.
