# Test Proof: Entity Layer Runtime And Reference Example

Status: Not started — plan is open, no implementation yet.

## Planned Proof

To be executed and recorded here as milestones land:

1. Unit tests: `uv run pytest tests/test_entities.py` (temp catalog CRUD,
   review-state transitions, ref validation).
2. CLI contract: `even entity add/list/show/alias/link/review/find` JSON
   outputs against a temp `EVEN_CACHE`.
3. Worked reference example from a clean cache:
   `catalog create` → `sources scan` → `docs parse` → `media inspect` →
   `index scope [--image]` → `index routing` → `entity add/alias` →
   `entity find [--image]` → `entity link` → `entity review` → `entity show`.
4. Durability check: re-run `docs parse` / `index scope` / `index routing`
   over the fixture and diff entity/link/task rows — must be unchanged.

Each step records the command run, expected result, actual result, and gaps.
