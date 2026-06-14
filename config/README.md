# Evidence Engine Config

Configuration contracts in this directory describe generated storage and local
runtime defaults. They are public defaults, not private workspace policy.

## Routing

`routing.yaml` controls global representative routing defaults:

- `representative_top_k`: global summary hits considered before deep search.
- `max_routed_scopes`: maximum root scopes searched before widening.
- `min_hydrated_deep_hits`: minimum deep evidence hits before routing is
  considered strong enough.
- `min_representative_score_gap`: minimum score gap between the top two
  representative hits. If the gap is weaker, routed search falls back to all
  current FTS scopes.
- `summary_sample_chunks_default`: maximum document chunks sampled into one
  summary prompt.
- `summary_sample_chars_per_chunk`: excerpt budget per sampled chunk.
- `summary_prompt_max_chars`: total prompt budget for local summary generation.
- `summary_model`: default local Ollama model. Override with
  `EVEN_SUMMARY_MODEL`.
- `summary_ollama_url`: default local Ollama URL. Override with
  `EVEN_SUMMARY_OLLAMA_URL`.

Summary generation only accepts localhost Ollama endpoints. Global
representative indexes are derived cache projections and are not catalog
registry rows.
