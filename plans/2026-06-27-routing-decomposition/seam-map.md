# Phase 1 — Verified Seam Map (OP-002 / OP-003 resolved)

Derived from an AST call-graph of `src/even/routing.py` (120 top-level
defs/classes), assigned to submodules, then checked for module-level import
cycles and per-module size. **Result: acyclic DAG, every module under the ~800
target.** Cycle check and sizing reproduced by the analysis script in the
hand-off notes.

## Module DAG (leaf → root; an import may only point left/down)

```
_shared            (no routing deps)
  ← budget         → _shared
  ← importance     → budget, _shared
  ← medoids        → _shared
  ← summary_store  → _shared
  ← media_summaries→ budget, importance, medoids, summary_store, _shared
  ← summaries      → budget, importance, summary_store, _shared
  ← representative_store      → summary_store, _shared
  ← representatives (build)   → representative_store, summary_store, medoids, _shared
  ← representative_search     → representative_store, summary_store, _shared
  ← search         → representative_search, medoids, _shared
  ← __init__       → summaries, media_summaries, representatives, budget, _shared
```

No edge points back up — verified by DFS cycle detection (CYCLES: NONE).

## Two design corrections to the plan's first-draft cut

1. **`summaries.py` would have been ~1446 lines** (well over target). Split into
   four real seams: `summaries` (root/document generation), `media_summaries`
   (media album + cluster generation), `summary_store` (the summary-node
   read/write/budget layer that representatives consume), and `importance`
   (prior/learn subsystem). Largest resulting module: `media_summaries` ~705.

2. **`RoutingIndexOptions` and `SummaryGenerationError` must live in `_shared`,
   not `__init__`.** They are referenced by `_upsert_*` (summaries/media) as well
   as the orchestrator. Leaving them in `__init__` created the only real cycle
   (`init → representatives → summary_store → … → init`). Moving them to
   `_shared` breaks it. `RoutingIndexOptions` is also part of the external facade
   (`cli.py`), so `__init__` re-exports it from `_shared`.

3. **The feared `summaries ↔ representatives` cycle (OP-003) does not exist.**
   The summary *writers* (`_upsert_*`) never read summaries back; only the
   *representatives* read via `summary_store` (`_current_summary_rows`,
   `_select_budgeted_rows`). So `representatives → summary_store` is one-way.

4. **`representatives` (~804 body lines) is split build/search.** The three
   `build_*` orchestrators feed `index_routing`; the three `_search_global_*`
   readers feed the search engine. Splitting into `representatives` (build,
   ~430), `representative_search` (~291), and `representative_store` (shared
   manifest/watermark/uri/medoid-row helpers, ~130) keeps each well under target
   and removes the build machinery from `search`'s dependency closure.

## Three shared helpers relocated to break root/media coupling

- `_root_source_item_id` → `summary_store` (catalog lookup used by both upserts).
- `_coverage` (sample/source ratio math) → `_shared`.
- `_clean_routing_meta` (prune-empty dict helper) → `_shared`.

## Function → module assignment

**`_shared.py`** — module constants (`GLOBAL_*`, `*_PROMPT_VERSION`,
`MEDIA_*_PROFILE`, `_IMPORTANCE_RE`), `RoutingIndexOptions`,
`SummaryGenerationError`, `_iso`, `_utc_now`, `_json_object`, `_json_field`,
`_first`, `_summary_id`, `_media_summary_id`, `_media_cluster_summary_id`,
`_empty_watermark`, `_routing_defaults`, `_fts_profile`, `_chunk_profile`,
`_tantivy_runtime_status`, `_tantivy_index_exists`, `_image_profile_name`,
`_embedding_profile_name`, `_coverage`, `_clean_routing_meta`.

**`budget.py`** — `_estimate_tokens`, `_blend_tokens_per_sec`, `_token_budget`,
`_load_calibration`, `_save_calibration`, `_current_tokens_per_sec`,
`_record_calibration`, `_generate_and_calibrate`, `_build_budget_report`,
`_budget_skipped_summary`.

**`importance.py`** — `_parse_importance`, `_importance_prior`,
`_importance_learn_threshold`, `_learned_low_priors`, `_learn_low_prior`,
`_resolve_importance`.

**`medoids.py`** — `_kmeans_medoids`, `_album_medoids`, `_media_asset_clusters`,
`_assign_to_medoids`, `_normalized_vector`, `_mean_vector`,
`_media_cluster_k_max`, `_media_cluster_title`.

**`summary_store.py`** — `_current_summary_rows`, `_select_budgeted_rows`,
`_entry_budget`, `_precedence_key`, `_negative_rollup`, `_routing_payload`,
`_upsert_summary_row`, `_summary_state`, `_representation_policy_version`,
`_root_source_item_id`.

**`summaries.py`** — `_upsert_root_summary`, `_generate_summary_text`,
`_validated_local_base_url`, `_sample_chunks`, `_summary_prompt`,
`_document_routing_meta`, `_source_refs`, `_primary_summary`,
`_blocked_summary_status`, `_summary_payloads`, `_combined_summary_counts`.

**`media_summaries.py`** — `_upsert_media_summary`,
`_upsert_media_cluster_summaries`, `_media_assets_for_root`,
`_sample_media_assets`, `_media_summary_prompt`, `_media_metadata_facets`,
`_media_routing_meta`, `_media_source_refs`, `_media_high_watermark`,
`_media_modality`, `_dominant_media_kind`, `_media_cluster_summary_text`,
`_media_cluster_attrs`, `_media_cluster_importance`,
`_delete_stale_media_clusters`, `_media_summary_attrs`, `_value_counts`.

**`representative_store.py`** — `_manifest_current`, `_representative_watermark`,
`_siglip_watermark`, `_global_fts_uri`, `_global_semantic_uri`,
`_global_siglip_uri`, `_current_album_medoid_rows`.

**`representatives.py`** (build) — `build_global_representative_fts`,
`build_global_representative_semantic`, `build_global_representative_siglip`,
`_write_global_fts_index`, `_global_fts_schema`, `_write_global_semantic_index`,
`_semantic_row`, `_write_global_siglip_index`, `_siglip_row`, `_write_manifest`.

**`representative_search.py`** — `_search_global_representatives`,
`_search_global_representatives_semantic`,
`_search_global_representatives_siglip`.

**`search.py`** — `search_text_with_routing`, `_routed_fts_only`,
`_fuse_representative_hits`, `_multi_route_trace`, `_query_budget`,
`_budget_max_scopes`, `_finalize_route`, `_selected_scopes`,
`_weak_route_reasons`, `_recursive_deepening_trace`, `_summary_region_rows`,
`_summary_region_precedence`, `_summary_region_payload`, `_route_trace`,
`_fallback_trace`, `_deep_searches`, `_visual_route_from_images`,
`_scoped_image_hits`.

**`__init__.py`** — `index_routing`, `list_representatives`, plus the facade
re-export block (OP-001).

## OP-001 — facade

Re-export from `__init__` the public names (`RoutingIndexOptions`,
`index_routing`, `list_representatives`, `search_text_with_routing`, and
`build_global_representative_siglip` — the test imports this fifth name too, which
the plan's original facade list missed) **plus** the 10 tested privates so
`tests/test_routing.py` needs zero churn:

| tested private | now lives in |
| --- | --- |
| `_blend_tokens_per_sec` | `budget` |
| `_estimate_tokens` | `budget` |
| `_token_budget` | `budget` |
| `_entry_budget` | `summary_store` |
| `_select_budgeted_rows` | `summary_store` |
| `_importance_prior` | `importance` |
| `_parse_importance` | `importance` |
| `_kmeans_medoids` | `medoids` |
| `_fuse_representative_hits` | `search` |
| `_search_global_representatives_siglip` | `representative_search` |

Tightening test imports to point at submodules is deferred to Phase 5 (optional).
