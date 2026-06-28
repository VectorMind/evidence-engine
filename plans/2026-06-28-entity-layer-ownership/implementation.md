# Implementation: Entity Layer Ownership

## Progress

`▰▰▰▰ Done` - public layer naming and generic entity catalog ownership are
implemented and proven.

## Changes Made

- Created this plan packet to supersede the ambiguous part of
  `2026-06-11-repo-consolidation` while preserving the private-repo-blind
  boundary.
- Reworked README stack language to:
  `Sources -> Evidence -> Indexes -> Entities -> Knowledge`.
- Updated the public/private split so the public repo owns generic entity
  schemas and helpers, while real entity rows, custom domain schemas, and
  private Knowledge Markdown stay private/generated.
- Updated `specifications/corpus-cache-cli/spec.md` so the stable contract says
  the engine owns Sources, Evidence, Indexes, and generic Entities.
- Extended `catalog.yaml` with generic Layer-4 tables:
  `entities`, `entity_aliases`, `entity_evidence_links`,
  `entity_classifications`, `entity_attributes`, `entity_relationships`, and
  `review_tasks`.
- Bumped the beta catalog schema from `0.9` / `user_version=9` to `0.10` /
  `user_version=10`.
- Added focused catalog schema tests and adjusted the routing catalog contract
  test for the new user version.
- Added a supersession note to `plans/2026-06-11-repo-consolidation/plan.md`.

## Decisions

- `even` manages standard entity catalogs.
- Upper layers still own private Knowledge, custom semantics, source maps,
  private paths, and domain-specific workflows.
- Old beta catalogs are expected to wipe/rebuild after this schema bump.

## Follow-Up Risks

- No entity CRUD CLI exists yet. The catalog can create and report the tables,
  but workflow commands for proposing, importing, reviewing, or exporting
  entity rows need a later packet.
- `evidence_ref` is a flexible catalog coordinate string. That keeps cross-table
  links generic, but validation helpers may be useful later.
