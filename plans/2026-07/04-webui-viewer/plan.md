# Plan: Web UI Viewer

Date: 2026-07-04
Status: Approved — all design decisions locked 2026-07-04. Milestones 0–1 are
the implementable scope; Milestone 2+ is sequenced but deliberately not
designed yet.

Unblocked by: `plans/2026-07/04-entity-layer-runtime/` (closed 2026-07-04). The
catalog now carries the full contract this viewer renders, including the
generic entity tables.

## Problem Summary

Today the only human-facing surface over the evidence cache is scattered:
per-run `results/*/summary.md` and ad hoc `reports/*/report.html` files, one
per command invocation, with no cross-run or cross-table view. There is no way
to browse the catalog itself (sources, documents, media, index scopes,
entities) as a coherent, navigable whole, and no way to run or review search
interactively. This plan builds a single local SSR web viewer over the public
contract: `catalog.sqlite` (read-only), `results/`, `reports/`, and the
`even` CLI's JSON-stdout commands (search today; entity writes later).

## Precedent: `astro-huge-doc`

The maintainer's `C:\dev\MicroWebStacks\astro-huge-doc` is the explicit style
reference. What carries over:

- **Astro in `output: "server"` mode** with the `@astrojs/node` adapter
  (`mode: 'middleware'`), not the static-build mode — every page is SSR.
- **React islands** (`@astrojs/react`) for the interactive pieces, with
  **`@tanstack/react-table`** driving table UI.
- **`better-sqlite3`** for direct, synchronous, in-process SQLite reads from
  the Node server — no ORM, no query builder, just SQL.
- Its **layout shell and theme** — top app bar, left pages-tree menu, right
  outline ToC, `tokens.css`/`colors.css` design tokens, light/dark theme
  toggle — reused directly rather than redesigned (D4).

What does *not* carry over: astro-huge-doc's entire pipeline (markdown
collection, remark/mdast rendering, Shiki, diagrams, 3D model viewers, GitHub
OAuth, the VS Code extension packaging) is about rendering a tree of markdown
documents. This viewer has nothing to do with markdown; it renders directly
from `even`'s catalog rows and JSON command output into a fixed, known
layout. Only the SSR/React/table/SQLite-access/layout *pattern* is reused,
not the content model.

## Contract Recap (what exists to render)

- **`catalog.sqlite`** (read-only), per `catalog.yaml`, in four groups:
  - *Sources*: `source_roots`, `source_items`, `source_root_stats`,
    `source_extension_stats`.
  - *Evidence*: `documents`, `docling_artifacts`, `artifact_blobs`,
    `document_objects`, `valuable_items`, `media_assets`, `image_metadata`,
    `video_metadata`, `model3d_metadata`, `media_artifacts`,
    `media_observations`, `media_dedupe_candidates`.
  - *Indexes*: `index_scopes`, `summary_nodes`, `fts_indexes`,
    `semantic_stores`, `image_stores`.
  - *Entities (Layer 4)*: `entities`, `entity_aliases`,
    `entity_evidence_links`, `entity_classifications`, `entity_attributes`,
    `entity_relationships`, `review_tasks`.
- **`results/YYYY.MM/DD/<run>/`**: `result.json`, `summary.md`,
  `events.jsonl` per command run (see `even/results.py`).
- **`reports/...`**: optional pre-rendered HTML per CLI run.
- **The `even` CLI, JSON on stdout**: `search text|semantic|hybrid|image`,
  and `entity add|list|show|alias|link|review|find`. This is the only path to
  anything requiring Python-side logic (FTS5 query planning, sqlite-vec
  similarity, RRF fusion, rerank, the entity runtime's validation rules). Refs
  from any of these resolve via `even.references.resolve_ref`, which is
  already generic across every table.

## Locked Decisions (2026-07-04)

### D1. Data-access architecture — Node-only, direct SQLite + CLI shell-out

The Astro/Node server reads `catalog.sqlite` directly via `better-sqlite3`
(read-only) for every straight catalog page — overview counts,
source/document/media/entity tables, evidence detail pages. For anything
needing Python-only logic — search today, entity writes later — the server
spawns `even <command> --json` as a subprocess and parses stdout. No
standalone Python HTTP service. Rejected: a Python backend service
(FastAPI/Starlette) fronting a thin Node client, and a Python-only SSR stack
with no Node/Astro/React at all.

**Why:** matches the working precedent exactly (astro-huge-doc already reads
a `better-sqlite3` database directly from Node). Zero new API surface to
design or keep in sync — `catalog.yaml` and the CLI's already-tested
JSON-stdout contract *are* the contract. Keeps the entity write path
singular, per the standing rule that review actions must never open a second
write path.

### D2. Search/entity-call latency

For the current phase (passive/read-only rendering, no interactive search UI
yet): subprocess-per-request via the `even` CLI is fine as-is; no persistent
Python process while there is no search page.

Forward commitment for when the Search milestone starts: a long-lived Python
process that keeps embedding models warm **is** required — no way around the
reload cost for `search semantic`/`search hybrid`/the image cross-modal probe
once search becomes interactive, and no duplication of embeddings or models
into Node. Explicitly **rejected**: a separate "embedding server" — it would
duplicate search logic between the CLI and Node. Any long-lived process must
reuse the exact same `even.fts`/`even.semantic`/`even.hybrid` functions the
CLI already calls. One search implementation (Python, in `even`), reached two
ways — never two implementations.

Deferred until the Search milestone: the sidecar's exact transport
(stdin/stdout JSON-RPC vs. loopback-only HTTP) and lifecycle.

### D3. Where the viewer lives and how it's launched

The Node/Astro project lives at **`src/web`** — nested under `src/`,
alongside `src/even`. `even serve` is a real CLI subcommand **from the
start**: it execs the Node process (initially the Astro dev server; later a
built server) so the whole viewer is reachable through the same `even`
entrypoint users already know — Node/`pnpm` stay an implementation detail
abstracted behind the CLI. Same shell-out shape D1 already establishes in the
other direction.

Implementation details (dev vs. built exec target, PATH requirements) settle
during Milestone 0.

### D4. Navigation, layout, and theme

Reuse astro-huge-doc's visual theme and layout components — app bar, left
pages-tree menu, right outline ToC, design tokens, theme toggle — directly.
The app bar holds the top-level sections (Overview, Sources, Evidence, Media,
Indexes, Entities, Search, Runs — v1 subset per Milestones).

Absent-content behavior, locked:

- **Left pages-tree menu:** omitted entirely — no reserved space — when the
  current app-bar section has no subpages; a single-page section shows its
  one page full width under the app bar.
- **Right outline ToC:** always present as a layout region for consistent
  chrome. Default state closed. When a page has sections, the toggle opens it
  normally. When a page has no sections, it stays closed and **disabled** —
  the open control is inert.

### D5. Table pagination contract — server-driven, data fully independent

Server-driven pagination from the start. Nothing is baked at build time: all
data reads happen at request time, so a data update never requires a website
rebuild — the site build and the data are fully independent. The initial page
render is request-time SSR; the mounted TanStack React Table island runs in
**manual pagination / manual sorting / manual filtering** mode: page-change,
sort-change, and filter-change trigger a fetch to an Astro server endpoint
that runs the equivalent `LIMIT`/`OFFSET`/`ORDER BY`/`WHERE` against
`catalog.sqlite` via `better-sqlite3` and returns one page of rows as JSON.
The client never holds the full table.

Page size: default **25**, selectable **50**, hard max **100**. Paging is
offset/limit (matches SQL directly; revisit per-table only if a row count
ever makes offset scanning slow).

### D6. Milestone scope

Milestones 0–1 approved as the implementable scope; Milestone 2+ is a rough
sequence to refine once 0–1 land.

## Resolved Items (2026-07-04, previously "lower priority")

- **`results/` and `reports/` stay.** They are one-shot records of each CLI
  invocation — unit-testing artifacts of the command that ran. They are
  generated only by the CLI layer (the `CommandRun` wrapper in `cli.py`),
  never from the internal Python functions themselves, so a long-lived
  service reusing those same functions (D2's future sidecar) produces no
  result spam and the functions stay reusable as-is. The viewer renders them;
  it does not replace them.
- **Auth is out of scope.** Local-first, single-user machine. Remote access
  is solved outside the viewer (VPN, or a separate auth layer in front of
  it). No multi-tenancy; the catalog is not auth- or user-aware and will not
  become so.
- **Live run monitoring comes later.** `events.jsonl` stays the mechanism;
  the viewer does not tail it in this plan.
- **Entity merge/dedupe UI: out of scope for this plan** (no runtime support
  exists yet either).

## Already Settled (from the direction memo, restated for the record)

- Fully SSR, no static-build mode; no use case identified for static output.
- Read-only, contract-only viewer: no ad hoc catalog writes, no querying/
  engine logic beyond what the CLI's public commands already provide.
- No control pane: the viewer never launches scan/parse/index/routing runs.
- Entity review actions (accept/reject/defer, bind link) come after the
  read-only viewer, writing through the same `even.entities` runtime API the
  CLI uses — no second write path, ever.

## Architecture

```text
src/web/                              # Node/Astro project, alongside src/even
  package.json                        # astro, @astrojs/node, @astrojs/react, react, @tanstack/react-table, better-sqlite3
  astro.config.mjs                    # output: "server", node adapter, react integration
  src/
    layout/                           # app bar + conditional left tree + collapsible right ToC (D4), tokens/colors from astro-huge-doc
    pages/
      index.astro                     # Overview (Milestone 0)
      sources/items.astro             # source_items paginated table (Milestone 1)
      api/
        source-items.json.ts          # manual-pagination endpoint (D5)
    components/
      table/                          # TanStack React Table island (manual mode)
    lib/
      catalog.ts                      # better-sqlite3 connection, read-only, resolves EVEN_CACHE
      even-cli.ts                     # subprocess wrapper for `even ...` JSON calls (Milestone 2+)
```

`src/even/cli.py` gains `even serve` (D3). No other change to `src/even/` is
required for Milestones 0–1.

## Milestones

0. **Skeleton + Overview.** `src/web` scaffolded; layout shell per D4 with
   the astro-huge-doc theme; `even serve` launches it; the Overview page
   reads `source_roots`/`source_root_stats`/`index_scopes` (and headline
   counts of documents, media assets, entities) live from `catalog.sqlite`
   read-only, proving the direct-read path against a real cache (fixture:
   a cache built from `tests/fixtures/entities-basic/`).
1. **First paginated table.** `source_items` table page proving D5
   end-to-end: TanStack manual mode, API endpoint with limit/offset/sort/
   filter, page sizes 25/50/100, client never holds more than one page.
2. **(Later, refine before starting)** Entities section (list + hydrated
   entity detail proving `resolve_ref` fan-out and the right ToC on a
   sectioned page); Search section (CLI shell-out first, then the D2
   warm-model sidecar designed for real); Runs section (`results/` browser);
   entity review write actions last.

## Exit Criteria (Milestones 0–1)

- `pnpm build` (and typecheck) clean in `src/web` from a clean checkout.
- `even serve` starts the viewer against the caller's `EVEN_CACHE` workspace.
- Overview page renders live counts matching direct SQL queries against the
  same catalog; the catalog file is opened read-only (no write lock, no WAL
  side effects on the cache).
- `source_items` page: requesting page 2 with a sort returns rows matching
  the equivalent `LIMIT/OFFSET/ORDER BY` query; response is capped at the
  requested page size (max 100); total row count reported for the pager.
- Changing catalog data and reloading shows the new data with **no rebuild**
  (D5's data-independence guarantee).
- Proof recorded in `test.md` against a cache built from
  `tests/fixtures/entities-basic/`.
