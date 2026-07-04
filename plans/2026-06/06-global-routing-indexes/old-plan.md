# Plan: Global Routing Indexes

Date: 2026-06-06
Status: Superseded 2026-06-11. Decision statuses for OP-001..OP-020 are now
tracked in `plan.md` (see its "Where every OP landed" table); this file is kept
as the original critique and phase breakdown.

## Problem Summary

The hand-in proposes a multi-resolution document search architecture: keep
SQLite as durable truth, keep full FTS and semantic indexes scoped by root or
index scope, add lightweight global representative indexes for query routing,
and use lossy summaries only to route toward deeper evidence.

This direction fits the repository's purpose, but it is ahead of the current
implementation. The repo currently has catalog control, health, fixed cache
paths, structured scan results, and `scan folder`. Parsing, indexing, and
search are reserved command surfaces. The current contracts also keep generated
chunks and backend rows out of SQLite.

The plan must therefore separate architectural intent from accepted work. It
should preserve the good routing model while explicitly resolving the schema,
privacy, CLI, and ranking decisions before code is written.

## Resolution Summary

Use the hand-in as an architecture candidate, not as direct implementation
scope.

Accepted planning premises:

- SQLite remains the source of truth for source roots, source items, documents,
  objects, valuable items, index scopes, lower-index registries, and accepted
  current representative metadata.
- Root-scoped lower indexes remain the evidence layer.
- Global representative indexes may route broad queries to likely roots,
  folders, documents, or clusters.
- Lossy summaries cannot prove absence.
- Search should widen when representative routing is weak.
- Materialized collection indexes are an optimization for repeated broad
  retrieval, not a V1 requirement.

Rejected or constrained premises:

- Do not store generated chunks or lower-index rows in SQLite.
- Do not add command logs or raw query histories to SQLite without a narrower
  aggregate usage decision.
- Do not auto-split user roots into many physical scopes until the planning and
  review behavior is accepted.
- Do not make global semantic routing a prerequisite for the first routing
  implementation.

## Goal

Decide and document the global routing architecture so the repo can later
implement a minimal, contract-compatible search routing layer without
violating the existing catalog, fixed-cache, privacy, and CLI design.

## Objectives

- Critique the hand-in against the current repo purpose and contracts.
- Identify which ideas fit now, which need schema or CLI changes, and which
  should be deferred.
- List all open design decisions with stable IDs so they can be reviewed one
  by one.
- Define the smallest credible implementation slice after decisions are
  resolved.
- Keep this plan folder consistent with the repo workflow.

## Scope

This planning packet covers:

- representative summary metadata;
- global representative FTS and optional later global representative semantic
  indexes;
- routing from global representatives into root-scoped lower indexes;
- lossy folder/root/document/cluster summaries as routing signals;
- search widening behavior and result confidence at a search-hit level;
- future materialized collection indexes as an optimization path.

## Non-Goals

- No implementation in this packet.
- No change to `catalog.yaml` until schema decisions are accepted.
- No automatic root splitting.
- No new cache-root argument.
- No arbitrary SQL wrapper.
- No raw private text or query log persistence by default.
- No answer synthesis layer before search hit retrieval is stable.
- No global LanceDB requirement before global FTS routing proves useful.

## Critical Assessment

| Hand-In Idea | Fit | Critique |
| --- | --- | --- |
| SQLite is authoritative. | Fits with constraints. | It must mean authoritative current metadata and registries, not generated chunks, backend rows, or logs. |
| Root-scoped indexes. | Fits. | This is already the V1 store policy. Keep it as the proof layer. |
| Global representative indexes. | Fits after design decisions. | Needs registry, path, template, and rebuild semantics. |
| Lossy folder summaries. | Fits. | They need provenance, coverage, and confidence because they are not evidence. |
| Search widening loop. | Fits. | Needs budget defaults and structured status output before ranking gets complex. |
| Summary nodes table. | Probably fits. | Must be current-state only and must not become summary history or raw chunk storage. |
| Query usage tracking. | Does not fit yet. | Current contracts keep command runs out of SQLite. This needs a narrow aggregate design or deferral. |
| Automatic scope suggestions. | Partly fits. | Good as scan planning output; not acceptable as automatic scope mutation in V1. |
| Materialized collections. | Later. | Useful only after repeated broad queries prove the need. |
| Global semantic routing. | Later. | Adds embedding cost and profile complexity; FTS representatives should come first. |

## Open Design Points

| ID | Point | Proposed Default | Status |
| --- | --- | --- | --- |
| OP-001 | Should `summary_nodes` be added to SQLite? | Yes, as current-state representative metadata only. | Open |
| OP-002 | What summary node kinds are accepted for the first pass? | `root_summary`, `folder_summary`, `document_summary`, `negative_summary`. | Open |
| OP-003 | How should a global representative index be represented in existing registry tables? | Add a reserved `index_scopes` row with `scope_kind = specialist` and `relative_path = global_representatives`, or add explicit global registry fields. | Open |
| OP-004 | Should `index_scopes.root_id` remain required for global/specialist scopes? | Prefer avoiding synthetic source roots; adjust schema if global scopes need no root. | Open |
| OP-005 | Should global FTS path templates be added to `config/exposures.yaml`? | Yes: `fts/global_representatives/{fts_profile}/` or equivalent. | Open |
| OP-006 | Should representative row templates be separate from chunk templates? | Yes. Representative rows have summary provenance and routing fields, not chunk evidence fields. | Open |
| OP-007 | Should `search text` accept explicit scope controls? | Defer new flags; first implement default all-roots routing after search exists. | Open |
| OP-008 | What is the first routing implementation? | Global representative FTS routes to root-scoped FTS. | Open |
| OP-009 | When should global LanceDB representatives be added? | After FTS routing and root-scoped LanceDB are working. | Open |
| OP-010 | How are lossy summaries generated? | Start extractive or deterministic from metadata/object text; require a separate decision before LLM summaries. | Open |
| OP-011 | Are remote models allowed for summary generation? | No default remote model; any remote provider must be explicit caller policy. | Open |
| OP-012 | How much provenance must a summary keep? | Store source object IDs, sample policy, content hash, coverage estimate, and confidence. | Open |
| OP-013 | Should query usage be stored in SQLite? | Defer, or store only aggregate counters keyed by route/index/scope, not raw query text. | Open |
| OP-014 | Should scan suggest automatic child scopes? | Yes as review output only; do not auto-create many active scopes by default. | Open |
| OP-015 | What generated folders get negative summaries versus exclusion? | Default excludes remain excluded; optional negative summaries are only for included but low-value folders. | Open |
| OP-016 | How should archives route? | Manifest summary first; deep unpack/index only with opt-in or strong routing hit. | Open |
| OP-017 | What does "good enough" mean for widening? | Define simple thresholds on hit count, score gap, and hydrated evidence availability. | Open |
| OP-018 | How are scores normalized across roots? | Keep initial router rank separate from deep index score; avoid pretending cross-index BM25 scores are globally calibrated. | Open |
| OP-019 | What result contract should search return? | JSONL hits with route trace, hydrated catalog IDs, snippets, scores, and widening status. | Open |
| OP-020 | When are materialized collection indexes created? | Manual command or future explicit promotion; not automatic in first pass. | Open |

## Implementation Phases

### Phase 0: Decision Review

Deliverables:

- review this plan and resolve OP items;
- record accepted decisions in this `plan.md`;
- update durable spec only for decisions that become binding.

Exit:

- no critical OP remains open for the first implementation slice.

### Phase 1: Schema And Template Contracts

Candidate deliverables after acceptance:

- add `summary_nodes` to `catalog.yaml`;
- add representative FTS template to `store_templates.yaml`;
- add global representative cache path to `config/exposures.yaml`;
- add routing and summary defaults to `config/parser.yaml` or a dedicated
  search config file.

Exit:

- catalog migration and status still pass;
- generated chunk tables remain out of SQLite.

### Phase 2: Representative Build Inputs

Candidate deliverables:

- build deterministic summary input packs from inventory, metadata, filenames,
  headings, object previews, and selected text once parse/index layers exist;
- write current `summary_nodes`;
- mark summaries stale when source items or objects change.

Exit:

- summaries can be rebuilt from catalog state;
- summary provenance is inspectable and redaction-safe.

### Phase 3: Global Representative FTS

Candidate deliverables:

- generate representative FTS rows from `summary_nodes`;
- register the global FTS index;
- rebuild global representatives when summary content changes.

Exit:

- a query can return likely roots/scopes without searching every deep index.

### Phase 4: Routed Search

Candidate deliverables:

- `search text` searches global representatives first;
- selected roots/scopes are searched in deep root-scoped FTS indexes;
- weak results widen according to configured budgets;
- output includes route trace and hydrated catalog IDs.

Exit:

- broad queries avoid blind fanout when representative routing is confident;
- weak routing falls back predictably.

### Phase 5: Later Optimizations

Candidate deliverables:

- global LanceDB representatives;
- aggregate query usage counters;
- materialized collection indexes;
- better score calibration and ranking evaluation fixtures.

Exit:

- only after Phase 4 is stable and repeated broad query behavior justifies the
  extra physical indexes.

## Dependencies

- Existing parse/index work from the Docling search index plan.
- Stable lower Tantivy FTS build and search behavior.
- A catalog migration path for any new `summary_nodes` table.
- Redaction rules for summary text, snippets, and route traces.
- Test fixtures with multiple roots or at least multiple scopes.

## Risks

- Representative summaries can hide important minority content if treated as
  proof instead of routing.
- Synthetic global scopes could pollute source-root semantics.
- Cross-index score merging can produce misleading rank if scores are treated
  as calibrated.
- Query usage tracking could violate the current no-command-log-in-SQLite
  contract.
- Global semantic routing may add dependency and embedding cost before the
  simpler FTS path proves useful.

## Exit Criteria

- Each OP item required for the first implementation slice is accepted,
  rejected, or deferred.
- The accepted slice does not contradict the fixed-cache contract.
- The accepted slice does not put generated chunks or backend rows in SQLite.
- The accepted slice preserves root-scoped deep indexes as the proof layer.
- The accepted slice defines how global representative indexes are registered,
  rebuilt, and searched.
- `implementation.md` records planning changes and later implementation facts.
- `test.md` records document review and, later, runtime proof.

