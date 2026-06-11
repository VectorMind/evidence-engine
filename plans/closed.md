# Closed Plans

Completed plan packets. Work is implemented and proven (or, for planning-only
packets, the decisions are settled). See each folder for details.

| Plan | Date | Summary | Proof / Notes |
| --- | --- | --- | --- |
| [2026-06-04-docling-search-index](2026-06-04-docling-search-index/) | 2026-06-04 | Corpus-cache CLI: fixed home cache, SQLite catalog, scan, Docling parse, Tantivy FTS, LanceDB semantic, hybrid RRF search. | Phases 0-7 implemented with runtime proof in [test.md](2026-06-04-docling-search-index/test.md). Residual follow-ups below. |
| [2026-06-06-parse-memory-failures](2026-06-06-parse-memory-failures/) | 2026-06-06 | Docling runtime defaults, failure classification, parse failure/partial reporting in summary + HTML, parse progress/quiet logging. | `uv run pytest` 4 passed; Ruff clean; parse report verified in [test.md](2026-06-06-parse-memory-failures/test.md). |
| [2026-06-07-knowledge-layers](2026-06-07-knowledge-layers/) | 2026-06-07 | Evidence/memory knowledge-layer consolidation. | Completed. |

## Residual follow-ups (not blocking closure)

From `2026-06-04-docling-search-index` "Future Proof Targets" — nice-to-have, not
yet proven:

- index health, rebuild, refresh, and deletion commands;
- manager-repository handoff export with a synthetic source manifest;
- expected-vs-actual search-hit fixtures for a small public corpus.
