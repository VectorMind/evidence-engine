# Evidence Engine

Reusable local evidence engine for document and generic media workflows.

Evidence Engine owns the public mechanics for source inventory, document
parsing, generated artifacts, SQLite catalog state, text search, semantic
search, hybrid search, command result files, and provenance-rich evidence
references. Private workspaces consume this open local data; they do not
reimplement lower extraction or search internals.

The name reflects the layering: a *corpus* of mixed local files, turned into
provenance-backed *evidence*, exposed as a lower *stack* layer that private
knowledge workspaces build on top of. The installable package and console
script remain `even` (see [Install Shape](#install-shape)).

## Layered Architecture

The system is a five-layer stack. A *layer* is a band; it can hold several
boxes. Each layer only describes what the layer below produced — meaning is
added on the way up, never assumed at the bottom:

```text
5  Curated knowledge     [ markdown notes · conventions · handoff slices ]   ▲ meaning
4  Reviewed facts        [ entities · classifications · links · decisions ]  │
3  Search projections    [ text (FTS) · semantic (vector) · hybrid · routing ]
2  Evidence              [ inventory · parsed objects · OCR/captions/summaries ]
1  Source authority      [ folders · OneDrive · archives · connectors ]      ▼ evidence
```

`even` **produces layers 2–3** from the layer-1 sources. **Layers 4–5 are
written by workspaces on top** (`private-documents`, `private-media`). There are
**no access boundaries**: every layer is open data the layer above reads
directly, plus one search API. The dependency direction is one-way — upper
layers know lower ones, never the reverse.

| # | Layer | Boxes inside | Catalog tables | Built by |
| --- | --- | --- | --- | --- |
| 1 | **Source authority** | Original files/connectors, read-only. Paths are private; only schemas are public. | `source_roots` | `sources scan` |
| 2 | **Evidence** | Everything machine-produced and **rebuildable**: source inventory, parsed typed objects (documents, pages, tables, figures, images, blobs), and generated observations (OCR text, captions, shallow descriptions). *Never proof of absence.* | `source_items`, `source_root_stats`, `source_extension_stats`, `documents`, `docling_artifacts`, `artifact_blobs`, `document_objects`, `valuable_items` | `docs parse` |
| 3 | **Search projections** | Fast rebuildable retrieval indexes: text (FTS), semantic (vector), hybrid fusion, and global routing. | `index_scopes`, `summary_nodes`, `fts_indexes`, `semantic_stores` | `index scope`, `index routing`, `search` |
| 4 | **Reviewed facts** | Meaning a human or agent **decided**: entities, classifications, identities, relationships, promotion choices. Durable; carries judgment. | *(upper catalog)* | workspaces on top |
| 5 | **Curated knowledge** | Human-readable Markdown: conventions, decisions, selected facts, topic handoff slices. | *(markdown)* | workspaces on top |

The two middle layers carry the load, so their scope is explicit:

- **Layer 2 — Evidence** is *rebuildable from sources + config + hashes*. No
  human judgment lives here; it can always be regenerated.
- **Layer 4 — Reviewed facts** is *decided and durable*. It is not regenerable
  and must never be overwritten by a re-parse.

The **SQLite catalog** is the current-state spine of layers 1–3. Layers stitch
together through plain catalog references — `corpus_cache.<table>.<row_id>`,
the same `ref:` convention the catalog uses for its own foreign keys — so an
upper row or a search hit points at exact evidence **without copying it**. See
the [Reference Contract](./specifications/corpus-cache-cli/spec.md#reference-contract).

Search is the one surface accessed through the CLI/API rather than direct reads,
because the physical text/vector internals stay hidden behind `text`,
`semantic`, and `hybrid`.

> The five bands are a mental model, not the precise data flow — indexing in
> particular touches several layers. They pack the real complexity into
> something a mind can stack.

## The Evidence Layer — the Novel Core

Most local search tools flatten a corpus into one index and lose the path back
to the original bytes. Evidence Engine keeps that path. **Layer 2 is the
engine's center of gravity:** a *typed, provenance-backed* evidence layer where
every machine-produced observation is

- **typed, not flattened** — a clause, a table cell, an OCR line, and a caption
  stay distinct objects with reading order, page span, and bbox, instead of
  being dissolved into anonymous text chunks;
- **rebuildable and hash-pinned** — each row carries its source `sha256`, so it
  can always be regenerated from Layer 1 and never drifts from the bytes it
  describes;
- **never proof of absence** — a missing observation means "not yet extracted,"
  not "does not exist";
- **referenced, not copied** — everything above points *into* this layer by
  `ref: corpus_cache.table.row_id`, so meaning accrues without duplicating
  evidence.

The diagram below shows Layer 2 in detail and how it hangs off the read-only
Layer 1 inventory. Documents and media are two parallel evidence branches that
share the same blob store and the same freshness contract.

```mermaid
flowchart TB
  subgraph L1["Layer 1 · Source authority (read-only)"]
    SRC["folders · OneDrive · archives · connectors"]
    ITEMS["source_roots → source_items<br/>path · size · sha256 · status"]
  end

  subgraph L2["Layer 2 · Evidence (rebuildable · hash-pinned)"]
    subgraph DOCS["Document evidence"]
      DOC["documents"]
      OBJ["document_objects<br/>pages · tables · figures · captions"]
      VAL["valuable_items"]
      ART["docling_artifacts → artifact_blobs"]
    end
    subgraph MEDIA["Media evidence"]
      ASSET["media_assets"]
      META["image / video / model3d metadata"]
      OBS["media_observations<br/>OCR · captions · kinds · tags"]
    end
  end

  SRC --> ITEMS
  ITEMS -->|"docs parse"| DOC
  DOC --> ART
  DOC --> OBJ --> VAL
  ITEMS -->|"media inspect / describe"| ASSET
  ASSET --> META
  ASSET --> OBS

  ITEMS -. "sha256 freshness" .-> DOC
  ITEMS -. "sha256 freshness" .-> ASSET
```

## Binding Reviewed Facts to Evidence

The payoff of a typed evidence layer is what Layer 4 can do with it. A single
**reviewed fact** — an entity, identity, or decision — can gather *many kinds of
evidence under one identity*. It reaches that evidence two ways:

- **discovery** — find candidate evidence by words (FTS), by meaning (semantic /
  hybrid), or by narrowing to the right root scope first (routing);
- **binding** — pin the accepted hits by `ref:` directly to the underlying
  evidence rows, with no copy, so the entity keeps an exact, regenerable trail.

So one entity can simultaneously hold an OCR line read off a scanned image, a
clause inside a parsed contract, a row in a spreadsheet table, and a geotagged
site photo — heterogeneous evidence types, one identity, every link
provenance-checkable.

```mermaid
flowchart TB
  ENT["Layer 4 · Entity: 'Acme Corp'<br/>(decided · durable)"]

  subgraph L3["Layer 3 · Search projections (disposable views)"]
    FTS["text (FTS)"]
    SEM["semantic / hybrid"]
    ROUTE["routing map"]
  end

  subgraph L2["Layer 2 · Evidence points (typed · provenance-rich)"]
    OCR["OCR text on scan.jpg<br/>media_observations"]
    CLAUSE["renewal clause in contract.pdf<br/>valuable_items"]
    TABLE["vendor row in sheet.xlsx<br/>document_objects (table)"]
    PHOTO["geotagged site photo<br/>image_metadata"]
  end

  ENT -->|"discover by words / meaning"| FTS
  ENT --> SEM
  ENT -->|"narrow to root scope"| ROUTE
  FTS --> OCR
  SEM --> CLAUSE
  SEM --> TABLE
  ROUTE --> PHOTO

  ENT -. "ref: corpus_cache.table.row_id — no copy" .-> OCR
  ENT -. ref .-> CLAUSE
  ENT -. ref .-> TABLE
  ENT -. ref .-> PHOTO
```

Layer 5 (curated Markdown) sits one step further out and belongs mostly to
workspaces that consume `even`; it is intentionally kept low-profile here.

## How Images Travel Two Lanes

A single image asset feeds **two independent retrieval lanes**, and the reason is
a structural asymmetry between text and images:

- **Text proof is verbatim.** Exact-term matching cannot survive compression, so
  the global text layer must be a *separate lossy artifact* (summaries) and a
  query is **routed** to the exhaustive per-root FTS. Two genuinely different
  objects: a summary versus a chunk.
- **An image embedding is already the representation.** There is no verbatim image
  layer beneath it, and an ANN index scales sub-linearly over the whole corpus, so
  image recall is served by **one central index directly, with no routing**.

That is why the two lanes look different:

- **Vector lane (visual similarity).** Each image is embedded with SigLIP into its
  per-root image store (every vector, exhaustive proof). `search image` queries the
  *logical union* of those stores directly — no router. A small set of **medoids**
  (cluster leads) is also drawn from those same vectors into a global representative
  store; medoids are the album's **visual fingerprint in the router**, not a
  substitute for the union.
- **Summary lane (hierarchical text).** The image's deterministic text — filename,
  metadata, `media_kind`, caption — is summarized into an `album_summary` (which
  also feeds the `root_summary`). Its `routing_payload` is indexed into the global
  representative FTS/semantic **router**, which selects scopes that are then proven
  in the per-root FTS. This is how `search text` finds media: through summarized
  text, **once**, never through a second cross-modal vector route.

The two lanes meet at exactly one place: the **scope router**, and only for an
**entity / cross-modal probe** that carries both words and example images. There a
text fingerprint (summary) and a visual fingerprint (medoids) are fused by RRF to
rank scopes; plain `search text` stays FTS-first and plain `search image` stays on
the central union.

```mermaid
flowchart TB
  IMG["image asset<br/>(Layer 2 evidence)"]

  subgraph VEC["Vector lane · visual similarity (no router)"]
    SIG["SigLIP embedding"]
    ROOTV["per-root image store<br/>all vectors · exhaustive proof"]
    UNION["logical union<br/>query-time merge of root stores"]
    MEDOID["k medoids · cluster leads<br/>(budgeted)"]
    SIGREP["global SigLIP representative store<br/>medoids only · routing fingerprint"]
  end

  subgraph TXT["Summary lane · hierarchical text (routed)"]
    FACTS["filename · metadata<br/>media_kind · caption"]
    ALBUM["album_summary<br/>+ feeds root_summary"]
    PAYLOAD["routing_payload"]
    FTSREP["global representative<br/>FTS + semantic · router"]
    ROOTF["per-root FTS<br/>exhaustive proof"]
  end

  SIMG(["search image<br/>image → image"])
  STEXT(["search text<br/>text → text"])
  ROUTER{{"scope router · RRF"}}
  ENTITY["entity / cross-modal probe<br/>words + example images"]

  IMG --> SIG --> ROOTV --> UNION --> SIMG
  SIG --> MEDOID --> SIGREP
  IMG --> FACTS --> ALBUM --> PAYLOAD --> FTSREP
  FTSREP --> ROUTER --> ROOTF --> STEXT
  SIGREP -. "visual fingerprint" .-> ROUTER
  ENTITY ==> ROUTER
  ENTITY -. "example image" .-> UNION
```

The asymmetry in one line: **text is routed because its proof is verbatim and
large; images are central because the embedding *is* the proof, and medoids exist
only to give the router a visual signal for mixed entity queries.**

## Current Status

This repository is in beta/pre-development. There is no backward-compatibility
burden for the older `agents-docs` command or old generated catalogs. Generated
workspace state may be wiped and rebuilt while the public contract settles.

Implemented today:

- package and CLI entrypoint named `even`;
- workspace-local storage under `.cache/`;
- SQLite catalog create/status/wipe;
- media-aware source inventory through `sources scan` (documents, images, video, audio, 3D);
- Docling parsing through `docs parse`;
- deterministic image, video, and 3D (OBJ/STL) metadata through `media inspect`;
- visual search (image→image and text→image) via SigLIP 2 image embeddings;
- media captions/metadata indexed into text/semantic search so media is findable by words;
- text, semantic, and hybrid search/index plumbing;
- document root summaries, media album summaries, and fixed-path global
  representative FTS routing for `search text`;
- JSON-first command stdout;
- persisted result JSON, events, summaries, and optional HTML reports.

## Install Shape

The brand is **Evidence Engine**. The package name is
`even`; the console script is `even` (ev-idence en-gine).

`even` is an installable tool, not a file that each consuming workspace vendors.
When the command is available on `PATH`, it can be launched from any folder. The
Python code runs from the environment that installed it, while evidence catalogs,
indexes, results, and reports are resolved from `EVEN_CACHE` or the process
current working directory.

For development in this source checkout, you can use the repo as `EVEN_HOME`.
Keep the virtual environment and shared model downloads at the repo root, then
add `bin/` to `PATH`:

```powershell
$env:EVEN_HOME = "<this-checkout>"
$env:PATH = "$env:EVEN_HOME\bin;$env:PATH"
even health
```

For reuse from another workspace, install the package into a user/tool
environment or another virtual environment, make sure its `even` executable is
on `PATH`, then `cd` to the workspace that should own the generated state before
running commands.

Optional dependency groups are defined in [pyproject.toml](./pyproject.toml).
Plain `uv sync` installs the `laptop` stack by default.

| Extra | Purpose |
| --- | --- |
| `docling` | Docling parsing. |
| `fts` | Full-text search implementation. |
| `semantic` | Vector store, PyArrow, and NumPy. |
| `embeddings` | FastEmbed local embeddings. |
| `heavy-embeddings` | SentenceTransformers local embeddings. |
| `media` | Image/video/3D metadata, thumbnails, perceptual hashing. |
| `image-search` | SigLIP 2 image embeddings for visual search. |
| `laptop` | Full local CPU stack (docling + fts + semantic + embeddings + media). Installed by default `uv sync`. |
| `station` | `laptop` plus heavier models (SentenceTransformers). |
| `all` | Alias of `station`. |

## Interaction Model

The key split is **Even home** versus **evidence cache**:

```text
EVEN_HOME                       default: ~/.even
  .venv/                        one Even install + heavy Python deps
  bin/                          optional wrapper scripts
  models/                       shared model downloads
        |
        | even command reads/writes evidence cache
        v
EVEN_CACHE                      default: <cwd>/.cache
  .cache/
    catalog/catalog.sqlite
    blobs/
    fts/
    semantic/
    results/
    reports/

source folders passed to commands
  read original files
  never receive generated cache files
```

`EVEN_HOME` selects the shared runtime home. Models always live under
`EVEN_HOME/models`. `EVEN_CACHE` selects the current catalog/index/result cache.
A `.env` file in the current directory can set `EVEN_HOME` or `EVEN_CACHE`; that
value overrides the process environment for the command. When `EVEN_CACHE` is
unset, the current working directory is the cache selector:

```powershell
cd C:\work\case-a
even sources scan C:\docs\case-a
# writes C:\work\case-a\.cache\...

cd C:\work\case-b
even sources scan C:\docs\case-b
# writes C:\work\case-b\.cache\...
```

If you want one shared evidence universe, set `EVEN_CACHE` explicitly, for
example to `~/.even/cache`. Then every command using that environment writes to
the same catalog and root-scoped indexes.

## Environment Variables

Even reads only these path environment variables:

| Variable | Default | Purpose | `.env` override |
| --- | --- | --- | --- |
| `EVEN_HOME` | `~/.even` | Shared Even home for the installed runtime, wrapper scripts, and model downloads. | yes |
| `EVEN_CACHE` | `<cwd>/.cache` | Evidence cache for the current catalog, blobs, indexes, results, reports, and calibration. | yes |

Resolution order is:

1. Current directory `.env`.
2. Process environment.
3. Built-in default.

Model paths are not separately configurable. FastEmbed downloads go to
`<EVEN_HOME>/models/fastembed/`; SigLIP downloads go to
`<EVEN_HOME>/models/siglip/`.

Example `.env`:

```env
EVEN_HOME=C:\tools\even
EVEN_CACHE=%USERPROFILE%\.even\cache
```

## Workspace Storage

Generated evidence data is written under `EVEN_CACHE`:

```text
<EVEN_CACHE>/
  catalog/catalog.sqlite
  blobs/
  fts/
  semantic/
  results/
  reports/
```

When `EVEN_CACHE` is unset, it defaults to `.cache/` under the caller's
current directory. The engine does not write generated files into the scanned
source folder. The scanner also excludes `.cache/` by default, so a local cache
is not inventoried as source input when scanning the workspace itself.

Runtime model files controlled by this code are stored under `EVEN_HOME/models`,
including FastEmbed and SigLIP model downloads. Third-party runtimes may still
keep their own external caches, but Evidence Engine's catalog, result, report,
FTS, semantic, and blob storage live under `EVEN_CACHE`.

This avoids one shared home-cache result/report tree. Real generated data is
private even when the code and schema files are public.

There is no V1 migration contract for old beta catalogs. Use
`even catalog wipe` and rebuild when the schema changes during
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
| `sources` | `scan <path>` | `path` | Inventory a mixed-content folder tree (documents, images, video, audio, 3D models). |
| `docs` | `parse <path>` | `path` | Auto-scan and parse documents through Docling. |
| `media` | `inspect <path>` | `path` | Extract image metadata (size, EXIF, GPS) and thumbnails into the catalog. |
| `media` | `describe <path>` | `path` | Shallow VLM captions (and optional `--kind`) via a local Ollama model. Opt-in, read-only. |
| `media` | `dedupe <path>` | `path` | Near-duplicate image candidate pairs via perceptual hashing (no model). |
| `index` | `scope <path>` | `path` | Build or refresh the text index for a source scope. |
| `index` | `scope <path> --semantic` | `path` | Build or refresh the semantic index for a source scope. |
| `index` | `scope <path> --image` | `path` | Build or refresh the image-embedding store for media images (needs `image-search` extra). |
| `index` | `routing <path>` | `path` | Build or refresh document/media summaries and the global representative FTS map. |
| `search` | `text <query>` | `query` | Search current text indexes. `--budget low\|mid\|high` tunes fanout; `--image PATH` (repeatable) adds a SigLIP visual route and returns image hits from the routed scopes (cross-modal probe). |
| `search` | `semantic <query>` | `query` | Search current semantic indexes. |
| `search` | `hybrid <query>` | `query` | Search text and semantic indexes with RRF fusion. |
| `search` | `image <image-path>` | `image-path` | Visual search: image→image (or `--text` for text→image) over image embeddings. |

Minimal examples:

```powershell
even catalog create
even catalog status
even health
even sources scan "C:\docs\example-folder"
even docs parse "C:\docs\example-folder"
even media inspect "C:\docs\example-folder"
even index scope "C:\docs\example-folder"
even index scope "C:\docs\example-folder" --semantic
even index routing "C:\docs\example-folder"
even search text "contract renewal clause"
even search semantic "contract renewal clause"
even search hybrid "contract renewal clause"
```

`sources scan` accepts optional safeguard overrides when a caller needs to
exceed configured defaults: `--max-files`, `--max-bytes`, and `--max-depth`.
Add `--report` for an HTML inventory report.

`docs parse` auto-runs the catalog and source-scan prerequisites. It defaults
to `docling_ocr`; use `--profile docling_fast_text` for a faster non-OCR run.
Parse failures are classified into actionable categories and included in
result JSON, Markdown summaries, and optional HTML reports.

`media inspect` auto-scans, then extracts deterministic metadata into typed
catalog tables, dispatched by media class: images (dimensions, color mode, EXIF
camera/orientation/GPS, capture time, plus a thumbnail through the shared blob
store), video (container, codecs, resolution, duration, frame rate, bit rate),
and 3D models (vertex/face counts and bounding box for OBJ and STL). It runs no
model. The model-based `describe`/`dedupe` commands follow in later slices.

`index scope` builds the text index from current parsed document objects **and
media text** (captions, media-kind, and filenames), so media shows up in
`search text`, `semantic`, and `hybrid` alongside documents. It auto-scans the
source path but does not silently parse/OCR missing documents. Run `docs parse`
and/or `media inspect`/`describe` first. Add `--semantic` for the semantic
index or `--image` for the image-embedding store.

`index routing` builds lossy document root summaries and media album summaries
into `summary_nodes`, then projects current summaries into a fixed global
representative FTS map. Media summaries use existing filenames, media metadata,
and caption/kind observations; they do not add OCR, transcripts, keyframes, or
object detection. Summary generation uses a local Ollama endpoint and is
explicit so ordinary `index scope` stays model-free. The global map is a routing
hint only; evidence still comes from root-scoped FTS hits.

`search text`, `search semantic`, and `search hybrid` are the public search
surface. Higher layers should not know which physical search engine backs
those projections. When a current global representative map exists,
`search text` routes to likely root scopes first and falls back to all current
FTS indexes when routing is unavailable or weak. Passing `--image PATH` turns
`search text` into an explicit cross-modal probe: the example images are embedded
with SigLIP, their visual route is fused with the text routes to choose scopes, and
image hits from those scopes come back alongside the text hits — the engine-side
tool for higher-level agentic queries that carry both words and pictures.

## Public Data Contract

The public contract is open local data plus search access:

| Surface | Purpose |
| --- | --- |
| [catalog.yaml](./catalog.yaml) | Current-state SQLite schema. |
| `.cache/catalog/catalog.sqlite` | Readable local catalog database. |
| [store_templates.yaml](./store_templates.yaml) | Generated text/semantic row templates. |
| [config/exposures.yaml](./config/exposures.yaml) | Workspace storage layout. |
| [config/parser.yaml](./config/parser.yaml) | Parser, traversal, indexing, and safeguard defaults. |
| [config/embeddings.yaml](./config/embeddings.yaml) | Embedding profile config. |
| [config/routing.yaml](./config/routing.yaml) | Global representative routing defaults. |
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
