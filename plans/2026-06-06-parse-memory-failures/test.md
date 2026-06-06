# Test

## Commands

- `uv run pytest`
  - Expected: focused tests pass.
  - Actual: 4 passed.

- `uv run ruff check src tests`
  - Expected: no Ruff findings.
  - Actual before cleanup: failed on an unused `fixed_cache_root` import in
    `catalog.py`.
  - Actual after cleanup: all checks passed.

- `uv run python -m agents_cli.cli parse folder tests\fixtures\parse-basic --profile docling_fast_text --limit 1 --report --no-progress`
  - Expected: fixture parses, report is written, runtime defaults are recorded.
  - Actual: status `ok`, parsed `1/1`, report written to
    `reports/2026.06/06/151317-parse-folder/report.html`.
  - Re-run after final suppression update returned status `ok`, unchanged
    `1/1`, and wrote `results/2026.06/06/151639-parse-folder/result.json`.

## Verified Outputs

- Generated result JSON included:
  - `docling_runtime.docling_threads: 2`
  - `docling_runtime.pdf_batch_size: 1`
  - `docling_runtime.pdf_queue_max_size: 8`
  - `docling_runtime.suppress_converter_output: true`
  - `counts.documents_partial: 0`
- Generated `summary.md` included `Partial documents` in the overview.
- Generated `report.html` included `Docling Runtime`, `Failure Details`, and
  `Partial Documents` sections.
