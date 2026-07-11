# Open Plans

Plan packets with work still outstanding. See each folder for details.

- [Web UI Viewer](./2026-07/04-webui-viewer/plan.md) — all decisions locked;
  Milestones 0–1 implemented and proven (`src/web` + `even serve`, overview
  and server-paginated source tables); Milestone 2+ (entities, search, runs,
  review actions) remains.
- [Evidence Engine Trust, Structure, And Retrieval Improvements](./2026-07/10-engine-improvements/plan.md)
  — implementation-ready plan for immutable reviewed evidence, split durable
  state, typed Docling objects, auditable review, calibrated/routed retrieval,
  and an evaluation harness. Milestone 0 (spec update, `corpus_cache`/
  `corpus_state` schema-contract split, failing trust-gap regression proof,
  deterministic evaluation baseline) is done — see `implementation.md`/
  `test.md`. Milestones 1-8 (physical store split/migration, immutable
  occurrence ledger, typed Docling normalization, transactional review, rank
  fusion, recursive retrieval, bounded visual routing, evaluation gates)
  remain, gated on Milestone 0 in that order.
