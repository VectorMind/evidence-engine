# Plan: Web UI Viewer (Placeholder)

Date: 2026-07-04
Status: Placeholder — direction notes only, not approved for implementation.
Blocked on: `plans/2026-07/04-entity-layer-runtime/` closing and the data
outputs (results JSON, summaries, entity tables) taking stable shape.

## Direction (agreed 2026-07-04)

One unified local server-rendered viewer replaces the scattered per-run
outputs (`results/*/summary.md`, ad hoc HTML under `reports/`) as the human
surface over the evidence cache. Working name: `even serve`.

Fixed points, to be expanded into real scope when this plan opens:

- **SSR from the start.** Server-side rendered pages over big tables
  (maintainer has prior warehouse-server table-rendering patterns to reuse);
  no SPA build pipeline as a baseline requirement. Set up incrementally.
- **Read-only first, contract-only always.** The viewer consumes exactly the
  public data contract: `catalog.sqlite` (read-only), `results/`, `reports/`,
  and the public search CLI/API. If a page needs something the contract does
  not expose, that is a contract gap to fix in the engine — never a private
  hook into internals. The viewer is a proof of the contract.
- **Analytics-focused, honest rendering.** Faithful provenance-preserving
  rendering of catalog analytics, run results, summaries, and search — with
  `ref:` trails resolvable to the evidence rows. Explicit non-goal: a general
  file/OS explorer over every detail.
- **Monitoring, not launching.** The viewer may render progress of runs by
  tailing `events.jsonl` written by CLI-launched commands. It does not launch
  tasks: build-time pipeline execution (scan/parse/index/routing) stays
  CLI-only under an admin role. A control pane is deliberately dropped for
  now; revisit only if a real need forces it.
- **Review interactions come second.** After the read-only viewer works,
  entity review tables get actions (accept/reject/defer, bind link) that
  write through the same entity runtime API the CLI uses — no second write
  path.

## Rough Shape (to refine at opening)

```text
even serve                       # local-only HTTP, SSR pages
  /            overview: catalog status, roots, counts, recent runs
  /runs        results/ browser: result.json + summary.md rendered, events tail
  /search      text/semantic/hybrid/image query pages over the public search API
  /entities    entity tables: filters, aliases, links, review queue
  /evidence/<ref>   hydrated view of one referenced row with provenance
```

## Open Questions (settle when plan opens)

- Stack: Python-side SSR (e.g. FastAPI/Starlette + templates + htmx-style
  partials) inside the `even` package vs. reusing the maintainer's existing
  warehouse-server approach as a sibling process reading the contract.
- Pagination/streaming strategy for large catalog tables.
- Whether `reports/` HTML generation is deprecated once the viewer covers it.
- Packaging: new optional extra (e.g. `serve`) so the baseline CLI stays lean.

## Exit Criteria

None yet — placeholder. Real scope, milestones, and exit criteria are written
when the entity runtime plan closes and this plan is opened.
