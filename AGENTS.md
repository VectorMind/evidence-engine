# Agent Guidance

## Spec And Planning Workflow

Use `specifications/` for stable, spec-driven requirements and `plans/` for
time-bounded planning packets.

- Store durable specifications under `specifications/<slug>/spec.md` when the
  work needs requirements that should outlive one implementation pass.
- Store planning work under `plans/YYYY-MM/DD-<slug>/`. Use a `YYYY-MM` month
  folder plus a `DD-<slug>` packet folder, where `DD` is the two-digit day the
  plan packet starts and `<slug>` is a short lowercase title.
- Every dated plan folder must contain `plan.md` and `test.md`.
- Create `implementation.md` only after implementation work has actually
  happened, to log facts really implemented. Never create it upfront as a
  stub during planning.
- Add `survey.md` only when the maintainer explicitly asks for a survey, not
  as a default step before planning.
- Keep `plan.md` focused on approved scope, milestones, dependencies, and exit
  criteria. Do not turn unreviewed survey notes into committed scope.
- Keep `implementation.md` as a running log of changes made, important
  decisions, deviations from the plan, and follow-up risks. Open it with a
  short **Progress** section (a filled/empty-block bar plus current phase, or
  `Done` when finished) and keep that bar current on every change.
- Keep `test.md` as proof of working behavior: commands run, fixtures used,
  expected and actual results, and any gaps that remain untested.

When a plan changes during implementation, update the packet folder so the
spec, plan, implementation notes, and test proof remain consistent.
