# Closed Plans

Completed plan packets. Work is implemented and proven (or, for planning-only
packets, the decisions are settled). See each folder for details.

| Plan | Date | Summary | Proof / Notes |
| --- | --- | --- | --- |
| [2026-06-04-docling-search-index](2026-06-04-docling-search-index/) | 2026-06-04 | Corpus-cache CLI: fixed home cache, SQLite catalog, scan, Docling parse, Tantivy FTS, LanceDB semantic, hybrid RRF search. | Phases 0-7 implemented with runtime proof in [test.md](2026-06-04-docling-search-index/test.md). Residual follow-ups below. |
| [2026-06-06-parse-memory-failures](2026-06-06-parse-memory-failures/) | 2026-06-06 | Docling runtime defaults, failure classification, parse failure/partial reporting in summary + HTML, parse progress/quiet logging. | `uv run pytest` 4 passed; Ruff clean; parse report verified in [test.md](2026-06-06-parse-memory-failures/test.md). |
| [2026-06-07-knowledge-layers](2026-06-07-knowledge-layers/) | 2026-06-07 | Evidence/memory knowledge-layer consolidation. | Completed. |
| [2026-06-11-repo-consolidation](2026-06-11-repo-consolidation/) | 2026-06-11 | Planning-only closure: `even` is private-knowledge-friendly but private-repo-blind; curated private Markdown/YAML lives in private Git. | No code changes. Boundary decisions and doc-only proof recorded in [implementation.md](2026-06-11-repo-consolidation/implementation.md) and [test.md](2026-06-11-repo-consolidation/test.md). |
| [2026-06-27-engine-maturation-refactor](2026-06-27-engine-maturation-refactor/) | 2026-06-27 | Engine review follow-up. Findings 2–5, 7 closed: hermetic test fixture; shared `db.catalog_connection` + `sqlite3.Row` across all 9 modules; dead YAML fallback parsers removed (−358 LOC); representative manifest layer unified (6 helpers → 2); ollama text-gen consolidated; tests broadened. | `uv run pytest` 67 passed; Ruff clean; no public CLI/JSON/schema change. Finding 1 (`routing.py` split) handed off to [2026-06-27-routing-decomposition](2026-06-27-routing-decomposition/). |

## Residual follow-ups (not blocking closure)

From `2026-06-04-docling-search-index` "Future Proof Targets" - nice-to-have,
not yet proven:

- index health, rebuild, refresh, and deletion commands;
- manager-repository handoff export with a synthetic source manifest;
- expected-vs-actual search-hit fixtures for a small public corpus.

From `2026-06-11-repo-consolidation`:

- open a separate generic export-contract packet if current `even` JSON/JSONL
  command output is not enough for private Markdown/YAML curation workflows;
- scaffold the private knowledge repository outside `evidence-engine`;
- archive old private repositories only after confirming they remain private.
