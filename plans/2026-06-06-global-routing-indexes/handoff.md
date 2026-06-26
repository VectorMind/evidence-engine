# Handoff: Global Routing Indexes

Date: 2026-06-26
Purpose: resume pointer for a fresh session. Read this first, then `plan.md`
(decisions) and `implementation.md` (dated build log).

## Status in one line

D0 + D1 are implemented and tested; the **D0 global-representation contract
(O1–O7) is now fully implemented in code** (importance, per-root budget,
precedence, `negative_summary` rollup, time-primary budget + calibration). Tests:
`uv run pytest` → 41 passed; `uv run ruff check .` → clean.

## Git state (IMPORTANT — work is uncommitted)

On branch `main`. Nothing for the D0 implementation is committed yet.

- Uncommitted working changes (11 files): `catalog.yaml`, `config/routing.yaml`,
  `src/even/{catalog,config,paths,routing}.py`, `tests/test_routing.py`, and the
  four plan-packet docs + `plans/open.md`.
- `specifications/corpus-cache-cli/spec.md` is **already committed** in `ec4b69c`
  (its `Global Representation Contract` section is in HEAD). So the hardened spec
  is persisted, but the code that implements it is not.
- Suggested next git action: branch off `main` and commit the D0 implementation
  (the spec is already in, so a fresh session need not re-add it).

## What this session did

1. Reviewed the D0 question ("how each root is represented in the global index")
   and surfaced open points O1–O7.
2. Hardened them into `spec.md` (`Global Representation Contract`) and `plan.md`
   (decisions F5/F6 + B1–B14), per-point with user sign-off.
3. Implemented the contract in five steps (see `implementation.md` dated entries
   for 2026-06-26):
   - schema: `summary_nodes.importance` (`real`), catalog `0.8`/`8`;
   - importance as a structured summary side output + deterministic priors;
   - projection-time per-root budget + selection precedence + overflow counting;
   - time-primary `max_build_seconds` budget + `tokens_per_sec` calibration;
   - `negative_summary` overflow rollup, dynamic learned priors, O6 rename.

## Code surface (where the new logic lives, all in `src/even/routing.py`)

- Budget/selection: `_entry_budget`, `_precedence_key`, `_select_budgeted_rows`
  (reserves L0 `root_summary`/`album_summary`, ranks companions by
  importance→coverage→id), `_negative_rollup`. Applied in
  `build_global_representative_fts` and `_search_global_representatives` so FTS and
  the staleness watermark consume the identical trimmed set.
- Importance: `_parse_importance` (strips `IMPORTANCE: <0..1>` from model text),
  `_importance_prior` (config + learned priors), `_resolve_importance`,
  `_learn_low_prior` / `_learned_low_priors` (feedback into `calibration.json`).
  Threaded through `_upsert_root_summary` / `_upsert_media_summary` and persisted
  by `_upsert_summary_row`.
- Time budget + calibration: `RoutingIndexOptions.max_build_seconds`,
  `_generate_and_calibrate`, `_record_calibration`, `_current_tokens_per_sec`,
  `_token_budget`, `_build_budget_report`. Calibration sidecar at
  `paths.calibration_path()` = `.cache/even/calibration.json`.
- Config keys (in `config/routing.yaml` and the `config.py` fallback — keep in
  sync): `representation_policy_version`, `max_build_seconds`, `max_entries`,
  `importance_default`, `importance_low_prior`, `importance_learn_threshold`,
  `importance_priors`, and `sample_policy: doc_roundrobin_v1`.

## How to verify

```
uv run pytest tests/test_routing.py -q   # 16 routing tests
uv run pytest -q                          # 41 total
uv run ruff check .
```

Note: automated tests use a fake summary generator. The media (D1) path and the
new importance side output have **not** been proven against a live Ollama model on
a real corpus — record a manual run before trusting them in production.

## What's next

- **Deferred from D0 (it is a D2 dependency, not a gap):** the derived embedding
  budget and the FTS/semantic backend parity it would exercise need an actual
  semantic representative projection, which is the D2 "global semantic
  representative store" slice.
- **Future slices (unbuilt), recommended order:** D2 global semantic (text-vector)
  representative store → SigLIP image-representative routing → media-cluster
  summaries. Rationale and trade-offs are in this session's analysis; the semantic
  slice reuses `src/even/semantic.py` and is the first to exercise RRF fusion.
- The D2 slice is where `embedding_units` budgeting and the parity contract get
  implemented and tested for real.
