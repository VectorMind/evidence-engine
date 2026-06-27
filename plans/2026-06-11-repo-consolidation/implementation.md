# Implementation: Repository Consolidation

## Progress

`██████████` Done

## Changes Made

- Closed the packet as a planning-only decision on 2026-06-27.
- Rewrote [plan.md](./plan.md) around the accepted boundary:
  `even` produces generic evidence surfaces, while a private Git repository
  owns curated Markdown/YAML judgment.
- Resolved the private knowledge location as private Git, with
  OKF-compatible Markdown/YAML allowed as a lightweight convention.
- Removed the earlier implication that `even` should own or implement a durable
  private knowledge database.
- Recorded that old private repository material is useful as design evidence
  only; private paths, config, labels, entities, and curation stay outside
  public `evidence-engine`.
- Updated [test.md](./test.md) with doc-only proof and remaining gaps.
- Moved the packet from `plans/open.md` to `plans/closed.md`.

## Decisions

- `even` is private-knowledge-friendly but private-repo-blind.
- Private curated data is versioned as Markdown/YAML in private Git.
- OneDrive, Google Drive, Gmail, and local folders are source authorities, not
  curated-output targets.
- `.cache/even/` remains generated machine state and is not versioned.
- Any future code work should be a separate generic export-contract plan.

## Follow-Up Risks

- Current `even` command outputs may need stronger JSON/JSONL export contracts
  for private workflows. That is intentionally deferred to a future packet.
- Old private repositories must remain private if archived, because history may
  contain personal facts.
