# Plan: Entity Layer Ownership

Date: 2026-06-28
Closed: 2026-06-28
Status: Closed - implemented and proven

## Problem Summary

The repository has drifted between two correct but conflicting ideas:

- `plans/2026-06/07-knowledge-layers/` established the durable layer split:
  observed/generated evidence is lower, reviewed semantic meaning is upper.
- `plans/2026-06/11-repo-consolidation/` closed with `even` as
  private-repo-blind and put private Markdown/YAML knowledge in private Git.
  That boundary correctly kept real paths, source maps, personal labels, and
  curated notes out of the public repo.

The confusion is Layer 4. The consolidation survey already identified generic
Layer-4 catalog schemas as public capabilities, but the closed resolution also
said entities belonged to the private repo. That left standard entity catalogs
in no man's land: too structured for Markdown-only knowledge, but not owned by
the public catalog.

## Resolution

Adopt the maintainer decision from 2026-06-28:

```text
1 Sources
2 Evidence
3 Indexes
4 Entities
5 Knowledge
```

`evidence-engine` owns the standard mechanics through Layer 4:

- source discovery and source state;
- typed evidence extraction;
- rebuildable text/vector/routing indexes;
- generic entity catalog tables and review/task scaffolding.

Upper layers own what remains non-standard or private:

- real source maps and selected local/private paths;
- personal/domain-specific labels beyond generic classification slots;
- private Markdown knowledge, conventions, topic narratives, and handoff notes;
- custom workflows that do not belong in the reusable engine.

The revised rule is:

```text
even manages standard entity catalogs; upper layers curate knowledge and custom semantics.
```

This supersedes `plans/2026-06/11-repo-consolidation/plan.md` RD-006 only where
it excluded generic entity runtime ownership from `evidence-engine`. RD-004
still stands: `even` must remain blind to private repo path, Git state, OKF
layout, and private Markdown structure.

## Scope

In scope:

- rename public layer wording to Sources, Evidence, Indexes, Entities,
  Knowledge;
- update README and the stable CLI/catalog specification to clarify the new
  boundary;
- extend `catalog.yaml` with generic Layer-4 entity tables;
- bump the beta catalog schema/user version;
- add focused tests proving new catalogs include the entity tables;
- record implementation and proof in this plan packet.

Out of scope:

- entity CRUD CLI commands;
- private knowledge repository scaffolding;
- domain-specific tax, family, media, vehicle, medical, or housing schemas;
- committing real entity rows, private catalogs, source maps, or Markdown
  knowledge;
- migration support for old beta catalogs beyond existing wipe/rebuild.

## Milestones

1. Record the superseding ownership decision in this packet.
2. Rework public stack/layer language in README and the durable specification.
3. Add generic entity tables to the public catalog contract.
4. Bump schema version and add focused catalog tests.
5. Run proof and close the packet.

## Exit Criteria

- README uses the new layer names and does not say Layers 4-5 are both external.
- The durable specification says Layer 4 generic entity catalogs are engine
  owned, while private/custom semantics and Knowledge remain above the engine.
- `catalog.yaml` defines generic entity tables without real private data.
- New catalog creation reports the entity tables.
- `implementation.md` and `test.md` record the work and proof.
