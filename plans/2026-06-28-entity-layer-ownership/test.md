# Test Proof: Entity Layer Ownership

## Commands

| Command | Result |
| --- | --- |
| `$env:UV_CACHE_DIR='.cache\uv'; uv run python -c "from even.catalog import load_catalog_tables; tables=load_catalog_tables(); print(len(tables)); print([t.name for t in tables[-7:]])"` | Pass - loaded 28 tables; final seven are the entity-layer tables. |
| `$env:UV_CACHE_DIR='.cache\uv'; uv run pytest tests\test_catalog_schema.py --basetemp .tmp\pytest -p no:cacheprovider` | Pass - 2 passed. |
| `$env:UV_CACHE_DIR='.cache\uv'; uv run pytest --basetemp .tmp\pytest -p no:cacheprovider` | Pass - 58 passed, 13 skipped, 13 warnings. |
| `$env:UV_CACHE_DIR='.cache\uv'; uv run ruff check .` | Pass - all checks passed. |
| `rg -n "Source authority|Search projections|Reviewed facts|Curated knowledge|Layers 4|layers 4|Layer 4.*Reviewed|private semantic facts|private review decisions" README.md specifications\corpus-cache-cli\spec.md catalog.yaml plans\2026-06-28-entity-layer-ownership plans\2026-06-11-repo-consolidation\plan.md plans\closed.md plans\open.md` | Pass - no active-doc contradictions; only this packet's exit criterion wording remained before close. |

## Expected Results

- New catalog schema exposes standard entity tables: pass.
- Focused tests pass: pass.
- Documentation no longer describes Entities as a private-repo-only layer: pass.

## Gaps

- Entity CRUD/import/review/export commands are not implemented in this packet.
- The first pytest attempt failed before test execution because pytest tried to
  use `C:\Users\wassi\AppData\Local\Temp\pytest-of-wassi`, which is not
  accessible in this environment. Rerunning with `--basetemp .tmp\pytest`
  produced valid proof.
- The first `uv run` attempt used the user-level uv cache and failed with an
  access-denied error. Rerunning with `UV_CACHE_DIR=.cache\uv` produced valid
  proof.
