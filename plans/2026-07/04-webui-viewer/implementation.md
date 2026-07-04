# Implementation: Web UI Viewer

Progress: [######----] Milestones 0-1 done; Milestone 2+ (Entities, Search,
Runs, review actions) not started.

## What Was Built (Milestones 0-1, 2026-07-04)

### `src/web` — the Node/Astro viewer project (plan D3)

- `package.json` / `astro.config.mjs` / `tsconfig.json`: Astro 5 in
  `output: "server"` with `@astrojs/node`, `@astrojs/react`, TanStack React
  Table, and `better-sqlite3` — the same stack majors as astro-huge-doc.
  One deviation from the precedent: the node adapter runs in **standalone**
  mode, not `middleware`, so `node dist/server/entry.mjs` is directly
  runnable by `even serve` — astro-huge-doc's middleware mode exists to host
  its express auth layer, which this viewer doesn't have (auth is out of
  scope per the plan's resolved items). pnpm 10 requires
  `pnpm.onlyBuiltDependencies` to allow the `better-sqlite3`/`esbuild`
  native build scripts.
- `src/layout/`: the astro-huge-doc shell reused per plan D4 —
  `colors.css`, `tokens.css`, and `toc_menu_activation.js` copied verbatim;
  `Layout.astro`, `AppBar.astro`, `SideMenu.astro`, `SubMenu.astro`,
  `ThemeToggle.astro`, `menu_interactions_activation.js` copied with
  adaptations:
  - navigation comes from the fixed model in `src/lib/nav.ts` (app-bar
    sections + per-section page lists) instead of a markdown content tree;
  - left pages-tree region is omitted entirely when the current section has
    fewer than two pages (D4);
  - right ToC region is always rendered; when the page declares no sections
    the app-bar toggle carries `disabled`, the adapted
    `menu_interactions_activation.js` forces the nav closed and attaches no
    click handler, and the resize handle loses its `active` class (D4
    "closed by default, can't open");
  - `SideMenu`'s content-hash state key (which hashed the markdown workspace
    path) became a fixed `even-viewer:<category>` key;
  - `SubMenu` dropped the markdown table/diagram section indicator icons.
- `src/lib/catalog.ts`: read-only `better-sqlite3` connection to
  `<EVEN_CACHE>/catalog/catalog.sqlite` (plan D1). `readonly: true,
  fileMustExist: true` so the viewer can never hold a write lock. A missing
  catalog returns `null` (pages render an empty state) and is re-checked per
  request, so creating a catalog later needs no server restart.
- `src/lib/tables.ts`: the D5 table registry. One `TableSpec` per exposed
  table (columns, sortable set, LIKE-searchable columns, default sort);
  `parsePageQuery` clamps limit to 1..100 (default 25) and resolves
  sort/dir/q strictly against the whitelist, so no request string ever
  reaches SQL as an identifier. `queryPage` runs
  `SELECT ... LIMIT ? OFFSET ?` plus a `COUNT(*)` with the same WHERE.
  Registered so far: `source_items`, `source_roots`.
- `src/pages/api/table/[table].json.ts`: the manual-pagination endpoint —
  404 for unregistered tables, 503 while no catalog exists, else one page.
- `src/components/table/DataTable.tsx`: TanStack React Table island in
  fully manual mode (`manualPagination/manualSorting/manualFiltering`).
  Page 1 arrives as SSR props (no first-paint fetch); every page/sort/
  debounced-filter change fetches one page from the endpoint with an
  `AbortController` cancelling stale requests. Page sizes 25/50/100 per D5.
- Pages: `index.astro` (Overview — live headline counts for all four layer
  groups, per-root stats joined from `source_root_stats`, index scope list),
  `sources/items.astro` and `sources/roots.astro` (server-paginated tables;
  roots exists partly so the Sources section has two pages and the left
  tree region is exercised).

### `even serve` (plan D3)

- `src/even/serve.py`: resolves the workspace via the existing
  `even.paths.workspace_root()` (so `.env` handling matches every other
  command), passes it to the Node child as `EVEN_CACHE` with `HOST`/`PORT`,
  and runs the built server (`node dist/server/entry.mjs`) or, with `--dev`
  or when no build exists, the Astro dev server via pnpm. Prints one JSON
  status line (mode, url, workspace, web root) before handing the console to
  the child; clear JSON errors for missing web project / node / pnpm.
- `src/even/cli.py`: `even serve [--host] [--port] [--dev]` wired like every
  other subcommand. Deliberate deviation from the command contract: `serve`
  does **not** create a `results/` run record — result artifacts are one-shot
  records of completed CLI invocations, and a long-running server has no
  single completion to record (consistent with the plan's resolved item that
  results/reports stay CLI-generation-only).
- README: CLI table row + Current Status entry.

## Verified Behavior

See `test.md` for the full proof transcript. Highlights: all three pages
SSR 200 against a fixture cache; overview counts match direct SQL; the API
endpoint pages/sorts/filters correctly, clamps `limit=500` to 100, rejects
unknown tables with 404, and falls back to the default sort on a hostile
`sort` value; a CLI write to the catalog shows up on reload with no rebuild
while the built server keeps running (D5 data-independence); `pnpm build`
and `astro check` clean; full Python suite still passes.

## Post-Landing Fix (2026-07-04)

First real run against the maintainer's own `.cache` (schema v9, predating
the entity-runtime plan's 7 entity tables — not the fixture cache) 500'd:
the Overview page queried `entities`/`entity_aliases`/`entity_evidence_links`/
`review_tasks` unconditionally and `better-sqlite3` throws on `SELECT` against
a table the file doesn't have. The catalog's own contract is wipe-and-rebuild,
not migrate (README "Current Status"), so an older cache genuinely can lack
newer tables — a page must degrade for that, not crash. Fixed:

- `catalog.ts`: added `catalogTableNames()` (reads `sqlite_master` once) and
  changed `tableCount()` to return `null` for a table the catalog file
  doesn't have, instead of letting the `SELECT` throw.
- `index.astro`: renders `null` counts as `n/a` (`statValue()`), guards the
  `source_root_stats` join and `index_scopes` query behind presence checks,
  and shows a banner naming the missing tables with the exact recovery
  command (`even catalog wipe && even catalog create`) when any are absent.
- `tables.ts`: `queryPage()` now checks `catalogTableNames(db).has(spec.table)`
  before querying and returns `null` (same path as "no catalog yet") rather
  than throwing, so a stale catalog degrades a table page to "no data here
  yet" instead of a 500.

Verified against the maintainer's real `.cache` (17 source items, 16 media
assets, 1 index scope, schema v9): Overview now returns 200 with the warning
banner and `n/a` for the four missing counts; `/sources/items` unaffected
(those tables predate the schema split). `pnpm build`/`check` clean.

## Notes / Follow-Ups

- `astro check` reports 4 hints (unused event params) in the verbatim-copied
  `menu_interactions_activation.js` — left as-is to keep the reuse diffable
  against the precedent repo.
- The Overview left menu: the Overview section has no subpages, so it proves
  the omitted-left-region path; Sources proves the two-page tree; the
  disabled-ToC path is proven by the Sources table pages (no sections), and
  the enabled-ToC path by Overview's four sections.
- `even serve` requires a repository checkout (web project at `src/web`);
  packaging the built viewer into the wheel is out of scope until the
  viewer stabilizes.
- Milestone 2+ (Entities pages with `resolve_ref` hydration, Search via CLI
  shell-out, Runs browser, review actions) starts from the D6 sequence in
  `plan.md`; the D2 warm-model sidecar gets designed when the Search
  milestone opens.
