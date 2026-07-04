# Plan: Entity Layer Runtime And Reference Example

Date: 2026-07-04
Closed: 2026-07-04
Status: Closed - implemented and proven

## Problem Summary

The Indexes layer (Layer 3) — including the scope router and the
entity/cross-modal probe — was designed and tuned for a consumer that does not
exist yet. `plans/2026-06-28-entity-layer-ownership/` gave the engine ownership
of the generic Layer-4 entity catalog and added the tables to `catalog.yaml`
(`entities`, `entity_aliases`, `entity_evidence_links`,
`entity_classifications`, `entity_attributes`, `entity_relationships`,
`review_tasks`), but explicitly scoped out entity CRUD. Today:

- no code in `src/even/` can create, alias, link, or review an entity;
- the README's central story — one entity binding heterogeneous evidence by
  `ref:` — has never been executed;
- the routing layer has only been validated bottom-up (ad hoc search queries),
  never top-down by the discovery→bind workflow it was built for.

This plan closes that gap: a minimal entity runtime (API + CLI) plus **one
worked reference example** that drives search, routing, and the cross-modal
probe end-to-end and records what that exercise reveals about Layer 3.

## Direction Decisions (2026-07-04)

- Build-time pipeline execution (scan, parse, index, routing) stays CLI-only,
  driven by an admin role. No server, daemon, or UI-triggered tasks in this
  plan.
- The web UI is a separate later plan
  (`plans/2026-07-04-webui-viewer/`). It consumes the data outputs this plan
  stabilizes; nothing here may depend on it.
- Reference-example selection is expected to need real discussion. This plan
  fixes the *criteria* and commits to **at least one** example; further
  examples are follow-up work, not exit criteria.

## Scope

In scope:

- `src/even/entities.py`: entity runtime helpers over the existing catalog
  tables — create/list/show entities, add aliases, add evidence links, record
  review decisions, open/close review tasks. Follows existing conventions:
  JSON-first payloads, UTC timestamps, stable text IDs, `evidence_ref` strings
  from `references.py`.
- CLI surface under `even entity ...` (see CLI Sketch below), JSON on stdout,
  consistent with the existing command contract.
- A discovery bridge: `even entity find` wrapping the existing public search
  (`text`/`hybrid`, optional `--image` cross-modal probe) and returning hits
  with their canonical `ref` plus the entity context, so a hit can be bound in
  one follow-up command. Optionally `--propose` to record candidate links as
  `proposed` rows plus open `review_tasks`.
- One synthetic reference example: fixture corpus, scripted end-to-end run,
  proof in `test.md`.
- A short **routing feedback memo** in this packet recording what the entity
  workflow revealed about the Layer-3 API (gaps, awkward shapes, missing
  fields). This is a first-class deliverable, not a nice-to-have — validating
  Layer 3 top-down is the point of the plan.
- Documentation: README CLI table + Current Status, and a new "Entity
  Contract" section in `specifications/corpus-cache-cli/spec.md` describing
  the durable rules (review state is never overwritten by re-parse/re-index;
  links store `ref` strings only, never copies).

Out of scope:

- model-driven or agentic entity *proposal* pipelines (NER, auto-extraction);
  producers in this plan are humans and the search-assisted `--propose` flow;
- entity merge/dedupe workflows beyond setting `entity_status = merged`
  manually;
- any UI (web viewer, review buttons) — deferred to the web UI plan;
- domain-specific schemas (tax, family, vehicles, ...) — stay above the engine;
- committing real private entity rows anywhere; fixtures are synthetic;
- migration of old beta catalogs (wipe/rebuild remains the contract).

## CLI Sketch

```text
even entity add <name> --kind <kind> [--description ...] [--status proposed|active]
even entity list [--kind ...] [--status ...] [--review ...]
even entity show <entity-id>                      # entity + aliases + links + tasks, hydrated
even entity alias <entity-id> <alias-text> [--kind name|identifier|...]
even entity link <entity-id> <evidence-ref> --role mention|visual_match|... [--status proposed]
even entity review <target-id> --accept|--reject|--defer   # entity, link, or task by id
even entity find <entity-id> [--query ...] [--image PATH]  # discovery via search + probe
```

Exact flags settle during implementation; the fixed points are: JSON stdout,
`evidence_ref` strings as the only way links point at evidence, and review
decisions writing `review_status`/`link_status`/`task_status` without ever
mutating Layer-2/3 rows.

## Reference Example

Selection criteria (fixed by this plan):

1. fully synthetic and redaction-safe — committable to the public repo;
2. spans **at least two evidence types** across both branches (e.g. a mention
   inside a parsed document and a filename/caption-hinted image);
3. exercisable on the `laptop` extra without a GPU; model-dependent steps
   (captions, summaries via Ollama) may be included but the example must
   degrade to a provable core without them;
4. small enough that scan→parse→index→routing→find→link→review runs in a test
   or a single scripted session from a clean `EVEN_CACHE`.

Candidate (to confirm at milestone 1): a synthetic organization
("Northwind Salvage") with a fixture folder `tests/fixtures/entities-basic/`
containing one small PDF/text document mentioning it under two spellings, and
one or two images whose filenames/synthetic metadata hint at it. The worked
example: create the entity, alias the second spelling, `entity find` with a
text query (and `--image` when the image-search extra is present), bind the
returned refs as `mention` and `visual_match` links, accept one and reject one
via review, then `entity show` proving the full provenance trail.

## Milestones

1. **Confirm the reference example.** Settle the fixture design against the
   criteria above with the maintainer; record the decision in this packet.
2. **Entity runtime module.** `src/even/entities.py` with catalog read/write
   helpers and unit tests (`tests/test_entities.py`) against a temp catalog.
3. **CLI surface.** `even entity` subcommands wired in `cli.py`, JSON stdout,
   contract tests alongside the existing `test_cli_contract.py` style.
4. **Discovery bridge.** `entity find` over public search with `ref`-carrying
   hits; `--propose` writing proposed links + review tasks.
5. **Worked example end-to-end.** Fixture corpus committed; scripted run from
   clean cache through review; recorded in `test.md`.
6. **Docs + spec + feedback memo.** README and spec updated; routing feedback
   memo written; packet closed.

## Exit Criteria

- A new catalog accepts entity rows through `even entity` commands only; all
  writes go through the runtime module, no ad hoc SQL in the CLI layer.
- `entity link` accepts exactly the `corpus_cache.<table>.<row_id>` reference
  strings that search hits already expose, and `entity show` hydrates them by
  reading the referenced rows (Reference Contract respected: no copying).
- The reference example runs end-to-end from a clean `EVEN_CACHE` and is
  reproducible from `test.md` alone; the cross-modal probe path is exercised
  when the `image-search` extra is installed and skipped cleanly when not.
- Re-running `docs parse` / `index scope` / `index routing` over the fixture
  does not alter any entity, link, or review row (durable-review guarantee
  proven by a test).
- README CLI table and the spec's new Entity Contract section are current.
- The routing feedback memo exists in this packet, even if its content is
  "no gaps found".
