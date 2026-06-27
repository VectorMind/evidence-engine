# Image Search Cache Isolation

## Scope

Fix the observed `search image` degradation caused by synthetic pytest image
stores being visible to a real catalog.

## Milestones

- Make pytest cache/home isolation fail closed so tests cannot write to a real
  `EVEN_CACHE` or `EVEN_HOME` by accident.
- Harden image union search so stores with incompatible vector dimensions are
  skipped before LanceDB search.
- Clarify the README text-to-image CLI example.
- Clean the known polluted live catalog after code fixes are in place.

## Dependencies

- Existing `even.paths` cache resolution remains unchanged for runtime behavior.
- Tests that intentionally exercise `EVEN_CACHE`, `EVEN_HOME`, or `.env`
  override behavior may still set those values explicitly.

## Exit Criteria

- Focused pytest coverage passes for CLI path contracts and image search.
- A regression test proves incompatible image stores are skipped, not counted as
  search failures.
- README shows the correct `search image --text` argument shape.
- The live polluted catalog is cleaned or the remaining cleanup gap is recorded.
