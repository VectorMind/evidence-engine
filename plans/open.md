# Open Plans

Plan packets with work still outstanding. See each folder for details.

| Plan | Date | Status | What remains |
| --- | --- | --- | --- |
| [2026-06-06-global-routing-indexes](2026-06-06-global-routing-indexes/) | 2026-06-06 | D0 + D1 implemented; D0 representation contract closed in code; later media/semantic slices remain open. | D0/D1 implemented and tested. The D0 global-representation contract (O1–O7) is now fully implemented and tested: `summary_nodes.importance` column (catalog 0.8/8), importance summary side output with deterministic + dynamic learned priors, projection-time per-root budget enforcement with selection precedence, overflow counting and `negative_summary` rollup, the time-primary `max_build_seconds` budget with `tokens_per_sec` calibration, `representation_policy_version`, and the `doc_roundrobin_v1` rename. Deferred to D2 (not a D0 gap): the derived embedding budget + FTS/semantic parity, which need an actual semantic projection. Remaining future slices: media-cluster summaries, global semantic representative stores, and SigLIP representative routing. |
| [2026-06-11-repo-consolidation](2026-06-11-repo-consolidation/) | 2026-06-11 | Proposed — awaiting maintainer review. | Absorb `private-documents` + `private-media` designs into this repo, create one private knowledge base, archive both private repos. 5 open points (OP-001..OP-005) in [plan.md](2026-06-11-repo-consolidation/plan.md); OP-001 (knowledge-base location) gates Phase 3. Phases 1-4 all pending. |
