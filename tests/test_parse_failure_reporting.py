from __future__ import annotations

from io import StringIO

from agents_cli.cli import _ParseProgress
from agents_cli.parse import _classify_error
from agents_cli.results import render_html_report, render_summary_markdown


def test_classifies_pdf_password_errors() -> None:
    message = "Failed to load document (PDFium: Incorrect password error)."

    assert _classify_error("PdfiumError", message) == "pdf_password_required"


def test_classifies_native_memory_errors() -> None:
    assert _classify_error("RuntimeError", "std::bad_alloc") == (
        "resource_exhausted_memory"
    )


def test_parse_summary_and_html_include_failure_tables() -> None:
    payload = {
        "command": "parse folder",
        "status": "partial",
        "root_label": "sample",
        "parser_profile": "docling_ocr",
        "ocr_requested": True,
        "auto_scan_status": "ok",
        "result_uri": "results/2026.06/06/120102-parse-folder",
        "docling_runtime": {
            "docling_threads": 2,
            "pdf_batch_size": 1,
            "pdf_queue_max_size": 8,
        },
        "counts": {
            "documents_planned": 2,
            "documents_parsed": 1,
            "documents_partial": 0,
            "documents_failed": 1,
            "documents_unchanged": 0,
            "artifacts_written": 1,
            "objects_written": 1,
        },
        "failures": [
            {
                "relative_path": "locked.pdf",
                "error_kind": "pdf_password_required",
                "error_category": "input",
                "message": "Incorrect password error.",
                "suggested_action": "Provide an unlocked copy.",
            }
        ],
    }

    summary = render_summary_markdown(payload)
    report = render_html_report(payload, summary)

    assert "## Failure Details" in summary
    assert "locked.pdf" in summary
    assert "<h2>Failure Details</h2>" in report
    assert "pdf_password_required" in report


def test_parse_progress_prints_done_lines_for_noninteractive_stream() -> None:
    stream = StringIO()
    progress = _ParseProgress(stream, enabled=True)

    progress(
        {
            "event": "document_done",
            "index": 1,
            "total": 2,
            "status": "failed",
            "error_kind": "resource_exhausted_memory",
            "relative_path": "large.pdf",
        }
    )

    assert stream.getvalue() == (
        "parse [1/2] failed (resource_exhausted_memory): large.pdf\n"
    )

