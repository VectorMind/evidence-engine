# Open Plans

Plan packets with work still outstanding. See each folder for details.

| Plan | Date | Status | What remains |
| --- | --- | --- | --- |
| [2026-06-06-global-routing-indexes](2026-06-06-global-routing-indexes/) | 2026-06-06 | D0 + D1 implemented; D0 representation contract hardened; later media slices remain open. | D0/D1 implemented and tested. The D0 global-representation contract is now hardened in the spec and plan: per-root budget envelope (time-primary `max_build_seconds`, log-scaled `max_entries`), mandatory `root_summary` floor, importance (summary side output + dynamic priors), selection precedence, FTS/vector parity, and `representation_policy_version`. Not yet landed in code/schema: `summary_nodes.importance` column, projection-time budget enforcement, `tokens_per_sec` calibration, `text_stratified_v1`→`doc_roundrobin_v1` rename. Media-cluster summaries, global semantic representative stores, and SigLIP representative routing remain future slices. |
| [2026-06-11-repo-consolidation](2026-06-11-repo-consolidation/) | 2026-06-11 | Proposed — awaiting maintainer review. | Absorb `private-documents` + `private-media` designs into this repo, create one private knowledge base, archive both private repos. 5 open points (OP-001..OP-005) in [plan.md](2026-06-11-repo-consolidation/plan.md); OP-001 (knowledge-base location) gates Phase 3. Phases 1-4 all pending. |
