# Implementation

## Changes

- Added `parser_runtime` defaults in `config/parser.yaml`:
  - 300 second per-document timeout;
  - 2 Docling CPU threads;
  - PDF OCR/layout/table batch size 1;
  - PDF stage queue size 8;
  - image scale 1.0.
- Added fallback parsing for those runtime defaults in `agents_cli.config`.
- Updated parser construction to always pass explicit PDF pipeline options, so
  `docling_fast_text` now actually disables OCR and table structure.
- Added runtime override fields to `ParseOptions` and CLI flags:
  `--document-timeout`, `--max-pages`, `--max-file-size`,
  `--docling-threads`, `--batch-size`, and `--queue-size`.
- Added a PDF preflight step using `pypdfium2` when available. It catches
  password/open failures and configured page/file safeguards before the heavier
  Docling conversion starts.
- Switched document conversion to `raises_on_error=False` so Docling failure and
  partial-success statuses can be recorded in structured results.
- Added failure classification for password-protected PDFs, native memory
  exhaustion, timeouts, size/page safeguards, invalid inputs, skipped documents,
  and generic Docling conversion failures.
- Added `documents_partial`, `partial_documents`, and failure truncation metadata
  to parse results.
- Added parse-specific `summary.md` failure detail and partial-document tables.
- Added parse-specific HTML reports with overview, Docling runtime, failure
  summary, failure details, and partial-document sections.
- Added document-level CLI parse progress on stderr with `--progress`,
  `--no-progress`, and quiet third-party parser logging by default. `--verbose`
  restores third-party parser logs.
- Converter stdout/stderr is suppressed by default to hide model/progress noise
  from dependencies; `--verbose` disables that suppression.
- Updated README and the durable CLI spec for the new parse behavior.
- Removed an unused import in `catalog.py` that blocked project-wide Ruff.

## Decisions

- Keep document-level parsing sequential. The risk was Docling's internal
  page/stage concurrency and queue buffering, not a parallel Python document
  loop.
- Do not default to a page-count cap because that silently drops content. Page
  and file caps are available only as explicit CLI overrides.
- Treat Docling partial success as an overall `partial` run status while still
  writing the available artifact.
