# Test: Knowledge Layers Merge

Date: 2026-06-07
Status: Runtime proof complete.

## Review Proof

This packet now includes code changes. Runtime proof is recorded below as tests
are run.

Files reviewed:

- `README.md`
- `specifications/corpus-cache-cli/spec.md`
- `catalog.yaml`
- `src/documents_manager/cli.py`
- `plans/2026-06/04-docling-search-index/plan.md`
- `plans/2026-06/04-docling-search-index/implementation.md`
- `plans/2026-06/06-parse-memory-failures/plan.md`
- `plans/2026-06/06-parse-memory-failures/implementation.md`
- `plans/2026-06/06-global-routing-indexes/plan.md`
- `plans/2026-06/06-global-routing-indexes/survey.md`
- `plans/2026-06/07-knowledge-layers/merge-plan.md`
- `plans/2026-06/07-knowledge-layers/evidence-memory-survey.md`
- `plans/2026-06/07-knowledge-layers/evidence_memory_consolidation_handover.md`

Expected result:

- `plan.md` exists in the dated plan folder.
- The plan includes problem and resolution summaries.
- The plan includes current and proposed CLI surfaces.
- The plan separates small open points from big design decisions.
- The plan accounts for `private-documents`, `private-media`, media-manager
  scope reduction, and global routing indexes.
- The updated plan defers `handoff` from V1 scope.
- The updated open-points table includes proposal confidence and whether each
  point has one obvious option or several viable options.
- The updated plan removes `documents-manager` backward-compatibility requirements.
- The updated plan records `sources scan`, workspace-local results/reports,
  JSON-first output, and deferred MCP-inspired-at-most transport as direction.
- The implementation adds focused tests for:
  - new `sources scan` parser surface;
  - removal of old `scan folder`;
  - removal of `catalog migrate`;
  - JSON `health` output;
  - workspace-local `sources scan` catalog/result files.

Actual result:

- Planning-document checks are satisfied by review.
- `uv run pytest tests\test_cli_contract.py tests\test_parse_failure_reporting.py tests\test_hybrid_search.py`
  - Expected: focused tests pass for the new CLI contract and unchanged parse/search helpers.
  - Actual: 11 tests passed.
- `uv run ruff check .`
  - Expected: changed Python code passes lint.
  - Actual: all checks passed.
- `uv run pytest`
  - Expected: full test suite passes.
  - Actual before the final catalog reset-required tweak: 11 tests passed.
- `uv run documents-manager catalog status`
  - Expected: renamed console script runs and emits JSON with workspace-local
    catalog path.
  - Actual: status `missing`, expected user version `4`, expected tables include
    `fts_indexes` and `semantic_stores`, and `workspace_root` points at
    `.documents-manager`.
- Final rerun after changing stale/incomplete catalogs to return
  `reset_required` instead of migrating was attempted but blocked by the
  environment approval/usage limit. Remaining unverified risk is small and
  limited to that catalog reset branch.
