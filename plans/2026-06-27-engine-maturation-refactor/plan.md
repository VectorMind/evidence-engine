# Engine Maturation Refactor

## Problem Summary

A full review of `even` (2026-06-27) found the concept and five-layer
architecture sound and worth maturing, but the implementation carries one
structural hot spot and three systemic patterns that will fight reuse once
private workspaces consume the package as a library. None are correctness bugs;
all are reuse/maturation cleanups.

Findings (ranked):

1. **`routing.py` is a god module** — 3,672 lines / 126 defs (~31% of the
   codebase) mixing six responsibilities: the `index_routing` orchestrator,
   root/media/cluster summary generation, three representative-store backends,
   the routed-search engine, k-means/medoid math, and a
   budget/calibration/importance subsystem.
2. **Triplicated representative-store machinery** — near-identical
   `_write_global_*_index` / `_*_manifest_current` / `_write_*_manifest` /
   `_search_global_representatives*` families for FTS, semantic, and siglip
   (rule-of-three: build rows → check manifest watermark → write → search).
3. **Positional tuple row access** — `sqlite3.Row` is used exactly once in the
   whole codebase (`routing.py:2430`); everywhere else SQL rows are read by
   integer index (e.g. `chunks.py` reaches `row[14]` on a 15-column SELECT).
   Reordering a column silently corrupts downstream.
4. **No shared catalog access layer** — 33 hand-rolled
   `with sqlite3.connect(catalog_path()) as conn:` sites across 11 modules;
   `with sqlite3.connect(...)` also does not close the connection.
5. **Dead-weight fallback YAML parsers** — `config.py` and `catalog.py` keep
   stdlib-only `_load_*_fallback` parsers for a scaffold environment that no
   longer exists now that PyYAML is a hard base dependency
   (`pyproject.toml`). ~200 LOC unreachable in any supported install.
6. **Test coverage is routing-heavy** — 1,039 of 1,596 test lines are
   `test_routing.py`; parse/inventory/semantic/blobs have thin direct coverage.
7. **Tests are not hermetic against the new path env vars** — the 2026-06-27
   `path env var home` commit gave `EVEN_CACHE`/`EVEN_HOME` (and a cwd `.env`)
   precedence over `workspace_root()`, but tests only `monkeypatch.chdir`. When
   those vars are exported in the shell, the suite reads the real `~/.even`
   catalog and 12 tests fail (e.g. `assert 23 == 1`). The suite must clear the
   even env vars so it is isolated regardless of the developer's shell.

Minor: Ollama plumbing is split between `ollama.py` (image generation) and
inline urllib in `routing.py` (text generation).

## Resolution Summary

Land the cleanups in risk order: mechanical/low-risk systemic fixes first
(catalog access layer + Row factory, delete dead fallbacks), then the
representative-store dedupe, then the `routing.py` package decomposition, then
shore up the thin test areas. Public CLI/JSON contract and catalog schema are
unchanged throughout; this is internal structure only.

## Goal And Objectives

Goal: make `even` reuse-ready as a library for private workspaces without
changing its public contract.

Objectives:

- Single catalog connection helper with `sqlite3.Row`, eliminating positional
  row access at consumed call sites.
- One representative-store abstraction parameterized by backend.
- `routing.py` decomposed into a navigable sub-package.
- Dead fallback parsers removed.
- Test coverage broadened beyond routing.

## Scope And Non-Goals

In scope:

- Internal refactor of `src/even/` modules and their tests.
- Removal of provably unreachable code paths.

Non-goals:

- No change to the public CLI surface, JSON/JSONL output shapes, result-file
  layout, or `catalog.yaml` schema.
- No new features (no new commands, no Layer 4/5 runtime).
- No git operations — maintainer owns staging and commits (WORKFLOW.md).

## Open Points

| ID | Question | Status | Resolution |
| --- | --- | --- | --- |
| OP-001 | Should the catalog helper be a context manager (`catalog_connection()`) or a thin module-level façade with query helpers? | Open | — |
| OP-002 | Does any supported install path actually run without PyYAML, or are all fallback parsers safe to delete outright? | Open | Lean: delete; PyYAML is a base dep. Confirm before removal. |
| OP-003 | Package layout for the routing split — submodule names and what stays in a top-level `routing/__init__.py` facade so `from even.routing import index_routing, search_text_with_routing, list_representatives` keeps working for `cli.py`/`fts.py`. | Open | — |
| OP-004 | Convert all 33 connect sites to the helper, or only the read sites that use positional access (lowest-risk subset first)? | Open | — |

## Implementation Phases

0. **Hermetic test fixture (Finding 7).** Add an autouse fixture (conftest) that
   `monkeypatch.delenv`s `EVEN_CACHE`/`EVEN_HOME` and isolates cwd, so the suite
   does not read the developer's real `~/.even` catalog. Do this first: every
   later phase relies on a trustworthy green suite to prove no behavior change.
1. **Catalog access layer (Findings 3+4).** Add a `catalog_connection()` (or
   chosen shape, OP-001) that opens the catalog with `row_factory =
   sqlite3.Row`. Migrate call sites incrementally, converting `row[i]` to keyed
   access. Start with `chunks.py` (worst offender) to validate the pattern.
   *Done: `db.py` helper added; `chunks.py` migrated.*
2. **Delete dead fallback parsers (Finding 5).** After confirming OP-002,
   remove `_load_*_fallback` from `config.py` and `catalog.py` and their
   branches.
3. **Representative-store dedupe (Finding 2).** Extract a backend-parameterized
   representative store (build/manifest-watermark/write/search) and reduce the
   three FTS/semantic/siglip families to one.
4. **`routing.py` decomposition (Finding 1).** Split into a `routing/`
   sub-package (e.g. `summaries`, `representatives`, `search`, `budget`,
   `importance`) behind a stable `__init__` facade. Pure mechanical moves; no
   behavior change.
5. **Minor consolidation.** Fold routing's text generation into `ollama.py` as
   a shared `generate_text`.
6. **Test broadening (Finding 6).** Add direct tests for parse, inventory,
   semantic, and the new catalog helper; keep the routing suite green.

## Dependencies And Risks

- `routing.py` is imported by `cli.py` and `fts.py`; the `__init__` facade must
  preserve those import paths (OP-003).
- Risk: row-access migration is broad and easy to get subtly wrong — mitigate
  by phasing per module and leaning on the test suite after each module.
- Risk: representative-store dedupe touches the most conceptually dense code
  (the two-lane image model); land it only after the access layer makes the
  call sites readable.
- The existing `test_routing.py` (1,039 lines) is the safety net for Phases 3–4.

## Exit Criteria

- No module over ~800 lines; `routing.py` is a package.
- One representative-store abstraction; no FTS/semantic/siglip triplication.
- Zero positional `row[i]` access at migrated call sites; `sqlite3.Row` in use
  via the shared helper.
- Fallback YAML parsers removed; `uv run pytest` green; Ruff clean.
- Public CLI/JSON/schema contract byte-identical (proven in `test.md`).
