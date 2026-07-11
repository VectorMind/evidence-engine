# Evaluation

Deterministic retrieval/routing baselines for the
`plans/2026-07/10-engine-improvements` plan packet. Milestone 0 seeds the
format and captures a pre-change baseline; Milestone 8 grows this into the
full evaluation harness (more scenarios, a CI gate, model-dependent opt-in
benchmarks).

## Layout

- `datasets/<name>/<root>/*.txt` — a small, checked-in, multi-root fixture
  corpus. Each top-level folder under a dataset is scanned as its own root
  (its own FTS/semantic/routing scope), so cross-root ("multi-scope")
  queries are possible. Filenames are unique across the whole dataset so a
  hit can be judged by `relative_path` alone.
- `queries/<name>.json` — a list of `{query_id, text, note, scopes_expected}`.
  `scopes_expected` names the root(s) whose evidence a fully-correct answer
  must draw from; a query naming more than one root is a deliberate
  multi-scope case that a single-best-scope (`--budget low`) route cannot
  answer without widening.
- `judgments/<name>.json` — `{query_id: [relative_path, ...]}`, the
  hand-authored relevant-document set for each query, small enough to
  eyeball against the dataset's fixture files.
- `runners/run_<name>_baseline.py` — builds a temporary workspace, seeds the
  fixture corpus, builds FTS/semantic/routing indexes, runs every query
  against exhaustive text, routed text (`low`/`mid`/`high` budget), and
  hybrid search, scores the hits against the judgments, and writes a report.
- `reports/<name>-baseline.json` — the committed output of the runner. Future
  milestones must not regress these numbers without documented
  justification (see the plan packet's Risks And Mitigations /
  Dependencies And Sequencing sections).

## Determinism

Runners avoid both Docling and network-dependent embedding models so the
baseline is reproducible offline:

- document evidence is seeded directly through
  `even.parse._write_parsed_document` (the same private entry point Docling
  parsing itself writes through), bypassing the Docling converter;
- semantic embeddings use a small deterministic vocabulary-overlap vector
  function instead of a downloaded model, by monkeypatching
  `even.semantic._embed_passages`/`_embed_query` — the same pattern
  `tests/test_routing.py` already uses for deterministic semantic-routing
  tests;
- routing summaries use a deterministic fake summary generator instead of a
  local LLM, again following `tests/test_routing.py`'s existing
  `_fake_summary` convention.

Image-to-image and text-to-media baselines are out of scope for the
`milestone0` dataset (no image fixtures yet); the runner records them as
`skipped` rather than omitting the section, so future datasets can add image
fixtures without changing the report shape.

## Running

```powershell
python evaluation/runners/run_milestone0_baseline.py
```

This does not require network access, Docling, Ollama, or a downloaded
embedding model. It requires `tantivy` and `lancedb`/`fastembed` (the
project's normal semantic/FTS extras) to be installed; sections whose
runtime dependency is missing are reported as `skipped`, not treated as a
failure.
