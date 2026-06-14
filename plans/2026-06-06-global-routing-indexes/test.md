# Test Proof: Global Routing Indexes

Date: 2026-06-14
Status: D0/D1 runtime proof recorded.

## Commands And Checks

| Check | Expected | Actual |
| --- | --- | --- |
| List repo root. | Confirm project shape and workflow files. | Found Python CLI repo with `src`, `tests`, `docs`, `plans`, `specifications`, `catalog.yaml`, and config files. |
| List target plan folder. | Confirm existing hand-in and missing required plan files. | Folder contained `handing-in.md` only before this packet. |
| `git status --short` | Identify dirty worktree and avoid unrelated edits. | Existing unrelated modifications were present outside this plan folder. |
| Read `handing-in.md`. | Extract proposed architecture. | Found proposal for SQLite truth, root-scoped indexes, global representatives, lossy summaries, routing, widening, usage tracking, and collections. |
| Read README, workflow, spec, schema, configs, and selected source files. | Compare hand-in to current repo purpose and contracts. | Confirmed current implementation includes catalog, scan, parse, media inspect/describe, root-scoped FTS, semantic search, hybrid search, image search, and global representative routing. |
| Review active plan references. | Ensure active packet does not depend on superseded drafts for implementation scope. | `plan.md` is now self-contained; `plans/open.md` points at `plan.md` instead of archived drafts. |
| Review schema landing details. | Make `summary_nodes` implementable from the plan. | `plan.md` now specifies columns, indexes, fixed projection paths, document/media summary behavior, build command, route trace, fallback behavior, and test expectations. |
| `uv run pytest tests/test_routing.py` | Routing-focused tests pass. | Passed: 7 tests. Covers catalog version/table, CLI parser, fake-summary indexing, document-only prompt isolation, media album summaries, routed media search, and routed document search. |
| `uv run pytest` | Full suite passes. | Passed: 32 tests. |
| `uv run ruff check .` | Lint is clean. | Passed: all checks. |

## Review Result

The planning packet is internally consistent with repository workflow:

- `survey.md` records the local inventory and critique.
- `plan.md` records scoped planning, closed design points, D0/D1 implementation
  phases, `summary_nodes` schema proposal, risks, and exit criteria.
- `implementation.md` records the D0/D1 implementation facts.
- `test.md` records planning-review proof and runtime proof.

## Runtime Tests

The first sandboxed `uv run pytest tests/test_routing.py` attempt could not
access the normal uv cache directory; the command was rerun with approved cache
access. Full-suite and ruff checks also used approved cache access.

Automated tests use a fake summary generator so the suite does not require a
local model. The D1 media summary path has not yet been manually proven with a
live Ollama model on a real media folder.
