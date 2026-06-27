# Test Proof: Global Routing Indexes

Date: 2026-06-14
Status: D0/D1 runtime proof recorded.

## Commands And Checks

| Check | Expected | Actual |
| --- | --- | --- |
| List repo root. | Confirm project shape and workflow files. | Found Python CLI repo with `src`, `tests`, `docs`, `plans`, `specifications`, `catalog.yaml`, and config files. |
| List target plan folder. | Confirm existing hand-in and missing required plan files. | Folder contained `handing-in.md` only before this packet. |
| `git status --short` | Identify dirty worktree and avoid unrelated edits. | Existing unrelated modifications were present outside this plan folder. |
| Read `handing-in.md`. | Extract proposed architecture. | Found proposal for SQLite truth, root-scoped indexes, global representatives, lossy summaries, routing, widening, usage tracking, and collections. |
| Read README, workflow, spec, schema, configs, and selected source files. | Compare hand-in to current repo purpose and contracts. | Confirmed current implementation includes catalog, scan, parse, media inspect/describe, root-scoped FTS, semantic search, hybrid search, image search, and global representative routing. |
| Review active plan references. | Ensure active packet does not depend on superseded drafts for implementation scope. | `plan.md` is now self-contained; `plans/open.md` points at `plan.md` instead of archived drafts. |
| Review schema landing details. | Make `summary_nodes` implementable from the plan. | `plan.md` now specifies columns, indexes, fixed projection paths, document/media summary behavior, build command, route trace, fallback behavior, and test expectations. |
| `uv run pytest tests/test_routing.py` | Routing-focused tests pass. | Passed: 7 tests. Covers catalog version/table, CLI parser, fake-summary indexing, document-only prompt isolation, media album summaries, routed media search, and routed document search. |
| `uv run pytest` | Full suite passes. | Passed: 32 tests. |
| `uv run ruff check .` | Lint is clean. | Passed: all checks. |

## Review Result

The planning packet is internally consistent with repository workflow:

- `survey.md` records the local inventory and critique.
- `plan.md` records scoped planning, closed design points, D0/D1 implementation
  phases, `summary_nodes` schema proposal, risks, and exit criteria.
- `implementation.md` records the D0/D1 implementation facts.
- `test.md` records planning-review proof and runtime proof.

## Runtime Tests

The first sandboxed `uv run pytest tests/test_routing.py` attempt could not
access the normal uv cache directory; the command was rerun with approved cache
access. Full-suite and ruff checks also used approved cache access.

Automated tests use a fake summary generator so the suite does not require a
local model. The D1 media summary path has not yet been manually proven with a
live Ollama model on a real media folder.

## 2026-06-26: Contract-vs-implementation gap (D0 hardening)

The D0 global-representation contract (O1–O7) is now hardened in the spec and
plan. Implementation is landing in steps.

Implemented and tested (step 1+2, 2026-06-26):

- `summary_nodes.importance` column (`real`, `[0,1]`) and catalog version bump to
  `0.8`/`8` — `test_summary_nodes_catalog_contract` checks the column and version;
- importance as a structured summary side output with deterministic prior
  fallback — `test_parse_importance_extracts_and_strips_marker`,
  `test_importance_prior_low_for_tooling_paths`,
  `test_index_routing_stores_model_importance`,
  `test_index_routing_falls_back_to_importance_prior`;
- `representation_policy_version` in the global FTS watermark and manifest.

Implemented and tested (step 3, 2026-06-26):

- projection-time per-root budget enforcement (log-scaled `_entry_budget`,
  `max_entries` default 20) with reserved L0 units and importance/coverage/id
  precedence — `test_entry_budget_is_log_scaled_and_capped`,
  `test_select_budgeted_rows_reserves_l0_and_ranks_companions`;
- identical trimmed unit set feeds the FTS projection and the staleness
  watermark (parity-ready), with overflow counted in build counts and manifest.

Implemented and tested (step 4, 2026-06-26):

- `max_build_seconds` decisive time budget skips the media companion when the
  per-root budget is reached while keeping the mandatory `root_summary` —
  `test_index_routing_skips_media_when_build_budget_exhausted`;
- `tokens_per_sec` measure-and-cache calibration (EMA, workspace `calibration.json`)
  and the derived token budget — `test_tokens_per_sec_calibration_math`.

Implemented and tested (step 5, 2026-06-26 — D0 close):

- `negative_summary` overflow rollup (one synthesized unit per root with dropped
  companions) — folded into
  `test_select_budgeted_rows_reserves_l0_and_ranks_companions`;
- dynamic low-importance prior learning from model feedback —
  `test_index_routing_learns_low_importance_prior`;
- O6 sampling-policy rename `text_stratified_v1` → `doc_roundrobin_v1` (configs +
  `config.py` fallback in sync).

Implemented and tested (RP1 + DP1, 2026-06-26):

- `routing_text` blob → structured `routing_meta` (json) with projection-time
  `routing_payload`; catalog bumped `0.9`/`9`. Verified by the catalog-contract
  test (`routing_meta` present, `routing_text` absent), the doc/media projection
  tests (read `routing_meta`), and the rollup test (reads `routing_payload`). The
  DP1 correction (embed `routing_payload` fresh; reuse is SigLIP-medoid-only) is
  recorded in spec/plan; the embedding itself lands with the D2 semantic slice.

Implemented and tested (Retrieval Strategy v1, 2026-06-26):

- `even list [path]` lists the current `summary_nodes` hierarchy —
  `test_parser_exposes_list_and_search_budget`,
  `test_list_representatives_lists_current_nodes`;
- `search text --budget low|mid|high` drives routed-scope fanout and stamps the
  budget into `route_trace` — `test_search_text_low_budget_limits_fanout`.

Implemented and tested (D2 semantic representative store, 2026-06-26):

- `build_global_representative_semantic` embeds `routing_payload` fresh into a
  LanceDB store over the identical budgeted unit set (DP1/DP2/DP5);
- fused FTS+semantic representative route with RRF and the multi-route
  `routes`/`fused_selection` trace (DP4), opt-in via `index routing --semantic` —
  `test_fuse_representative_hits_ranks_shared_unit_first`,
  `test_semantic_representative_route_fuses_with_fts` (monkeypatched embedder, real
  LanceDB, no model download; asserts FTS/semantic parity count + fused trace).

Run: `uv run pytest` → 46 passed; `uv run ruff check .` → clean.

Real-embedding benchmark (2026-06-26, CPU, `fastembed_bge_small_en_v1_5`, 384-dim):
embedded 300 routing_payload-shaped texts in 2.85 s → ~105 texts/s, ~29.7k
chars/s, ~7.4k approx tokens/s; one-time model load+warmup ~7 s. Confirms
embedding is negligible vs LLM summary generation, so the budget-bounded
representative set embeds near-instantly. The fake-embedder automated tests stand;
the routing semantic store has not yet been built with the real model on a real
corpus.

D0 representation contract (O1–O7) plus RP1 is fully implemented and tested. The
only remaining contract item is the **derived embedding budget**, intentionally
deferred to the D2 semantic-representative slice (no semantic projection exists to
budget yet), and the FTS/semantic backend parity it would exercise.

Current behavior (1 `root_summary` + 1 `album_summary` per scope, projected as one
FTS doc each) stays within the hardened contract, so the shipped D0/D1 tests
remain valid; the items above extend it.

## 2026-06-27: D3 media SigLIP representative routing (B1–B3)

Spec consolidation first (Modality Asymmetry + Media representatives clauses;
README two-lane diagram), then built B1–B3.

Implemented and tested:

- B1 medoid selection — `test_kmeans_medoids_selects_one_per_cluster` (pure scipy
  k-means picks one medoid per visual cluster) and
  `test_index_routing_persists_album_medoids_in_attrs` (medoid `asset_id`s +
  `medoid_profile` land on `album_summary.attrs`, reusing the per-scope image proof
  vectors);
- B2 global SigLIP store — `test_build_global_siglip_store_reuses_medoid_vectors`
  (one row per medoid, `albums=1`, reused vectors, idempotent unforced rebuild ⇒
  `current`/`unchanged`);
- B3 fusable visual route — `test_siglip_route_returns_fusable_album_hits` (the
  visual route returns album-keyed hits and fuses with a text route at scope
  granularity via the shared RRF).

- B4 cross-modal probe — `test_search_text_image_engages_visual_route_and_returns_image_hits`
  (`search text --image` engages the SigLIP visual route in fusion and returns image
  hits from the routed scopes alongside text hits; monkeypatched embedder/runtime,
  registered per-scope image store, real LanceDB).

Tests use real LanceDB with synthetic 3-dim vectors and no model download (torch is
not needed to build/search the store — medoid vectors are reused; the B4 test fakes
the query-time SigLIP embedder). The SigLIP representative store has **not** yet been
built from real SigLIP vectors on a real photo corpus; that end-to-end manual proof
(`index scope --image` → `index routing --semantic` → `search text --image` with a
real model) remains open.

Run: `uv run pytest` → 51 passed; `uv run ruff check .` → clean.
