# Implementation: Knowledge Layers Merge

Date: 2026-06-07
Status: First public-engine slice implemented.

## Changes

- Reviewed the existing knowledge-layer inputs:
  - `merge-plan.md`
  - `evidence-memory-survey.md`
  - `evidence_memory_consolidation_handover.md`
- Reviewed the related global routing index packet:
  - `plans/2026-06-06-global-routing-indexes/plan.md`
  - `plans/2026-06-06-global-routing-indexes/survey.md`
- Reviewed the current repo state through README, the binding corpus-cache CLI
  spec, `catalog.yaml`, and the current CLI entrypoint.
- Created `plan.md` for the knowledge-layer merge with:
  - problem summary;
  - resolution summary;
  - current and proposed CLI surfaces;
  - private-document and private-media scope;
  - global routing index fit;
  - small open points;
  - big design decisions.
- Reworked `plan.md` after design-decision review:
  - accepted `documents-manager` as the public name and "evidence engine" as
    the technical description;
  - removed `manage` from the V1 CLI direction;
  - deferred `handoff` from V1 scope;
  - clarified that the public contract is open local data plus search access,
    not functional API transfer between layers;
  - clarified one-way dependency: private repos may know public catalogs, but
    public code must not know private catalogs;
  - rebuilt the open-points table with proposal confidence and option shape.
- Reworked `plan.md` after open-point review:
  - removed backward-compatibility assumptions for `documents-manager`;
  - recorded that old generated catalogs and indexes may be wiped/reset;
  - moved source inventory direction from `scan folder` to `sources scan`;
  - kept `media scan` out of scope and retained `media inspect`,
    `media describe`, and `media dedupe`;
  - moved results/reports direction to caller workspace output;
  - made search CLI/JSON the initial fully abstracted access surface;
  - initially considered schema discovery and a future stdio-like surface;
  - deferred private workspace template and DB-vs-Markdown decisions to private
    repo planning;
  - allowed shallow generated media descriptions as public generated
    observations while keeping deep identity/location analysis private.
- Clarified future command schema/transport direction:
  - no MCP-compatible commitment;
  - MCP-inspired at most;
  - schema discovery and `--input <json-file>` are deferred;
  - default operation remains CLI arguments plus file output.
- Implemented the first public-engine code slice:
  - renamed the Python package to `documents_manager`;
  - changed the console script to `documents-manager`;
  - moved generated storage to the caller workspace `.documents-manager/`;
  - changed stdout to JSON-first command payloads;
  - replaced `scan folder` with `sources scan`;
  - replaced `parse folder` with `docs parse`;
  - replaced `index folder` with `index scope`;
  - removed the public `catalog migrate` command and added `catalog wipe`;
  - changed stale/incomplete beta catalogs to return `reset_required` instead
    of silently migrating;
  - renamed public registry tables/templates to `fts` and `semantic` names.

## Notes

- The implemented CLI intentionally avoids a vague `manage` root and splits
  responsibilities into direct nouns.
- No backward compatibility alias was kept for the older command surface.
- Future schema discovery, `--input <json-file>`, and any MCP-inspired
  long-lived transport remain deferred.
