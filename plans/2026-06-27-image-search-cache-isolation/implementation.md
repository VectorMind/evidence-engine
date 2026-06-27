# Implementation

## Progress

Done.

## Changes

- Updated the autouse pytest fixture to run every test from `tmp_path` and set
  temp-local `EVEN_CACHE` and `EVEN_HOME`, closing the repository `.env`
  override gap.
- Updated `search image` to skip unsupported profiles, profile mismatches,
  vector-dimension mismatches, and unavailable LanceDB image stores before
  querying compatible stores.
- Clarified the README image-search CLI surface and examples.
- Added regression coverage for temp-local pytest paths and incompatible image
  store skipping.

## Verification

- `uv run pytest tests/test_cli_contract.py tests/test_image_search.py -q`
  passed with 14 tests.
- `uv run pytest -q` passed with 69 tests.
- `uv run ruff check .` passed.

## Live Cleanup

- Backed up `C:\Users\wassi\.even\catalog\catalog.sqlite` to
  `C:\Users\wassi\.even\catalog\catalog.sqlite.bak-20260627T161619Z`.
- Deleted the seven explicitly approved incompatible `siglip2_base` image-store
  rows.
- Removed their seven matching `.lancedb` directories under
  `C:\Users\wassi\.even\semantic\image\siglip2_base`.
- Verified the live catalog now has one remaining `siglip2_base` image store,
  with `vector_dimension = 768`, and zero incompatible `siglip2_base` rows.
