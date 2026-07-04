# Plan: Plans Layout Refactor

Date: 2026-07-04
Closed: 2026-07-04
Status: Closed - implemented and proven

## Problem Summary

The repository had standardized on flat plan packet paths under
`plans/YYYY-MM-DD-<slug>/`, but the maintainer wants month buckets with packet
folders nested under them as `plans/YYYY-MM/DD-<slug>/`. The existing tree,
top-level packet indexes, and workflow guidance still assumed the old layout,
so moving packets without a coordinated reference update would leave broken
links and stale instructions.

## Resolution Summary

Move every existing packet into a `YYYY-MM` month folder with a `DD-<slug>`
leaf folder, then update the workflow surfaces and in-repo packet references to
use the new canonical layout. Leave historical references to other repositories
unchanged.

## Scope

In scope:

- move all existing plan packet directories into `plans/YYYY-MM/DD-<slug>/`;
- update `AGENTS.md`, `WORKFLOW.md`, and `plans/README.md` to define the new
  layout for future work;
- fix in-repo links and path references in `plans/open.md`, `plans/closed.md`,
  `README.md`, source comments, and packet cross-references;
- record proof that internal stale-path references were cleaned up.

Out of scope:

- changing packet status semantics beyond path updates;
- rewriting historical references to external repositories that still use their
  own layout;
- introducing automation beyond the documented workflow contract.

## Implementation Phases

1. Inventory existing packet directories and in-repo path references.
2. Move packet directories into month buckets.
3. Update workflow docs and packet indexes to the new canonical layout.
4. Rewrite in-repo packet references and confirm no stale internal paths
   remain.

## Exit Criteria

- every existing packet directory lives under `plans/YYYY-MM/DD-<slug>/`;
- future-work guidance points to `plans/YYYY-MM/DD-<slug>/`;
- `plans/open.md`, `plans/closed.md`, and README links resolve to the moved
  packets;
- repo-wide scans show no stale internal references to the old flat layout.
