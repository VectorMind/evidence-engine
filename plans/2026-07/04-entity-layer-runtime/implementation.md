# Implementation: Entity Layer Runtime And Reference Example

Progress: [##########] Done

## What Was Built

- `src/even/entities.py`: the entity runtime. `add_entity`, `list_entities`,
  `show_entity`, `add_alias`, `add_link`, `review_target`, and
  `find_entity_evidence`, plus small `Add*Options`/`FindEntityEvidenceOptions`
  dataclasses matching the codebase's existing per-command options pattern.
  IDs are `uuid4`-based (`ent_<hex32>`, `alias_<hex32>`, `link_<hex32>`,
  `task_<hex32>`) rather than content-hash stable IDs, because entity/alias/
  link creation is a non-idempotent user action (unlike the deterministic
  producer pipelines elsewhere in the engine) -- calling `entity add` twice
  with the same name must create two rows, not upsert one.
- `src/even/references.py`: added `parse_ref` and `resolve_ref`. There was no
  existing generic way to hydrate a `corpus_cache.<table>.<row_id>` reference
  back to its live row; `resolve_ref` derives the primary-key column from
  `catalog.yaml`'s `pk_<table>` index-naming convention (already implicit in
  every table definition) so it works for any current or future referenceable
  table without a hardcoded table map.
- `src/even/cli.py`: `even entity add|list|show|alias|link|review|find`,
  wired the same way as every other command (`CommandRun.start` / `.finish`,
  JSON stdout, non-zero exit on failure). No ad hoc SQL in the CLI layer --
  every handler calls straight into `even.entities`.
- `tests/test_entities.py` (13 tests) and `tests/test_entity_cli.py` (6 tests):
  unit and CLI-contract coverage, including the durability guarantee (`review_target`
  on a link never changes the referenced evidence row) and the reference-integrity
  guard (`add_link` refuses an unresolvable ref).
- `tests/fixtures/entities-basic/`: the confirmed reference example fixture --
  a hand-built minimal PDF (`northwind-field-report.pdf`, matching the existing
  `parse-basic/dummy.pdf` construction style) mentioning "Northwind Salvage"
  and, under an older-invoice framing, "N.W. Salvage", plus a synthetic image
  (`northwind_salvage_pier9.png`) whose filename hints at the same entity. Both
  evidence types are covered by the worked example without deviating from the
  plan's candidate.
- Documentation: README CLI table, a new "Entity Contract" section in
  `specifications/corpus-cache-cli/spec.md`, and a short explanatory paragraph
  in the README's command-narrative section.

## Deviation From The CLI Sketch

The plan's sketch showed `entity find <entity-id> [--query ...] [--image PATH]`.
Implemented instead as `entity find <entity-id> <query> [--image PATH]` --
`query` is a mandatory positional argument, mirroring `search text <query>`'s
own contract exactly, since `find_entity_evidence` is a thin wrapper around
`search_text_indexes` and that command has no query-less mode. The plan
explicitly left exact flags to settle during implementation.

## Mid-Implementation Fix

While running the worked example, `entity find`'s cross-modal probe
(`--image`) produced no visible `route_trace` in its output even though the
underlying `search_text_indexes` call always returns one. Cause:
`find_entity_evidence` originally reconstructed a narrow payload
(`status`/`hits`/`counts` only) instead of passing the full search result
through. Fixed to `payload = dict(result)` plus the entity-specific additions
(`entity_id`, `query`, `proposed_links`), so `route_trace`, `failures`, and
`skipped` now surface exactly as they do from `search text` directly. Covered
by re-running the worked example after the fix (see `test.md`).

## Scope Notes

- `review_target` only covers the four target kinds this module actually
  writes (`entities`, `entity_aliases`, `entity_evidence_links`,
  `review_tasks`). `entity_classifications`, `entity_attributes`, and
  `entity_relationships` have catalog tables but no CLI writer in this pass
  (matches the plan's out-of-scope list), so no review path was built for them
  either -- adding one before there is a producer would be speculative.
- `attrs_json` is left `NULL` on every directly-created row (`entity add`,
  `entity alias`, `entity link`); it is populated only on links/tasks written
  by `entity find --propose`, where it records the originating query, hit
  path, and score for audit purposes. No CLI flag exposes `attrs_json`
  directly yet -- not required by the plan's scope.

## Routing Feedback Memo

Required by the plan as a first-class deliverable, even if the answer were
"no gaps found." It wasn't quite that clean:

1. **Real gap, fixed:** there was no reusable way to resolve a `ref:` string
   back to a row anywhere in the engine before this plan. Every existing
   module either didn't need to (search only produces refs, never consumes
   them) or worked around it locally. `resolve_ref` in `references.py` closes
   that gap generically, using the existing `pk_<table>` naming convention
   from `catalog.yaml`. This is reusable by the web UI plan for the same
   "hydrate a reference into a viewable row" need.
2. **Real gap, fixed:** `find_entity_evidence` silently dropped diagnostic
   fields (`route_trace`, `failures`, `skipped`) from the wrapped search call.
   Worth a general note for future search wrappers: `search_text_indexes`'s
   return shape is not obvious from a glance, and cherry-picking fields from it
   is an easy way to lose diagnostics. Spread the full result and only add to
   it.
3. **Fixture limitation, not a code gap:** the confirmed reference example has
   exactly one index scope, so the cross-modal probe's scope-selection effect
   (`counts.image_hits_returned`, visual-route ranking) has nothing to
   discriminate between and is not observably exercised end-to-end by this
   worked example -- it returns `status: ok` and no extra image hits, which is
   correct given a single-scope corpus, not a failure. The probe's actual
   ranking behavior is already covered by `tests/test_routing.py`'s
   multi-scope unit tests; proving it top-down through `entity find` would
   need a second index scope, which is out of scope for a minimal reference
   example.
4. **No other gaps found.** The central hoped-for validation held on the first
   try: every search hit already carries a `ref` (via
   `_first(stored, "ref")` in `fts.py` and `evidence_ref(...)` in
   `image_index.py`), so `entity link` could bind a hit's `ref` directly with
   no new plumbing beyond `attach_hit_refs`, and `entity show` could hydrate
   both document and media evidence through the same generic `resolve_ref`
   path. The Layer-3 API shape the routing/entity plans anticipated back in
   `plans/2026-06/28-entity-layer-ownership/` needed no redesign.

## Post-Landing Fixes (2026-07-04)

Two minor observations from the post-landing review, fixed directly:

- `add_alias` now validates `evidence_ref` the same way `add_link` does:
  a ref that does not resolve to a current row is refused with
  `error_kind: evidence_ref_not_found` instead of being stored blind. The CLI
  never exposed the flag, so no CLI behavior changed -- this closes the
  module-level path only. Covered by
  `test_add_alias_rejects_unresolvable_evidence_ref`.
- `entity find --propose` now skips hits whose ref the entity already links
  (any status), so re-running the same discovery query never duplicates
  proposed links or review tasks. Dedupe also applies within a single result
  set. Recorded in the spec's Entity Contract section; covered by
  `test_find_entity_evidence_propose_never_duplicates_links`.

## Follow-Up Risks

- `review_target`'s prefix-based target-kind lookup (`ent_`, `alias_`,
  `link_`, `task_`) assumes IDs never collide across kinds by prefix; safe
  today since prefixes are fixed constants, but would need revisiting if a
  future producer introduces its own ID scheme.
- No entity merge/dedupe workflow exists yet (explicitly out of scope); two
  entities proposed for the same real-world thing currently coexist with no
  guided path to `entity_status = merged` beyond a manual `entity review`-style
  follow-up this plan did not build.
