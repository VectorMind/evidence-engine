# Test Proof: Web UI Viewer (Milestones 0-1)

Status: Milestones 0-1 verified 2026-07-04. Milestone 2+ unproven (not built).

## Build And Typecheck

```powershell
pnpm --dir src/web install   # pnpm 10; native builds allowed via pnpm.onlyBuiltDependencies
pnpm --dir src/web build     # clean (server + client bundles)
pnpm --dir src/web check     # 0 errors, 0 warnings, 4 hints (verbatim-copied layout JS)
```

Python suite after the `even serve` CLI addition:

```powershell
uv run pytest -q
# 92 passed (no regressions)
```

## Fixture Cache

Built from the entity-runtime packet's reference example, in an isolated
scratch `EVEN_CACHE` (no `.env` collision):

```powershell
$env:EVEN_CACHE = "<scratch>/.cache"
even catalog create
even docs parse tests/fixtures/entities-basic --profile docling_fast_text   # ok, 1 parsed
even media inspect tests/fixtures/entities-basic                            # ok
even index scope tests/fixtures/entities-basic                              # ok
even entity add "Northwind Salvage" --kind organization ...                 # ent_...
even entity alias ent_... "N.W. Salvage" --kind abbreviation
even entity find ent_... "Northwind Salvage" --propose                      # 2 links + 2 tasks
```

Resulting ground truth (direct sqlite3 queries): `source_items` 3,
`documents` 1, `media_assets` 1, `entities` 1, `entity_aliases` 1,
`entity_evidence_links` 2, `review_tasks` 2, `index_scopes` 1.

## Milestone 0 — Overview Page, Direct Read-Only SQLite

Server started as the built bundle (`node dist/server/entry.mjs`) with
`EVEN_CACHE` pointing at the fixture cache.

- `GET /` → 200. SSR'd stat values matched the ground truth above exactly
  (all 16 headline counts, including the zero counts for tables the fixture
  does not populate).
- The workspace line renders the resolved `EVEN_CACHE` path and the catalog
  is opened with `readonly: true` (no write lock, no WAL files created in
  the cache).

## Milestone 1 — Server-Driven Pagination (D5)

- `GET /sources/items` → 200 with page 1 SSR'd into the HTML (fixture rows
  visible in the response body without any client fetch).
- `GET /api/table/source_items.json?limit=2&offset=1&sort=size_bytes&dir=desc`
  → exactly 2 rows, in correct descending-size order from offset 1, with
  `total: 3` for the pager.
- `limit=500` → clamped to `limit: 100` (hard max).
- `q=northwind` → `total: 2`, only the two matching fixture files.
- Unknown table (`/api/table/nope.json`) → 404 `unknown_table`.
- Hostile sort value (`sort=;drop`) → falls back to the whitelisted default
  (`relative_path`); identifiers never come from the request.

## D5 Data Independence — No Rebuild On Data Change

With the built server still running (no rebuild, no restart):

```powershell
even entity add "Pier Nine Holdings" --kind organization
# reload GET /
```

Overview `entities` count went 1 → 2 on plain reload. The build and the data
are fully independent as locked in D5.

## `even serve` (D3)

```powershell
even serve --port 4362
```

Printed the JSON status line (`"mode": "built"`, resolved `workspace_root`,
`url`) then served: `GET /` → 200 and the pagination API answered correctly
through the CLI-launched process. `Ctrl+C` terminates the child. Error paths
(`web_project_missing`, `pnpm_missing`, `node_missing`) return JSON with
exit code 1.

## Known Gaps

- No automated Node-side test harness yet (playwright exists in the
  precedent repo; adopt when pages multiply). All proofs above are manual
  transcripts.
- Client-side island interactions (page clicks, sort clicks, filter typing)
  verified only through the API contract they call, not through a browser
  automation run.
- `even serve --dev` path exercised implicitly (built path proven; dev falls
  back through the same pnpm script used during development).
