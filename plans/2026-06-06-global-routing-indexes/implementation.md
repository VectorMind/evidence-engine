# Implementation Log: Global Routing Indexes

Date: 2026-06-06
Status: Planning packet created. No runtime implementation changes.

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
  OP-020) into the plan's tracking table and resolved them by accepting the
  `old-plan.md` defaults.
- Added an OP-001..OP-020 traceability table; noted that F3 reverses OP-010's
  extractive-first default and F2 reverses old Phase-3 index registration.
- New decisions: S5 (media-bearing documents treated as folders of images,
  `container_kind` column), M7 (absent-facet renormalization + skipped widening
  rungs), RRF as the V1 cross-route merge rule (F4).
- Clarified F2: vectors never enter SQLite; per-profile rebuild sources (text
  from SQLite alone; siglip from `summary_nodes` medoid IDs + per-scope
  LanceDB stores).
- Runtime change: renamed `AGENTS_DOCS_OLLAMA_RERANK_MODEL` to
  `EVEN_OLLAMA_RERANK_MODEL` in `src/even/hybrid.py` (pre-rebrand leftover);
  decided the `EVEN_` prefix as the env-flag convention.
- Updated `plans/open.md` status row and marked `old-plan.md` superseded for
  decision tracking.

## Follow-Up Risks

- `plan.md` has many open points by design. It should not be used as
  implementation approval until the required OP items are resolved.
- Any accepted schema change must update `catalog.yaml`, migration tests, and
  the durable spec if it becomes a public contract.

