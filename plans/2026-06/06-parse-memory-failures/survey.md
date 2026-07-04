# Survey

## Context

The observed `parse folder` run used the default `docling_ocr` profile on 107
documents. It completed with partial status: 99 parsed and 8 failed. The noisy
terminal output included PDFium password errors and repeated Docling threaded
pipeline `std::bad_alloc` page-preprocess failures.

## Local Findings

- The CLI parses documents sequentially at the Python loop level.
- Docling's PDF pipeline is internally threaded and uses per-stage queues.
- Installed Docling exposes memory-relevant options:
  - `document_timeout`
  - `accelerator_options.num_threads`
  - `ocr_batch_size`
  - `layout_batch_size`
  - `table_batch_size`
  - `queue_max_size`
  - `images_scale`
- The current CLI does not set those options, so the OCR profile uses Docling
  defaults: batch sizes of 4 and queue size of 100.
- `docling_fast_text` currently reports `ocr_requested: false`, but the parser
  does not explicitly pass PDF options for the non-OCR profile.
- Parse summaries currently group failures by error kind only. HTML reports are
  generic inventory reports and do not include parse failure detail tables.

## Diagnosis

The memory failures are caused by a heavy OCR/layout/table pipeline buffering or
processing too many page-level objects for large PDFs. Windows is not the root
cause, but local Windows laptop memory pressure makes the native allocation
failure surface as `std::bad_alloc`.

Password-protected PDFs are a separate input failure and should be detected and
reported before Docling emits a traceback.

