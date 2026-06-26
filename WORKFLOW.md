# Workflow

This repository is spec-driven. It uses durable specifications for binding
contracts and dated plans for time-bounded implementation work.

This repository does not use repo-level `memory/`, `knowledge_base/`, or
`.cache/` workflow areas. Generated runtime data belongs under caller-provided
output paths or implementation-specific test fixtures, not in persistent
workflow folders.

## Spec Maintenance

Keep `specifications/` current as durable decisions emerge. Whenever the
maintainer states a strategy, policy, contract, or wisdom-level rule — or work
settles such a decision — fold it into the relevant spec in the same pass, not
just into a plan or a commit message. Plans are time-bounded and get abandoned
after implementation; the spec is what survives. Do not record case-level
implementation detail in the spec; capture the durable rule behind it.

## Read-Only Sources

Source files are read-only, always. The engine, tools, and tests must never
copy, move, rename, edit, or write to a source file or its folder. Pointing a
command at a source location is for reading only.

The only outputs are **derived** artifacts under the workspace cache
(`.cache/even/`): metadata rows, thumbnails/previews, embeddings, indexes, and
result files. Generating a small thumbnail from a source is fine; duplicating
the source is not — copies waste storage and break the read-only contract. When
a test needs sample media, read it in place from the user-provided path; do not
copy it into a fixture.

## Git Ownership

The maintainer owns all git operations. Assistants and tools must not run
`git add`, `git commit`, `git push`, branch, or any other history-changing git
command. Leave finished work in the working tree and let the maintainer review,
stage, and commit it.

## Areas

### `specifications/`

Use `specifications/` for durable requirements that constrain implementation
across more than one pass.

Create a specification under:

```text
specifications/<slug>/spec.md
```

Specifications contain timeless binding rules and contracts:

- CLI capabilities, command behavior, inputs, outputs, and exit semantics;
- JSON, JSONL, manifest, and schema contracts;
- identity, provenance, freshness, redaction, and error rules;
- storage layout rules that callers and implementations may rely on;
- accepted non-goals and unsupported behavior.

Specifications must not read like plans or history. Avoid wording such as
"planned", "future", "previously", or "we decided". Put implementation history
in `implementation.md` instead.

### `plans/`

Use `plans/` for dated planning packets tied to active work.

Each plan folder uses:

```text
plans/YYYY-MM-DD-<slug>/
  survey.md            # only when the maintainer explicitly requests one
  plan.md
  implementation.md    # created only after implementation work has happened
  test.md
```

Create `survey.md` only when the maintainer explicitly requests a survey. Do
not produce one as a default step; fold light discovery notes into `plan.md`
instead.

Two index files at the top of `plans/` track packet status: `closed.md` lists
completed packets with their proof, and `open.md` lists packets with work still
outstanding. Update these tables whenever a plan is finished or started so the
current state of all plans is visible at a glance.

## Plan Shape

`plan.md` must stay focused on the work package. It should contain:

- problem summary;
- resolution summary;
- goal and objectives;
- scope and non-goals;
- open points with resolution status;
- implementation phases;
- dependencies and risks;
- exit criteria.

Open points should be tracked across the discussion. Use stable IDs such as
`OP-001`, keep the current status visible, and record the resolution only when
the answer is accepted.

`plan.md` does not need detailed rewrites for every implementation deviation.
Once implementation starts, facts about what actually landed belong in
`implementation.md`.

## Implementation Log

Create `implementation.md` only once implementation work has actually
happened; it logs facts really implemented, never planned intent. A packet
that is still in planning or review has no `implementation.md`.

Every `implementation.md` opens with a **Progress** section — the first
section after the title — and it is updated on every change to the file. It is
a one-glance progress bar, not prose:

- one line with a bar of filled/empty blocks plus the current phase, e.g.
  `` `▰▰▰▱▱▱ Phase 3/6` ``, using the plan's own phase or milestone names;
- one short clause naming the phase in progress and what comes next;
- when the packet is fully implemented and proven, the bar is full and the
  line reads `Done`, e.g. `` `▰▰▰▰▰▰ Done` `` with a one-clause summary and any
  non-blocking follow-ups.

Keep the Progress section to two lines at most; the running detail belongs in
the log below. Use the rest of the file as the running trace of work:

- files changed;
- implementation facts;
- decisions made during development;
- deviations from the plan;
- follow-up risks;
- important commands or migrations.

The implementation log should describe what happened, not restate the whole
plan.

## Test Proof

Use `test.md` as proof of behavior:

- commands run;
- fixtures used;
- expected results;
- actual results;
- known gaps;
- environment or dependency notes that affect reproducibility.

For planning-only changes, `test.md` may record document review and consistency
checks instead of runtime proof.

## Scope Ownership

`even` owns reusable CLI implementation for manager repositories and
central skills. Central skills may wrap these commands and manage dependency
installation, but they do not own the SQL catalog, FTS indexing, semantic
indexing, search routing, schema migrations, or lower-index health behavior.

Manager repositories are customers. They pass source manifests, policy, and
output locations into this CLI and consume structured results.
