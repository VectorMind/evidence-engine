# Test Proof: Global Routing Indexes

Date: 2026-06-14
Status: D0 runtime proof recorded.

## Commands And Checks

| Check | Expected | Actual |
| --- | --- | --- |
| List repo root. | Confirm project shape and workflow files. | Found Python CLI repo with `src`, `tests`, `docs`, `plans`, `specifications`, `catalog.yaml`, and config files. |
| List target plan folder. | Confirm existing hand-in and missing required plan files. | Folder contained `handing-in.md` only before this packet. |
| `git status --short` | Identify dirty worktree and avoid unrelated edits. | Existing unrelated modifications were present outside this plan folder. |
| Read `handing-in.md`. | Extract proposed architecture. | Found proposal for SQLite truth, root-scoped indexes, global representatives, lossy summaries, routing, widening, usage tracking, and collections. |
| Read README, workflow, spec, schema, configs, and selected source files. | Compare hand-in to current repo purpose and contracts. | Confirmed current implementation includes catalog, scan, parse, media inspect/describe, root-scoped FTS, semantic search, hybrid search, and image search; global routing is still pending. |
| Review active plan references. | Ensure active packet does not depend on superseded drafts for implementation scope. | `plan.md` is now self-contained; `plans/open.md` points at `plan.md` instead of archived drafts. |
| Review schema landing details. | Make `summary_nodes` implementable from the plan. | `plan.md` now specifies columns, indexes, fixed projection paths, D0 write behavior, build command, route trace, fallback behavior, and test expectations. |
| `uv run pytest tests/test_routing.py` | Routing-focused tests pass. | Passed: 5 tests. Covers catalog version/table, CLI parser, fake-summary indexing, media exclusion, and routed search. |
| `uv run pytest` | Full suite passes. | Passed: 30 tests. |
| `uv run ruff check .` | Lint is clean. | Passed: all checks. |

## Review Result

The planning packet is internally consistent with repository workflow:

- `survey.md` records the local inventory and critique.
- `plan.md` records scoped planning, closed design points, D0 implementation
  phases, `summary_nodes` schema proposal, risks, and exit criteria.
- `implementation.md` records the D0 implementation facts.
- `test.md` records planning-review proof and runtime proof.

## Runtime Tests

The first sandboxed `uv run pytest tests/test_routing.py` attempt could not
access the normal uv cache directory; the command was rerun with approved cache
access. A later test failure was a fixture bug in the new test and was fixed
before the final passing runs above.

Manual local-Ollama summary proof was not run. Automated tests use a fake
summary generator so the suite does not require a local model.
