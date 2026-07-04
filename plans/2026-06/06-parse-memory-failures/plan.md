# Plan

## Scope

- Add conservative Docling runtime defaults for local OCR parsing.
- Explicitly honor OCR/table settings for all configured PDF parser profiles.
- Classify conversion failures into actionable categories.
- Add failure detail tables to parse `summary.md` and parse `report.html`.
- Add concise document-level parse progress and quiet third-party logging by
  default.

## Milestones

1. Add parser runtime configuration and fallback defaults.
2. Update `parse_folder_to_catalog` to apply Docling backpressure and timeout
   options.
3. Add preflight and exception/result failure classification.
4. Render parse failure details in Markdown and HTML reports.
5. Add CLI progress and logging controls.
6. Add focused tests for reporting and classification.

## Exit Criteria

- `parse folder` result JSON includes effective runtime settings and structured
  failure records with suggested actions.
- `summary.md` includes a failure details table when parse failures exist.
- `--report` parse output includes an HTML failure table.
- `docling_fast_text` explicitly disables OCR and table structure.
- Tests pass for changed reporting and classification behavior.

