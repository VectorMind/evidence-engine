# Survey: Global Routing Indexes

Date: 2026-06-06
Status: Local inventory and critique complete.

## Inputs Reviewed

- `plans/2026-06/06-global-routing-indexes/handing-in.md`
- `README.md`
- `WORKFLOW.md`
- `specifications/corpus-cache-cli/spec.md`
- `catalog.yaml`
- `config/exposures.yaml`
- `config/parser.yaml`
- `store_templates.yaml`
- `src/agents_cli/cli.py`
- `src/agents_cli/catalog.py`
- `src/agents_cli/inventory.py`
- `src/agents_cli/results.py`
- `src/agents_cli/paths.py`

## Current Repository State

`agents-cli` is a Python package exposing the `agents-docs` CLI. Its purpose is
to own reusable local document corpus-cache internals for manager repositories:
inventory, Docling parsing orchestration, SQLite catalog control, Tantivy FTS
indexes, LanceDB semantic stores, refresh behavior, health checks, and
structured command reports.

The current implementation is still early:

- fixed cache root and catalog path are implemented;
- catalog create, migrate, status, and health commands exist;
- `scan folder` inventories a folder tree into `source_roots`,
  `source_items`, and a root `index_scopes` row;
- `.results/` and optional HTML report generation exist for scan output;
- `parse folder`, `index folder`, and `search text` are reserved but not
  implemented;
- `catalog.yaml` is current-state catalog only;
- generated chunks are intentionally not SQLite tables;
- lower Tantivy and LanceDB row shapes live in `store_templates.yaml`;
- V1 semantic store policy is currently `one_per_root`.

The worktree already contains unrelated modified files outside this plan
packet. This survey does not treat them as part of this planning change.

## Hand-In Fit Assessment

The hand-in has a strong high-level principle:

```text
Summaries route.
Samples support.
Deep indexes prove.
SQLite remembers everything.
```

That principle fits the repository if "SQLite remembers everything" means
durable current metadata, summary nodes, registry pointers, and enough
provenance to rebuild or audit routing. It does not fit if it means SQLite
should store every chunk, every search row, every command log, or backend
internal data. Current contracts explicitly reject those.

The following ideas fit cleanly:

- root-scoped lower indexes as the evidence layer;
- global representative indexes as a cheap routing layer;
- lossy summaries used only for routing, never proof of absence;
- widening search when routing confidence is weak;
- source roots as caller-approved privacy and ownership boundaries;
- index scopes as replaceable physical performance units;
- generated and dependency-heavy folders excluded or represented negatively;
- archives planned by manifest before full unpacking;
- materialized collection indexes only after repeated broad query need.

The following ideas need adjustment before they fit:

- The proposed `summary_nodes` table is reasonable only as current-state
  representative metadata, not as a historical summary log.
- "SQLite stores chunks, tables, images/captions" conflicts with the current
  contract if read literally. SQLite stores normalized objects and valuable
  items; generated chunks belong inside Tantivy and LanceDB rows.
- Query usage tracking conflicts with the current no-command-log-in-SQLite
  rule unless it is narrowed to current aggregate counters or moved to
  `.results/`.
- Automatic root or scope splitting conflicts with the current V1
  `one_per_root` policy unless it is introduced as suggested planning output,
  not automatic mutation.
- Global representative indexes need explicit representation in existing
  registry tables. The current `index_scopes` shape is root-oriented, so a
  global or synthetic scope requires a schema decision.
- The hand-in implies answer generation and confidence logic, but this repo's
  public surface is currently a CLI that should first return structured search
  hits and hydrated evidence.

The following ideas are too broad for this work package:

- full query answer synthesis;
- mature materialized collection promotion;
- automatic multi-root policy;
- every proposed representative kind;
- vector global representatives before FTS routing exists;
- production ranking calibration across all source types.

## Recommended Planning Direction

Use this plan as a decision packet for routing architecture. The next accepted
implementation should be the smallest useful slice:

```text
SQLite current-state summary_nodes
global representative Tantivy FTS
root-scoped deep FTS search fanout
simple widening fallback
redaction-safe structured search output
```

LanceDB global representatives, query usage promotion, and collection indexes
should remain later phases unless the open design points are accepted.
