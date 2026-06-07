"""Docling-backed folder parsing."""

from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import importlib
import io
import json
from pathlib import Path
import sqlite3
from typing import Any, Callable

from coev.blobs import store_artifact_blob
from coev.config import load_parser_config
from coev.inventory import ScanOptions, scan_folder_to_catalog
from coev.paths import catalog_path


FAILURE_RESULT_LIMIT = 100
ProgressCallback = Callable[[dict[str, Any]], None]


@dataclass(frozen=True)
class ParseOptions:
    profile: str | None
    limit: int | None
    progress: ProgressCallback | None = None
    document_timeout: float | None = None
    max_pages: int | None = None
    max_file_size: int | None = None
    docling_threads: int | None = None
    queue_size: int | None = None
    batch_size: int | None = None
    suppress_converter_output: bool = True


def parse_folder_to_catalog(path: Path, options: ParseOptions) -> dict[str, Any]:
    """Auto-scan a folder and parse current source files through Docling."""

    config = load_parser_config()
    profile_name = options.profile or config["defaults"].get(
        "parser_profile", "docling_ocr"
    )
    profile = _profile(config, profile_name)
    if profile is None:
        return {
            "status": "failed",
            "error_kind": "unknown_parser_profile",
            "parser_profile": profile_name,
        }
    runtime = _runtime_options(config, options)

    docling_status = _docling_runtime_status()
    if docling_status["status"] != "ok":
        scan_result = scan_folder_to_catalog(
            path,
            ScanOptions(max_files=None, max_bytes=None, max_depth=None),
        )
        payload = {
            "status": "failed",
            "error_kind": docling_status["error_kind"],
            "parser_profile": profile_name,
            "auto_scan_status": scan_result.get("status"),
            "message": docling_status["message"],
        }
        if "root_id" in scan_result:
            payload["root_id"] = scan_result["root_id"]
            payload["root_label"] = scan_result.get("root_label")
            payload["scope_id"] = scan_result.get("scope_id")
        return payload

    scan_result = scan_folder_to_catalog(
        path,
        ScanOptions(max_files=None, max_bytes=None, max_depth=None),
    )
    if scan_result["status"] != "ok":
        return {
            "status": scan_result["status"],
            "error_kind": "auto_scan_failed",
            "parser_profile": profile_name,
            "auto_scan_status": scan_result["status"],
            "scan_result": scan_result,
        }

    root_id = scan_result["root_id"]
    source_items = _source_items_for_root(root_id, options.limit)
    if not source_items:
        return {
            "status": "ok",
            "parser_profile": profile_name,
            "docling_runtime": runtime,
            "root_id": root_id,
            "root_label": scan_result.get("root_label"),
            "scope_id": scan_result.get("scope_id"),
            "auto_scan_status": scan_result["status"],
            "counts": {
                "documents_planned": 0,
                "documents_parsed": 0,
                "documents_failed": 0,
                "documents_unchanged": 0,
            },
        }

    converter_report = _build_converter(profile, runtime)
    if converter_report["status"] != "ok":
        return {
            "status": "failed",
            "error_kind": converter_report["error_kind"],
            "parser_profile": profile_name,
            "docling_runtime": runtime,
            "root_id": root_id,
            "root_label": scan_result.get("root_label"),
            "scope_id": scan_result.get("scope_id"),
            "message": converter_report["message"],
        }

    now = _iso(_utc_now())
    counts = {
        "documents_planned": len(source_items),
        "documents_parsed": 0,
        "documents_partial": 0,
        "documents_failed": 0,
        "documents_unchanged": 0,
        "artifacts_written": 0,
        "objects_written": 0,
    }
    failures: list[dict[str, Any]] = []
    partials: list[dict[str, Any]] = []

    _progress(
        options.progress,
        {"event": "planned", "total": len(source_items), "profile": profile_name},
    )
    for index, item in enumerate(source_items, start=1):
        _progress(
            options.progress,
            {
                "event": "document_start",
                "index": index,
                "total": len(source_items),
                "relative_path": item["relative_path"],
            },
        )
        parsed = _parse_one(
            item,
            converter_report["converter"],
            parser_profile=profile_name,
            runtime=runtime,
            now=now,
        )
        if parsed["status"] == "parsed":
            counts["documents_parsed"] += 1
            if parsed.get("docling_status") == "partial_success":
                counts["documents_partial"] += 1
                partials.append(parsed)
            counts["artifacts_written"] += parsed["artifact_count"]
            counts["objects_written"] += parsed["object_count"]
        elif parsed["status"] == "unchanged":
            counts["documents_unchanged"] += 1
        else:
            counts["documents_failed"] += 1
            failures.append(parsed)
        _progress(
            options.progress,
            {
                "event": "document_done",
                "index": index,
                "total": len(source_items),
                "relative_path": item["relative_path"],
                "status": parsed["status"],
                "error_kind": parsed.get("error_kind"),
                "docling_status": parsed.get("docling_status"),
            },
        )

    status = (
        "ok"
        if counts["documents_failed"] == 0 and counts["documents_partial"] == 0
        else "partial"
    )
    visible_failures = failures[:FAILURE_RESULT_LIMIT]
    visible_partials = partials[:FAILURE_RESULT_LIMIT]
    return {
        "status": status,
        "parser_profile": profile_name,
        "docling_runtime": runtime,
        "root_id": root_id,
        "root_label": scan_result.get("root_label"),
        "scope_id": scan_result.get("scope_id"),
        "source_uri_redacted": True,
        "auto_scan_status": scan_result["status"],
        "ocr_requested": bool(profile.get("ocr", False)),
        "counts": counts,
        "failures": visible_failures,
        "partial_documents": visible_partials,
        "failure_count_total": len(failures),
        "failure_count_returned": len(visible_failures),
        "failures_truncated": len(failures) > len(visible_failures),
        "partial_count_total": len(partials),
        "partial_count_returned": len(visible_partials),
        "partials_truncated": len(partials) > len(visible_partials),
    }


def _docling_runtime_status() -> dict[str, str]:
    try:
        importlib.import_module("docling.document_converter")
    except ModuleNotFoundError:
        return {
            "status": "failed",
            "error_kind": "docling_missing",
            "message": "Install the docling extra before running parse commands.",
        }
    return {"status": "ok"}


def _build_converter(profile: dict[str, Any], runtime: dict[str, Any]) -> dict[str, Any]:
    try:
        from docling.document_converter import DocumentConverter
    except ModuleNotFoundError:
        return {
            "status": "failed",
            "error_kind": "docling_missing",
            "message": "Install the docling extra before running parse commands.",
        }

    try:
        from docling.datamodel.accelerator_options import AcceleratorOptions
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import PdfPipelineOptions
        from docling.document_converter import PdfFormatOption

        pipeline_options = PdfPipelineOptions()
        ocr_setting = profile.get("ocr", False)
        if isinstance(ocr_setting, bool):
            pipeline_options.do_ocr = ocr_setting
        pipeline_options.do_table_structure = bool(profile.get("table_structure", True))
        if runtime.get("document_timeout_seconds") is not None:
            pipeline_options.document_timeout = float(
                runtime["document_timeout_seconds"]
            )
        if runtime.get("docling_threads") is not None:
            pipeline_options.accelerator_options = AcceleratorOptions(
                num_threads=int(runtime["docling_threads"])
            )
        if runtime.get("pdf_batch_size") is not None:
            batch_size = int(runtime["pdf_batch_size"])
            pipeline_options.ocr_batch_size = batch_size
            pipeline_options.layout_batch_size = batch_size
            pipeline_options.table_batch_size = batch_size
        if runtime.get("pdf_queue_max_size") is not None:
            pipeline_options.queue_max_size = int(runtime["pdf_queue_max_size"])
        if runtime.get("images_scale") is not None:
            pipeline_options.images_scale = float(runtime["images_scale"])

        converter = DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)
            }
        )
        return {"status": "ok", "converter": converter}
    except Exception as exc:
        return {
            "status": "failed",
            "error_kind": "docling_converter_failed",
            "message": f"Could not initialize Docling converter: {exc.__class__.__name__}",
        }


def _runtime_options(config: dict[str, Any], options: ParseOptions) -> dict[str, Any]:
    runtime = config.get("parser_runtime", {})
    return {
        "document_timeout_seconds": _float_or_none(
            options.document_timeout
            if options.document_timeout is not None
            else runtime.get("document_timeout_seconds_default")
        ),
        "max_num_pages": _int_or_none(
            options.max_pages
            if options.max_pages is not None
            else runtime.get("max_num_pages_default")
        ),
        "max_file_size_bytes": _int_or_none(
            options.max_file_size
            if options.max_file_size is not None
            else runtime.get("max_file_size_bytes_default")
        ),
        "docling_threads": _int_or_none(
            options.docling_threads
            if options.docling_threads is not None
            else runtime.get("docling_threads_default")
        ),
        "pdf_batch_size": _int_or_none(
            options.batch_size
            if options.batch_size is not None
            else runtime.get("pdf_batch_size_default")
        ),
        "pdf_queue_max_size": _int_or_none(
            options.queue_size
            if options.queue_size is not None
            else runtime.get("pdf_queue_max_size_default")
        ),
        "images_scale": _float_or_none(runtime.get("images_scale_default")),
        "suppress_converter_output": bool(options.suppress_converter_output),
    }


def _progress(callback: ProgressCallback | None, event: dict[str, Any]) -> None:
    if callback is None:
        return
    callback(event)


def _parse_one(
    item: dict[str, Any],
    converter: Any,
    *,
    parser_profile: str,
    runtime: dict[str, Any],
    now: str,
) -> dict[str, Any]:
    source_item_id = item["source_item_id"]
    doc_id = _stable_id("doc", source_item_id)
    source_sha256 = item["source_sha256"]
    existing = _document_state(doc_id)
    if (
        existing
        and existing["source_sha256"] == source_sha256
        and existing["parser_profile"] == parser_profile
        and existing["parse_status"] == "parsed"
    ):
        return {"status": "unchanged", "doc_id": doc_id}

    preflight = _preflight_source(item, runtime)
    if preflight["status"] == "failed":
        _mark_document_failed(
            source_item_id=source_item_id,
            doc_id=doc_id,
            source_sha256=source_sha256,
            parser_profile=parser_profile,
            title=Path(item["relative_path"]).name,
            now=now,
        )
        return _failure_payload(
            item=item,
            doc_id=doc_id,
            error_kind=preflight["error_kind"],
            redacted_detail=preflight.get("redacted_detail", "preflight_failed"),
            message=preflight.get("message", ""),
            page_count=preflight.get("page_count"),
        )

    try:
        convert_kwargs: dict[str, Any] = {"raises_on_error": False}
        if runtime.get("max_num_pages") is not None:
            convert_kwargs["max_num_pages"] = int(runtime["max_num_pages"])
        if runtime.get("max_file_size_bytes") is not None:
            convert_kwargs["max_file_size"] = int(runtime["max_file_size_bytes"])

        if runtime.get("suppress_converter_output", True):
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                result = converter.convert(item["source_uri"], **convert_kwargs)
        else:
            result = converter.convert(item["source_uri"], **convert_kwargs)
        docling_status = _status_value(getattr(result, "status", None))
        if docling_status in {"failure", "skipped"} or getattr(
            result, "document", None
        ) is None:
            failure = _failure_from_result(item=item, doc_id=doc_id, result=result)
            _mark_document_failed(
                source_item_id=source_item_id,
                doc_id=doc_id,
                source_sha256=source_sha256,
                parser_profile=parser_profile,
                title=Path(item["relative_path"]).name,
                now=now,
            )
            return failure

        document = result.document
        doc_json = _document_json(document)
        payload = json.dumps(doc_json, ensure_ascii=False, sort_keys=True).encode(
            "utf-8"
        )
        text_preview = _document_preview(document)
        title = _document_title(document, item)
        object_count = _write_parsed_document(
            source_item_id=source_item_id,
            doc_id=doc_id,
            source_sha256=source_sha256,
            parser_profile=parser_profile,
            title=title,
            text_preview=text_preview,
            payload=payload,
            now=now,
        )
    except Exception as exc:
        _mark_document_failed(
            source_item_id=source_item_id,
            doc_id=doc_id,
            source_sha256=source_sha256,
            parser_profile=parser_profile,
            title=Path(item["relative_path"]).name,
            now=now,
        )
        return _failure_from_exception(item=item, doc_id=doc_id, exc=exc)

    return {
        "status": "parsed",
        "doc_id": doc_id,
        "artifact_count": 1,
        "object_count": object_count,
        "docling_status": docling_status,
        "relative_path": item["relative_path"],
        "warnings": _conversion_errors(result, item)[:5],
    }


def _preflight_source(
    item: dict[str, Any], runtime: dict[str, Any]
) -> dict[str, Any]:
    size_bytes = item.get("size_bytes")
    max_file_size = runtime.get("max_file_size_bytes")
    if (
        max_file_size is not None
        and size_bytes is not None
        and int(size_bytes) > int(max_file_size)
    ):
        return {
            "status": "failed",
            "error_kind": "document_too_large",
            "redacted_detail": "max_file_size",
            "message": (
                f"File is {_format_count(size_bytes)} bytes; configured limit is "
                f"{_format_count(max_file_size)} bytes."
            ),
        }

    if not _is_pdf_source(item):
        return {"status": "ok"}

    try:
        import pypdfium2 as pdfium  # type: ignore[import-not-found]
    except ModuleNotFoundError:
        return {"status": "ok"}

    pdf_doc = None
    try:
        pdf_doc = pdfium.PdfDocument(item["source_uri"])
        page_count = len(pdf_doc)
    except Exception as exc:
        return _preflight_failure_from_exception(item=item, exc=exc)
    finally:
        close = getattr(pdf_doc, "close", None)
        if close is not None:
            close()

    max_pages = runtime.get("max_num_pages")
    if max_pages is not None and page_count > int(max_pages):
        return {
            "status": "failed",
            "error_kind": "document_too_many_pages",
            "redacted_detail": "max_num_pages",
            "message": (
                f"PDF has {page_count} pages; configured limit is {int(max_pages)}."
            ),
            "page_count": page_count,
        }
    return {"status": "ok", "page_count": page_count}


def _preflight_failure_from_exception(
    *, item: dict[str, Any], exc: Exception
) -> dict[str, Any]:
    message = _sanitize_message(str(exc), item)
    return {
        "status": "failed",
        "error_kind": _classify_error(exc.__class__.__name__, message),
        "redacted_detail": exc.__class__.__name__,
        "message": message,
    }


def _failure_from_result(
    *, item: dict[str, Any], doc_id: str, result: Any
) -> dict[str, Any]:
    docling_status = _status_value(getattr(result, "status", None))
    errors = _conversion_errors(result, item)
    message = errors[0] if errors else f"Docling returned status {docling_status}."
    payload = _failure_payload(
        item=item,
        doc_id=doc_id,
        error_kind=_classify_error(docling_status, message),
        redacted_detail=f"ConversionStatus.{docling_status}",
        message=message,
        page_count=_result_page_count(result),
        docling_status=docling_status,
    )
    if errors:
        payload["docling_errors"] = errors[:5]
    return payload


def _failure_from_exception(
    *, item: dict[str, Any], doc_id: str, exc: Exception
) -> dict[str, Any]:
    message = _sanitize_message(str(exc), item)
    return _failure_payload(
        item=item,
        doc_id=doc_id,
        error_kind=_classify_error(exc.__class__.__name__, message),
        redacted_detail=exc.__class__.__name__,
        message=message,
    )


def _failure_payload(
    *,
    item: dict[str, Any],
    doc_id: str,
    error_kind: str,
    redacted_detail: str,
    message: str,
    page_count: int | None = None,
    docling_status: str | None = None,
) -> dict[str, Any]:
    classification = _failure_classification(error_kind)
    payload: dict[str, Any] = {
        "status": "failed",
        "doc_id": doc_id,
        "source_item_id": item["source_item_id"],
        "relative_path": item["relative_path"],
        "size_bytes": item.get("size_bytes"),
        "error_kind": error_kind,
        "error_category": classification["category"],
        "redacted_detail": redacted_detail,
        "message": message or classification["diagnosis"],
        "diagnosis": classification["diagnosis"],
        "suggested_action": classification["suggested_action"],
    }
    if page_count is not None:
        payload["page_count"] = page_count
    if docling_status is not None:
        payload["docling_status"] = docling_status
    if classification.get("retry_profile"):
        payload["retry_profile"] = classification["retry_profile"]
    return payload


def _write_parsed_document(
    *,
    source_item_id: str,
    doc_id: str,
    source_sha256: str,
    parser_profile: str,
    title: str,
    text_preview: str,
    payload: bytes,
    now: str,
) -> int:
    artifact_id = _stable_id("artifact", doc_id, "docling_json")
    object_id = _stable_id("obj", doc_id, "paragraph", "0")
    with sqlite3.connect(catalog_path()) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        blob = store_artifact_blob(conn, payload=payload, now=now)
        conn.execute(
            """
            INSERT INTO "documents"
            (doc_id, source_item_id, source_sha256, parser_profile, parse_status,
             parsed_at, title, language, object_count, valuable_item_count)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(doc_id) DO UPDATE SET
                source_item_id = excluded.source_item_id,
                source_sha256 = excluded.source_sha256,
                parser_profile = excluded.parser_profile,
                parse_status = excluded.parse_status,
                parsed_at = excluded.parsed_at,
                title = excluded.title,
                language = excluded.language,
                object_count = excluded.object_count,
                valuable_item_count = excluded.valuable_item_count
            """,
            (
                doc_id,
                source_item_id,
                source_sha256,
                parser_profile,
                "parsed",
                now,
                title,
                None,
                1,
                0,
            ),
        )
        conn.execute(
            """
            INSERT INTO "docling_artifacts"
            (artifact_id, doc_id, artifact_kind, artifact_uri, blob_id,
             content_sha256, storage_mode, artifact_status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(artifact_id) DO UPDATE SET
                doc_id = excluded.doc_id,
                artifact_kind = excluded.artifact_kind,
                artifact_uri = excluded.artifact_uri,
                blob_id = excluded.blob_id,
                content_sha256 = excluded.content_sha256,
                storage_mode = excluded.storage_mode,
                artifact_status = excluded.artifact_status
            """,
            (
                artifact_id,
                doc_id,
                "docling_json",
                blob["relative_uri"].as_posix()
                if isinstance(blob["relative_uri"], Path)
                else blob["relative_uri"],
                blob["blob_id"],
                blob["sha256"],
                blob["storage_mode"],
                "current",
            ),
        )
        conn.execute(
            'DELETE FROM "document_objects" WHERE doc_id = ?',
            (doc_id,),
        )
        conn.execute(
            """
            INSERT INTO "document_objects"
            (object_id, doc_id, parent_object_id, object_type, order_index,
             page_start, page_end, heading_path, text_preview, attrs_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                object_id,
                doc_id,
                None,
                "paragraph",
                0,
                None,
                None,
                None,
                text_preview[:500],
                json.dumps({"source": "docling_json_preview"}, sort_keys=True),
            ),
        )
        conn.commit()
    return 1


def _mark_document_failed(
    *,
    source_item_id: str,
    doc_id: str,
    source_sha256: str,
    parser_profile: str,
    title: str,
    now: str,
) -> None:
    with sqlite3.connect(catalog_path()) as conn:
        conn.execute(
            """
            INSERT INTO "documents"
            (doc_id, source_item_id, source_sha256, parser_profile, parse_status,
             parsed_at, title, language, object_count, valuable_item_count)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(doc_id) DO UPDATE SET
                source_item_id = excluded.source_item_id,
                source_sha256 = excluded.source_sha256,
                parser_profile = excluded.parser_profile,
                parse_status = excluded.parse_status,
                parsed_at = excluded.parsed_at,
                title = excluded.title
            """,
            (
                doc_id,
                source_item_id,
                source_sha256,
                parser_profile,
                "failed",
                now,
                title,
                None,
                0,
                0,
            ),
        )
        conn.commit()


def _source_items_for_root(root_id: str, limit: int | None) -> list[dict[str, Any]]:
    sql = """
        SELECT source_item_id, relative_path, source_uri, media_type, size_bytes,
               source_mtime, source_sha256
        FROM "source_items"
        WHERE root_id = ?
          AND item_kind = 'file'
          AND inventory_status IN ('current', 'unchanged', 'changed')
        ORDER BY relative_path
    """
    params: list[Any] = [root_id]
    if limit is not None:
        sql += " LIMIT ?"
        params.append(limit)
    with sqlite3.connect(catalog_path()) as conn:
        rows = conn.execute(sql, params).fetchall()
    return [
        {
            "source_item_id": row[0],
            "relative_path": row[1],
            "source_uri": row[2],
            "media_type": row[3],
            "size_bytes": row[4],
            "source_mtime": row[5],
            "source_sha256": row[6],
        }
        for row in rows
    ]


def _document_state(doc_id: str) -> dict[str, Any] | None:
    with sqlite3.connect(catalog_path()) as conn:
        row = conn.execute(
            """
            SELECT source_sha256, parser_profile, parse_status
            FROM "documents"
            WHERE doc_id = ?
            """,
            (doc_id,),
        ).fetchone()
    if not row:
        return None
    return {
        "source_sha256": row[0],
        "parser_profile": row[1],
        "parse_status": row[2],
    }


def _document_json(document: Any) -> Any:
    for method_name in ("export_to_dict", "model_dump", "dict"):
        method = getattr(document, method_name, None)
        if method is None:
            continue
        try:
            return method()
        except TypeError:
            continue
    return {"repr": repr(document)}


def _document_preview(document: Any) -> str:
    method = getattr(document, "export_to_markdown", None)
    if method is not None:
        try:
            return " ".join(str(method()).split())
        except Exception:
            pass
    data = _document_json(document)
    return " ".join(json.dumps(data, default=str)[:2000].split())


def _document_title(document: Any, item: dict[str, Any]) -> str:
    for attr in ("title", "name"):
        value = getattr(document, attr, None)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return Path(item["relative_path"]).stem


def _conversion_errors(result: Any, item: dict[str, Any]) -> list[str]:
    messages: list[str] = []
    for error in getattr(result, "errors", []) or []:
        raw = getattr(error, "error_message", None)
        if raw is None:
            raw = str(error)
        message = _sanitize_message(str(raw), item)
        if message:
            messages.append(message)
    return messages


def _result_page_count(result: Any) -> int | None:
    input_doc = getattr(result, "input", None)
    page_count = getattr(input_doc, "page_count", None)
    if isinstance(page_count, int) and page_count > 0:
        return page_count
    return None


def _status_value(value: Any) -> str:
    if value is None:
        return "unknown"
    status = getattr(value, "value", value)
    return str(status)


def _classify_error(error_type: str, message: str) -> str:
    text = f"{error_type} {message}".lower()
    if "password" in text and ("incorrect" in text or "encrypted" in text):
        return "pdf_password_required"
    if any(
        marker in text
        for marker in (
            "std::bad_alloc",
            "bad_alloc",
            "memoryerror",
            "out of memory",
            "cannot allocate",
        )
    ):
        return "resource_exhausted_memory"
    if "timeout" in text or "document processing time" in text:
        return "document_timeout"
    if "max_num_pages" in text or ("page" in text and "limit" in text):
        return "document_too_many_pages"
    if "max_file_size" in text or ("file" in text and "size" in text and "limit" in text):
        return "document_too_large"
    if "skipped" in text:
        return "docling_skipped"
    if "not valid" in text or "cannot be opened" in text:
        return "docling_input_invalid"
    return "docling_convert_failed"


def _failure_classification(error_kind: str) -> dict[str, str]:
    classifications = {
        "pdf_password_required": {
            "category": "input",
            "diagnosis": "The PDF appears to be encrypted or password-protected.",
            "suggested_action": "Provide an unlocked copy or add a password-aware ingest path before parsing.",
        },
        "resource_exhausted_memory": {
            "category": "resource",
            "diagnosis": "The PDF/OCR pipeline exhausted native memory while processing page images.",
            "suggested_action": "Retry with docling_fast_text, split the PDF, or lower batch, queue, and thread settings further.",
            "retry_profile": "docling_fast_text",
        },
        "document_timeout": {
            "category": "resource",
            "diagnosis": "Document conversion exceeded the configured per-document timeout.",
            "suggested_action": "Retry with a higher timeout, split the PDF, or use docling_fast_text for text-based PDFs.",
            "retry_profile": "docling_fast_text",
        },
        "document_too_many_pages": {
            "category": "safeguard",
            "diagnosis": "The document exceeded the configured page limit.",
            "suggested_action": "Raise the page limit intentionally or split the document into smaller files.",
        },
        "document_too_large": {
            "category": "safeguard",
            "diagnosis": "The document exceeded the configured file-size limit.",
            "suggested_action": "Raise the file-size limit intentionally or process a smaller/split copy.",
        },
        "docling_input_invalid": {
            "category": "input",
            "diagnosis": "Docling could not open the source as a valid supported document.",
            "suggested_action": "Check whether the file is corrupt, locked, unsupported, or only partially synced locally.",
        },
        "docling_skipped": {
            "category": "input",
            "diagnosis": "Docling skipped the source under the active conversion limits or format rules.",
            "suggested_action": "Check parser limits and supported file formats for this run.",
        },
        "docling_convert_failed": {
            "category": "conversion",
            "diagnosis": "Docling failed while converting the document.",
            "suggested_action": "Retry with docling_fast_text for text PDFs or isolate the file for targeted OCR/debugging.",
            "retry_profile": "docling_fast_text",
        },
    }
    return classifications.get(error_kind, classifications["docling_convert_failed"])


def _sanitize_message(message: str, item: dict[str, Any]) -> str:
    cleaned = " ".join(message.split())
    source_uri = str(item.get("source_uri", ""))
    if source_uri:
        cleaned = cleaned.replace(source_uri, str(item.get("relative_path", "[source]")))
    return cleaned[:240]


def _is_pdf_source(item: dict[str, Any]) -> bool:
    media_type = str(item.get("media_type") or "").lower()
    return media_type == "application/pdf" or Path(item["relative_path"]).suffix.lower() == ".pdf"


def _int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    return int(value)


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def _format_count(value: Any) -> str:
    return str(int(value))


def _profile(config: dict[str, Any], name: str) -> dict[str, Any] | None:
    for profile in config.get("parser_profiles", []):
        if profile.get("name") == name:
            return profile
    return None


def _stable_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256("\0".join(parts).encode("utf-8")).hexdigest()[:32]
    return f"{prefix}_{digest}"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")
