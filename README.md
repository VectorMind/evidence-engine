# corpus-evidence

Reusable local evidence engine for document and generic media workflows.

`corpus-evidence` owns the public mechanics for source inventory, document
parsing, generated artifacts, SQLite catalog state, text search, semantic
search, hybrid search, command result files, and provenance-rich evidence
references. Private workspaces consume this open local data; they do not
reimplement lower extraction or search internals.

The name reflects the layering: a *corpus* of mixed local files, turned into
provenance-backed *evidence*, exposed as a lower *stack* layer that private
knowledge workspaces build on top of. The installable package and console
script remain `coev` (see [Install Shape](#install-shape)).

## Layered Architecture

The system is a stack of knowledge layers. Each layer only describes what the
layer below produced; meaning is added on the way up, never assumed at the
bottom. The single rule that governs every boundary:

```text
Lower layers describe what was observed and generated.
Upper layers describe what was believed, reviewed, promoted, or used.
```

`corpus-evidence` owns the five lower **evidence** layers. Private
workspaces (`private-documents`, `private-media`) own the two upper **meaning**
layers. Dependencies are one-way: private layers may read public catalog/schema
contracts; the public engine never knows about private state.

| # | Layer | Owner | What it holds | Catalog tables | Command |
| --- | --- | --- | --- | --- | --- |
| 1 | **Source authority** | public | Original files and connectors, read-only. Paths/URIs are private data; only schemas are public. | `source_roots` | `sources scan` |
| 2 | **Source inventory** | public | Generic typed source items, hashes, sizes, per-root and per-extension stats. No personal meaning. | `source_items`, `source_root_stats`, `source_extension_stats` | `sources scan` |
| 3 | **Evidence objects** | public | Parsed typed objects: documents, pages, tables, figures, images, stored artifacts and blobs. | `documents`, `docling_artifacts`, `artifact_blobs`, `document_objects`, `valuable_items` | `docs parse` |
| 4 | **Generated observations** | public | Machine-produced material: OCR text, captions, shallow descriptions, summaries, duplicate candidates. Rebuildable; never proof of absence. | (carried on artifacts/objects) | `docs parse` *(media `describe` planned)* |
| 5 | **Search projections** | public | Fast rebuildable retrieval indexes: text (FTS), semantic (vector), hybrid fusion. Hydrate back to catalog refs. | `index_scopes`, `fts_indexes`, `semantic_stores` | `index scope`, `search` |
| 6 | **Reviewed semantic facts** | private | Durable reviewed meaning: entities, classifications, identities, relationships, promotion choices. | *(private overlay)* | *(private workspaces)* |
| 7 | **Curated knowledge & handoff** | private | Human-readable Markdown knowledge, conventions, decisions, and topic handoff slices. | *(private overlay)* | *(private workspaces)* |

The **SQLite catalog** is the current-state spine of layers 1–5. The stable
stitching primitive across all layers is:

```text
catalog row identity + evidence_ref + provenance
```

This lets a private row or a search hit point back to exact public evidence
without copying lower-layer data. Search is the one public surface accessed
through the CLI/API rather than direct reads, because the physical text/vector
projection internals are deliberately hidden behind `text`, `semantic`, and
`hybrid`.

For the full design rationale and the per-layer contract see the
[Knowledge Layers plan](./plans/2026-06-07-knowledge-layers/plan.md).

## Current Status

This repository is in beta/pre-development. There is no backward-compatibility
burden for the older `agents-docs` command or old generated catalogs. Generated
workspace state may be wiped and rebuilt while the public contract settles.

Implemented today:

- package and CLI entrypoint named `coev`;
- workspace-local storage under `.cache/coev/`;
- SQLite catalog create/status/wipe;
- folder source inventory through `sources scan`;
- Docling parsing through `docs parse`;
- text, semantic, and hybrid search/index plumbing;
- JSON-first command stdout;
- persisted result JSON, events, summaries, and optional HTML reports.

## Install Shape

The repository and brand are `corpus-evidence`. The package name is
`coev`; the console script is `coev`. Branding and the
CLI/package identity are intentionally separate.

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
.cache/coev/
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
`coev catalog wipe` and rebuild when the schema changes during
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
coev catalog create
coev catalog status
coev health
coev sources scan "C:\docs\example-folder"
coev docs parse "C:\docs\example-folder"
coev index scope "C:\docs\example-folder"
coev index scope "C:\docs\example-folder" --semantic
coev search text "contract renewal clause"
coev search semantic "contract renewal clause"
coev search hybrid "contract renewal clause"
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
| `.cache/coev/catalog/catalog.sqlite` | Readable local catalog database. |
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
