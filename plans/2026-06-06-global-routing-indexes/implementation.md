# Implementation Log: Global Routing Indexes

Date: 2026-06-06
Status: D0 and D1 implemented. Document and media representatives route through
the global representative FTS map.

## Progress

`▰▰▰▰▱▱ D0 ✅ · D1 ✅ · D2+ ▱` — D0 (Phases 1–5: schema, document summaries,
global representative FTS, routed search, tests) and the D1 media-representative
slice are implemented and tested. Media-cluster summaries, global semantic
representatives, and SigLIP routing remain future slices.

## Changes Made

- Added `survey.md` with local repo inventory and critique of the hand-in.
- Added `plan.md` with problem summary, fit assessment, constrained scope,
  open design points, phases, risks, and exit criteria.
- Added this implementation log to satisfy the dated plan packet workflow.
- Added `test.md` with planning-review proof.

## Important Decisions

- Treated `handing-in.md` as architecture input, not approved implementation
  scope.
- Kept generated chunks and lower-index backend rows out of SQLite in the
  proposed direction.
- Framed global representative indexes as a later accepted slice after open
  design points are resolved.
- Recommended global representative FTS before global representative LanceDB.

## Deviations

- The user asked mainly for a new `plan.md`; this packet also adds
  `survey.md`, `implementation.md`, and `test.md` because repository workflow
  requires every dated plan folder to contain `plan.md`, `implementation.md`,
  and `test.md`, and discovery-heavy planning should include `survey.md`.

## 2026-06-11: Decision record closed

- Rewrote `plan.md` as a full decision record (Problem summary / Resolution
  summary first, then decision tables). All F/S/M/D points marked Decided.
- Carried the seven previously untouched open points (OP-007, OP-013..OP-017,
  OP-020) into the plan's tracking table and resolved them.
- Added an OP-001..OP-020 traceability table; noted that F3 reverses OP-010's
  extractive-first default and F2 rejects catalog registration for global
  representative indexes.
- New decisions: S5 (media-bearing documents treated as folders of images,
  `container_kind` column), M7 (absent-facet renormalization + skipped widening
  rungs), RRF as the V1 cross-route merge rule (F4).
- Clarified F2: vectors never enter SQLite; per-profile rebuild sources (text
  from SQLite alone; siglip from `summary_nodes` medoid IDs + per-scope
  LanceDB stores).
- Runtime change: renamed `AGENTS_DOCS_OLLAMA_RERANK_MODEL` to
  `EVEN_OLLAMA_RERANK_MODEL` in `src/even/hybrid.py` (pre-rebrand leftover);
  decided the `EVEN_` prefix as the env-flag convention.
- Updated `plans/open.md` status row.

## 2026-06-14: Implementation readiness pass

- Rewrote `plan.md` into a self-contained implementation plan for D0, so active
  implementation scope no longer depends on archived drafts.
- Added D0 goal, scope, non-goals, implementation phases, dependencies, risks,
  exit criteria, and test expectations.
- Sharpened the `summary_nodes` catalog proposal with concrete columns,
  indexes, nullable media fields, current-state status fields, canonical
  `source_refs_json`, and schema-version/reset expectations.
- Added the expected representative FTS template and fixed global projection
  paths while preserving the decision that global representative stores are not
  registered in catalog tables.
- Added the explicit `even index routing <path>` build-command proposal so
  normal `index scope` behavior does not become model-bound.
- Added routed `search text` behavior, route trace shape, D0 thresholds, and
  fallback-all-current-FTS behavior.
- Refreshed `test.md` to reflect the repo's current parse/index/search
  implementation state.
- Updated `plans/open.md` to point only at the active implementation-ready plan.

## 2026-06-14: D0 implementation

- Added `summary_nodes` to `catalog.yaml` and bumped the catalog schema/user
  version to `0.7` / `7`.
- Added the `fts_summary_node` store template, fixed global representative
  exposure paths, `config/routing.yaml`, and `config/README.md`.
- Added routing config loading and packaged the new config files in
  `pyproject.toml`.
- Implemented `src/even/routing.py` for document-only root summaries, local
  Ollama summary generation, fixed-path global representative FTS builds,
  sidecar manifest watermarks, routed `search text`, route traces, and fallback
  behavior.
- Added `even index routing <path>` with `--force`, `--limit`,
  `--summary-model`, and `--summary-ollama-url`.
- Updated FTS search to route by default for `search text`; `search hybrid`
  explicitly keeps the existing all-current-FTS candidate behavior.
- Updated README and the durable CLI spec for `summary_nodes`, `index routing`,
  fixed-path global representative projections, and routed `search text`.
- Added `tests/test_routing.py` covering catalog schema/version, parser surface,
  fake-summary indexing, media exclusion from D0 summaries, and routed search
  over a multi-root fixture.

## 2026-06-14: D1 media representative routing

- Extended `index_routing` to attempt both document `root_summary` generation
  and media `album_summary` generation for the same active root scope.
- Added media summary inputs from existing `media_assets`, source filenames,
  typed image/video/3D metadata, and current caption/media-kind observations.
- Kept document summary prompts document-only; media summaries have a separate
  prompt, profile, watermark, deterministic routing-text facets, and
  `corpus_cache.media_assets.<asset_id>` refs.
- Changed the global representative FTS projection to include all current
  `summary_nodes` with non-empty `routing_text`, not only `modality=text` rows.
- Preserved the explicit local-Ollama build path. There is no deterministic
  summary fallback and no remote API fallback in the minimal laptop scope.
- Updated README, the durable CLI spec, config notes, `plan.md`, and routing
  tests for the implemented media slice.

## 2026-06-26: O1 budget + importance hardened (spec + plan)

- Reviewed how each root is represented in the global index. Confirmed the
  per-root volume budget is currently implicit (one node per kind) and that the
  `kind` enum already permits unbounded hierarchical nodes once D2 lands.
- Verified the root-scoped (proof) indexes are exhaustive, not budgeted:
  `semantic.index_scope_to_semantic` embeds all `chunks_for_root` +
  `media_chunks_for_root`; FTS scans with `max_files=None`. Budget/lossiness is
  therefore a routing-layer concept only.
- Added a `Global Representation Contract` section to
  `specifications/corpus-cache-cli/spec.md`: representation unit, two-layer
  opposite contracts, the typed per-root budget envelope (`max_entries`,
  `embedding_units`, `cpu_seconds`, `local_llm_tokens`, `remote_llm_tokens`),
  mandatory `root_summary` floor, lossy-by-budget, importance, backend parity,
  and `representation_policy_version`.
- Recorded the O1 decision in `plan.md` (F5/F6 + B1..B10 table) and added the
  budget-envelope flags and policy version to the Configuration table.
- Open schema follow-ups noted: `importance` column home and projection-time
  budget enforcement; precedence-on-overflow remains tracked as O5.
- No code or schema changes in this pass; spec/plan hardening only.

## 2026-06-26: O3/O5/O6/O7 closed (spec + plan)

- O3 (per-unit cost): reframed the budget so wall-clock time is primary.
  `max_build_seconds` default `300` (5 min) per root is the decisive cost limit;
  token/embedding budgets derive from `max_build_seconds × tokens_per_sec`, where
  `tokens_per_sec` is measured-and-cached per machine and self-corrected.
- O5 (precedence): added deterministic selection order — reserve `root_summary`,
  then `album_summary`, then companions by importance desc → `coverage_estimate`
  desc → `summary_id`; overflow counted not silent; low-importance overflow may
  roll up into one `negative_summary`.
- O6 (sampling-policy honesty): decided to rename `text_stratified_v1` →
  `doc_roundrobin_v1` at implementation time; `text_stratified_v1` reserved for a
  real stratified sampler. Not yet applied to code to avoid churning
  watermarks/tests mid-design.
- O7 (importance): importance is a structured side output of the summary call
  (`{summary_text, importance}`), no separate rationale field; the prompt asks the
  model to surface the reason inside the summary only for extreme cases. Confirmed
  the only existing classifier is media `media_kind` in `describe_folder_to_catalog`
  (`classify_kind`); documents have no classifier and importance is new. Added a
  dynamic low-importance prior list (`node_modules`, `.git`, `.venv`/`venv`,
  git-ignored, OS folders) that updates from model feedback. Importance lands as a
  `real` `summary_nodes.importance` column.
- Hardened all four in the spec `Global Representation Contract` (time-primary
  budget + dynamic calibration, importance side output, importance priors,
  selection precedence) and recorded B11–B14 plus updated B1/B8 and the config
  table in `plan.md`.
- All D0 representation open points (O1–O7) are now closed at the contract level.
  Still spec/plan only — no code or schema changes landed.

## 2026-06-26: D0 hardening step 1+2 implemented (schema + importance)

- Schema foundation: added `summary_nodes.importance` (`real`, `[0,1]`) to
  `catalog.yaml`, bumped `spec_version` to `0.8`, and bumped
  `CATALOG_SCHEMA_VERSION`/`CATALOG_USER_VERSION` to `0.8`/`8`. Beta catalogs
  reset-and-rebuild on this bump (existing behavior).
- Config: added `representation_policy_version`, `max_build_seconds` (300),
  `max_entries` (20), and importance settings (`importance_default`,
  `importance_low_prior`, `importance_priors` list) to `config/routing.yaml`.
- Importance side output: bumped the summary/media prompts to v2 to request a
  trailing `IMPORTANCE: <0..1>` line, parsed and stripped by `_parse_importance`,
  with deterministic `_importance_prior` (low for `node_modules`, `.git`,
  `.venv`/`venv`, etc.) as fallback via `_resolve_importance`. Importance is now
  written by `_upsert_summary_row` for document and media root summaries.
- Wired `representation_policy_version` into the global FTS watermark and manifest
  (manifest `schema_version` now tracks `CATALOG_SCHEMA_VERSION`), so policy or
  schema changes force a projection rebuild.
- Tests: bumped the catalog-version assertion to 8 and added `importance` column,
  `_parse_importance`, `_importance_prior`, stored-model-importance, and
  prior-fallback tests. `uv run pytest` 36 passed; `uv run ruff check .` clean.
- Not yet implemented (later steps): projection-time budget enforcement and
  selection precedence, `tokens_per_sec` calibration and derived token budgets,
  dynamic prior-list feedback updates, and the `text_stratified_v1` →
  `doc_roundrobin_v1` rename.

## 2026-06-26: D0 hardening step 3 implemented (budget + precedence)

- Added projection-time per-root budget enforcement. `_select_budgeted_rows`
  groups current units by root, always keeps reserved L0 units (`root_summary`,
  `album_summary`), and fills the remaining log-scaled budget with companions
  ranked by importance desc → coverage desc → summary_id. `_entry_budget` is
  `clamp(round(1 + 2·log10(source_total)), 1, max_entries)` (default
  `max_entries=20`).
- Applied selection in both `build_global_representative_fts` and
  `_search_global_representatives`, so the FTS projection and the staleness
  watermark use the identical trimmed unit set (parity-ready for the future
  semantic projection).
- Overflow units are dropped from the projection but counted: build result
  `counts.summary_nodes_overflow` and manifest `overflow_count`.
- `_current_summary_rows` now also returns `source_count`, `coverage_estimate`,
  and `importance` for selection.
- For D0/D1 (only reserved L0 units exist) selection is a no-op, so shipped
  behavior is unchanged; the guard activates when D2 companions land.
- Tests: `test_entry_budget_is_log_scaled_and_capped` and
  `test_select_budgeted_rows_reserves_l0_and_ranks_companions`. `uv run pytest`
  38 passed; `uv run ruff check .` clean.
- Still not implemented: `tokens_per_sec` calibration + derived token budgets,
  dynamic prior-list feedback, `negative_summary` overflow rollup, and the
  `text_stratified_v1` → `doc_roundrobin_v1` rename.

## 2026-06-26: D0 hardening step 4 implemented (time budget + calibration)

- Made wall-clock time the decisive build budget. `RoutingIndexOptions` gained
  `max_build_seconds` (default from `config/routing.yaml`, 300). In `index_routing`
  the mandatory `root_summary` always runs; the media album companion is skipped
  with `error_kind="build_budget_exhausted"` once the per-root budget is reached.
- Added `tokens_per_sec` measure-and-cache calibration. `_generate_and_calibrate`
  times each summary call, estimates tokens (~4 chars/token), and EMA-updates a
  workspace-local `calibration.json` (`even/paths.py:calibration_path`).
  Near-instant (fake/cached) generations below 50 ms are ignored so they do not
  skew the value; absent calibration falls back to `CALIBRATION_DEFAULT_TPS=50`.
- Derived an advisory `_token_budget = max_build_seconds × tokens_per_sec`, and
  surfaced a `representation_budget` block (`max_build_seconds`, `tokens_per_sec`,
  `derived_token_budget`, `elapsed_seconds`) on the `index routing` result.
- Tests: `test_tokens_per_sec_calibration_math` (pure) and
  `test_index_routing_skips_media_when_build_budget_exhausted` (budget=0 skips the
  companion, keeps the mandatory root_summary). `uv run pytest` 40 passed;
  `uv run ruff check .` clean.
- Still not implemented: derived embedding budget (no semantic projection yet),
  dynamic prior-list feedback, `negative_summary` overflow rollup, and the
  `text_stratified_v1` → `doc_roundrobin_v1` rename.

## 2026-06-26: D0 closed (step 5 — rollup, dynamic priors, O6 rename)

- `negative_summary` overflow rollup: `_select_budgeted_rows` now collapses each
  root's dropped low-importance overflow into one synthesized `negative_summary`
  projection unit (`neg_<root_id>`, importance 0.05, routing_text listing the
  dropped titles), so deprioritized content stays visible to the router instead of
  vanishing. The rollup is a projection artifact, never stored in `summary_nodes`.
- Dynamic importance priors: when the model rates a root below
  `importance_learn_threshold` (default 0.2), `_learn_low_prior` records the path
  basename into `calibration.json`; `_importance_prior` now consults both the
  configured priors and this learned list, so a missed folder gets demoted on
  later builds (the node_modules-style feedback loop).
- O6 rename: sampling policy `text_stratified_v1` → `doc_roundrobin_v1` in
  `config/routing.yaml` and the `config.py` fallback (kept in sync, and the
  fallback now also carries the budget/importance keys). `text_stratified_v1`
  stays reserved for a real stratified sampler.
- Tests: rollup assertions folded into the budget test, plus
  `test_index_routing_learns_low_importance_prior`. `uv run pytest` 41 passed;
  `uv run ruff check .` clean.
- D0 representation contract (O1–O7) is now fully implemented and tested. The only
  contract item left is the derived embedding budget, which is intentionally
  deferred to the D2 semantic-representative slice (no semantic projection exists
  to budget yet).

## 2026-06-26: RP1 payload model + DP1 embedding-source correction

- RP1: replaced the flat `summary_nodes.routing_text` blob with structured
  `routing_meta` (json). `summary_text` keeps the model prose; `routing_meta`
  holds deterministic facets (paths/titles/headings/captions/metadata). The
  searchable/embeddable `routing_payload = summary_text + flattened routing_meta`
  is derived at projection time by one shared `_routing_payload`, so FTS and the
  future semantic store consume the identical payload (parity by construction) and
  the summary is no longer stored twice.
- Code: `_deterministic_routing_text`/`_media_routing_text` → `_document_routing_meta`/
  `_media_routing_meta` (return dicts); added `_routing_payload` + `_clean_routing_meta`;
  `_upsert_summary_row` stores `routing_meta` json; `_current_summary_rows` derives
  and filters on `routing_payload`; FTS schema/writer/search field `routing_text` →
  `routing_payload`; `_representative_watermark` and `_negative_rollup` updated.
- Schema: `catalog.yaml` `routing_text` (text) → `routing_meta` (json); catalog
  bumped `0.8`/`8` → `0.9`/`9`. `store_templates.yaml` `fts_summary_node` field
  `routing_text` → `routing_payload`.
- DP1 (D2 prep): corrected B4 and the spec. The text semantic representative store
  embeds `routing_payload` **fresh** (it is not a proof chunk → no vector to
  reuse); cost is low because the representative set is budget-bounded, not via
  reuse. Vector reuse is reserved for the SigLIP medoid route.
- Tests: catalog-version assertion → 9, asserts `routing_meta` present /
  `routing_text` absent; doc/media projection tests read `routing_meta`; rollup
  test reads `routing_payload`. `uv run pytest` 41 passed; `uv run ruff check .`
  clean.

## 2026-06-26: D2 decisions recorded + Retrieval Strategy v1 (list + budget)

- Hardened the D2 decision record (DP2–DP5) and the Retrieval Strategy / Auto Mode
  design into `plan.md`; updated the `route_trace` contract with the multi-route
  (`routes` + `fused_selection`) shape; added the `semantic_summary_node` template
  to `store_templates.yaml`; updated `spec.md` (multi-route routing paragraph,
  `list` command, `search --budget`).
- Implemented the cheap available pieces of the strategy layer:
  - `even list [path]` — `list_representatives()` walks current `summary_nodes`
    grouped by root (no query, no model); optional path filter on `source_uri`.
  - `search text --budget low|mid|high` (default `mid`) — `SearchOptions.budget`
    drives routed-scope fanout (`low`=1, `mid`=config, `high`=wider); the budget is
    stamped into `route_trace`. When deep search returns no hits, representative
    hits are attached as `routing_suggestions` (no-hit → routing fallback).
  - `high` recursive deepening into companion summaries is deferred until those
    exist (D2+); for now `high` widens fanout.
- DP2–DP5 (the semantic-rep store itself, fused RRF route, parity test) remain to
  build; the payload/template/mechanics are now pinned.
- Tests: `test_parser_exposes_list_and_search_budget`,
  `test_list_representatives_lists_current_nodes`,
  `test_search_text_low_budget_limits_fanout`. `uv run pytest` 44 passed;
  `uv run ruff check .` clean.

## Follow-Up Risks

- Media cluster summaries, global semantic representative stores, and SigLIP
  representative routing remain future work.
- D1 automated tests use a fake summary generator so CI does not require a
  local model; a manual Ollama proof should be recorded before relying on media
  summaries with a real personal corpus.
