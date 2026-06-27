# Plan: Repository Consolidation

Date: 2026-06-11
Closed: 2026-06-27
Status: Closed - planning decision settled, doc-only
Inputs: [survey.md](./survey.md)

## Problem Summary

Three repositories carried one system. `evidence-engine` held the reusable code
and lower generated-data machinery. The old private document/media repositories
held private source maps, stale `agents-docs` planning material, and generic
upper-layer schema ideas. The open question was whether `even` should own a
private curated-data layer, or whether private curation should live outside the
public engine.

The maintainer decision is now explicit: `even` should be friendly to private
knowledge workflows, but should not know about or interact with any private
knowledge repository.

## Resolution

Use three boundaries:

```text
evidence-engine
  Public, reusable engine. Owns source discovery, parsing, indexing, search,
  provenance, and generic export surfaces.

private knowledge repo
  Private Git repository. Owns curated Markdown/YAML knowledge, source maps,
  source-scope decisions, personal labels, entities, decisions, and local
  workflow scripts. OKF-compatible structure is allowed and preferred where it
  costs little.

source authorities and cache
  OneDrive, Google Drive, Gmail, and local folders remain raw source
  authorities. `.cache/even/` remains generated machine state: catalogs,
  indexes, embeddings, parse artifacts, and run reports.
```

The concise rule is:

```text
even produces evidence surfaces; the private repo produces judgment.
```

## Resolved Decisions

| ID | Decision |
| --- | --- |
| RD-001 | The private curated knowledge base will live in private Git, not only in OneDrive or Google Docs. |
| RD-002 | Curated private data is Markdown/YAML only by default. Generated databases, indexes, embeddings, thumbnails, OCR output, parse artifacts, and caches are not versioned. |
| RD-003 | The private repo may use an OKF-compatible convention: Markdown concept files with YAML frontmatter, `index.md` navigation, and optional `log.md`. This is a format convention, not a claim of public openness. |
| RD-004 | `even` must remain private-repo-blind. It must not know the private repo path, layout, taxonomy, Git state, or OKF structure. |
| RD-005 | `even` should expose generic structured outputs that private workflows can consume: stable IDs, source provenance, command JSON/JSONL, search/export records, and status reports. |
| RD-006 | Private source maps, labels, entities, decisions, and topic curation belong to the private repo or its local scripts, not to public `evidence-engine` runtime ownership. |
| RD-007 | Old private repositories should stay private permanently because their history may contain personal paths or other private facts. They can be archived after useful generic ideas are recorded. |

## Scope

This closed packet records the ownership boundary and closes the consolidation
decision. It does not implement runtime code.

In scope for this packet:

- settle the public/private ownership model;
- define the private Git plus Markdown/YAML direction;
- clarify that `even` is private-knowledge-friendly but private-repo-blind;
- preserve which old private-repo ideas remain useful.

Out of scope for this packet:

- implementing new `even` commands;
- creating or modifying the private Git repository;
- moving private files;
- archiving GitHub repositories;
- adding a durable private `knowledge.sqlite` owned by `even`;
- validating OKF files;
- committing generated private data.

## Useful Material From The Old Private Repos

The old `documents-manager` material is useful as design evidence, but should
not be merged wholesale.

Useful concepts:

- source authorities are read-only by default;
- generated index/cache data is disposable and rebuildable;
- curated human knowledge is durable;
- provenance must point back to exact source paths or URIs;
- lower reusable tools should not mutate private curated state;
- topic-specific workflows should consume evidence/results instead of owning
  generic crawling and indexing.

Material that should not move into `evidence-engine`:

- real source maps and personal paths;
- private config files with selected local folders;
- stale `agents-docs` references;
- private catalog databases;
- personal labels, private entities, or topic-specific curation.

## `even` Contract Direction

`even` should provide generic, reusable surfaces:

- stable source/item/artifact IDs;
- source path or URI provenance;
- parse/index/search status reports;
- structured JSON or JSONL command output;
- search result exports with enough provenance for downstream curation;
- redaction-safe diagnostics where possible.

`even` should not provide or assume:

- a private knowledge repository location;
- private Git operations;
- personal taxonomies;
- private entity schemas as runtime ownership;
- OKF validation or private Markdown rendering;
- domain-specific workflows such as tax, housing, vehicle, medical, media, or
  family curation.

If current command outputs are insufficient, open a future implementation plan
for a generic export contract. That follow-up should remain private-repo-blind.

## Private Knowledge Repo Direction

The private repo owns curated judgment and may call `even` as a tool:

```text
even sources scan ...
even docs parse ...
even search ...
local private script transforms JSON/JSONL into reviewed Markdown/YAML
git diff / review / commit in the private repo
```

Suggested private repo shape:

```text
private-knowledge/
  index.md
  log.md
  sources/
  topics/
  entities/
  decisions/
  config/
```

This structure is intentionally outside `evidence-engine`. It is recorded here
only to explain the boundary.

## Follow-Up Work

Future packets may cover:

- generic `even` export contracts if current JSON/JSONL output is not enough;
- public documentation improvements about source authority, generated cache,
  and private curation boundaries;
- private-repo scaffolding outside this workspace;
- archival of old private repositories after the maintainer prepares pointer
  READMEs and confirms they remain private.

## Exit Criteria

This packet is closed when:

1. the public/private ownership boundary is documented;
2. `plans/open.md` and `plans/closed.md` reflect closure;
3. [implementation.md](./implementation.md) records the doc-only update;
4. [test.md](./test.md) records review proof and confirms no code/runtime work
   was performed.
