# documents-manager

Reusable local evidence engine for document and generic media workflows.

`documents-manager` owns the public mechanics for source inventory, document
parsing, generated artifacts, SQLite catalog state, text search, semantic
search, hybrid search, command result files, and provenance-rich evidence
references. Private workspaces consume this open local data; they do not
reimplement lower extraction or search internals.

## Current Status

This repository is in beta/pre-development. There is no backward-compatibility
burden for the older `agents-docs` command or old generated catalogs. Generated
workspace state may be wiped and rebuilt while the public contract settles.

Implemented today:

- package and CLI entrypoint named `documents-manager`;
- workspace-local storage under `.documents-manager/`;
- SQLite catalog create/status/wipe;
- folder source inventory through `sources scan`;
- Docling parsing through `docs parse`;
- text, semantic, and hybrid search/index plumbing;
- JSON-first command stdout;
- persisted result JSON, events, summaries, and optional HTML reports.

## Install Shape

The package name is `documents-manager`; the console script is
`documents-manager`.

Optional dependency groups are defined in [pyproject.toml](./pyproject.toml):

| Extra | Purpose |
| --- | --- |
| `docling` | Docling parsing. |
| `fts` | Full-text search implementation. |
| `semantic` | Vector store, PyArrow, and NumPy. |
| `embeddings` | FastEmbed local embeddings. |
| `heavy-embeddings` | SentenceTransformers local embeddings. |
| `all` | Practical full local stack. |

## Workspace Storage

Generated data is written under the caller workspace:

```text
.documents-manager/
  catalog/catalog.sqlite
  blobs/
  fts/
  semantic/
  models/fastembed/
  results/
  reports/
```

This avoids one shared home-cache result/report tree. Real generated data is
private even when the code and schema files are public.

There is no V1 migration contract for old beta catalogs. Use
`documents-manager catalog wipe` and rebuild when the schema changes during
this phase.

## CLI Surface

Commands return JSON on stdout. Commands that perform larger work also write
`result.json`, `events.jsonl`, and `summary.md` under the workspace
`results/` tree. `--report` writes optional HTML under `reports/`.

| Command | Subcommand | Mandatory args | Purpose |
| --- | --- | --- | --- |
| `catalog` | `create` | none | Create the workspace catalog if missing. |
| `catalog` | `status` | none | Report catalog presence, version, table state, and row counts. |
| `catalog` | `wipe` | none | Delete the workspace catalog database. |
| `health` | none | none | Check workspace paths and optional dependencies. |
| `sources` | `scan <path>` | `path` | Inventory a mixed-content folder tree. |
| `docs` | `parse <path>` | `path` | Auto-scan and parse documents through Docling. |
| `index` | `scope <path>` | `path` | Build or refresh the text index for a source scope. |
| `index` | `scope <path> --semantic` | `path` | Build or refresh the semantic index for a source scope. |
| `search` | `text <query>` | `query` | Search current text indexes. |
| `search` | `semantic <query>` | `query` | Search current semantic indexes. |
| `search` | `hybrid <query>` | `query` | Search text and semantic indexes with RRF fusion. |

Minimal examples:

```powershell
documents-manager catalog create
documents-manager catalog status
documents-manager health
documents-manager sources scan "C:\docs\example-folder"
documents-manager docs parse "C:\docs\example-folder"
documents-manager index scope "C:\docs\example-folder"
documents-manager index scope "C:\docs\example-folder" --semantic
documents-manager search text "contract renewal clause"
documents-manager search semantic "contract renewal clause"
documents-manager search hybrid "contract renewal clause"
```

`sources scan` accepts optional safeguard overrides when a caller needs to
exceed configured defaults: `--max-files`, `--max-bytes`, and `--max-depth`.
Add `--report` for an HTML inventory report.

`docs parse` auto-runs the catalog and source-scan prerequisites. It defaults
to `docling_ocr`; use `--profile docling_fast_text` for a faster non-OCR run.
Parse failures are classified into actionable categories and included in
result JSON, Markdown summaries, and optional HTML reports.

`index scope` builds the text index from current parsed document objects. It
auto-scans the source path but does not silently parse/OCR missing documents.
Run `docs parse` first when no parsed objects exist. Add `--semantic` to build
the semantic index.

`search text`, `search semantic`, and `search hybrid` are the public search
surface. Higher layers should not know which physical search engine backs
those projections.

## Public Data Contract

The public contract is open local data plus search access:

| Surface | Purpose |
| --- | --- |
| [catalog.yaml](./catalog.yaml) | Current-state SQLite schema. |
| `.documents-manager/catalog/catalog.sqlite` | Readable local catalog database. |
| [store_templates.yaml](./store_templates.yaml) | Generated text/semantic row templates. |
| [config/exposures.yaml](./config/exposures.yaml) | Workspace storage layout. |
| [config/parser.yaml](./config/parser.yaml) | Parser, traversal, indexing, and safeguard defaults. |
| [config/embeddings.yaml](./config/embeddings.yaml) | Embedding profile config. |
| `results/` | Run proof: JSON, JSONL events, and Markdown summaries. |
| `reports/` | Optional human HTML reports. |
| Search CLI | Hydrated text/semantic/hybrid retrieval without exposing projection internals. |

Private repositories may open the SQLite database read-only and query it
directly. Search is intentionally accessed through the CLI/API because text and
vector projection internals are implementation details.

## Layer Rule

Use this boundary everywhere:

```text
Lower schemas describe what was observed and generated.
Upper schemas describe what was believed, reviewed, promoted, or used.
```

`documents-manager` owns lower evidence. Private workspaces own reviewed
meaning.

## Public And Private Split

Public repo material:

- code;
- schemas;
- empty/synthetic config examples;
- migration/reset logic during development;
- synthetic fixtures;
- contract documentation.

Private or generated material:

- real source manifests and paths;
- generated SQLite catalogs;
- OCR text and parser artifacts;
- generated descriptions and thumbnails;
- text/vector indexes;
- embeddings;
- review decisions;
- private knowledge Markdown.

## Related Plans

- [Knowledge Layers Merge](./plans/2026-06-07-knowledge-layers/plan.md)
- [Global Routing Indexes](./plans/2026-06-06-global-routing-indexes/plan.md)
- [Corpus Cache CLI Specification](./specifications/corpus-cache-cli/spec.md)
