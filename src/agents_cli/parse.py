"""Docling-backed folder parsing."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import importlib
import json
from pathlib import Path
import sqlite3
from typing import Any

from agents_cli.blobs import store_artifact_blob
from agents_cli.config import load_parser_config
from agents_cli.inventory import ScanOptions, scan_folder_to_catalog
from agents_cli.paths import catalog_path


@dataclass(frozen=True)
class ParseOptions:
    profile: str | None
    limit: int | None


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

    converter_report = _build_converter(profile)
    if converter_report["status"] != "ok":
        return {
            "status": "failed",
            "error_kind": converter_report["error_kind"],
            "parser_profile": profile_name,
            "root_id": root_id,
            "root_label": scan_result.get("root_label"),
            "scope_id": scan_result.get("scope_id"),
            "message": converter_report["message"],
        }

    now = _iso(_utc_now())
    counts = {
        "documents_planned": len(source_items),
        "documents_parsed": 0,
        "documents_failed": 0,
        "documents_unchanged": 0,
        "artifacts_written": 0,
        "objects_written": 0,
    }
    failures: list[dict[str, Any]] = []

    for item in source_items:
        parsed = _parse_one(
            item,
            converter_report["converter"],
            parser_profile=profile_name,
            now=now,
        )
        if parsed["status"] == "parsed":
            counts["documents_parsed"] += 1
            counts["artifacts_written"] += parsed["artifact_count"]
            counts["objects_written"] += parsed["object_count"]
        elif parsed["status"] == "unchanged":
            counts["documents_unchanged"] += 1
        else:
            counts["documents_failed"] += 1
            failures.append(parsed)

    status = "ok" if counts["documents_failed"] == 0 else "partial"
    return {
        "status": status,
        "parser_profile": profile_name,
        "root_id": root_id,
        "root_label": scan_result.get("root_label"),
        "scope_id": scan_result.get("scope_id"),
        "source_uri_redacted": True,
        "auto_scan_status": scan_result["status"],
        "ocr_requested": bool(profile.get("ocr", False)),
        "counts": counts,
        "failures": failures[:20],
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


def _build_converter(profile: dict[str, Any]) -> dict[str, Any]:
    try:
        from docling.document_converter import DocumentConverter
    except ModuleNotFoundError:
        return {
            "status": "failed",
            "error_kind": "docling_missing",
            "message": "Install the docling extra before running parse commands.",
        }

    if profile.get("ocr") is True:
        try:
            from docling.datamodel.base_models import InputFormat
            from docling.datamodel.pipeline_options import PdfPipelineOptions
            from docling.document_converter import PdfFormatOption

            pipeline_options = PdfPipelineOptions()
            pipeline_options.do_ocr = True
            pipeline_options.do_table_structure = bool(
                profile.get("table_structure", True)
            )
            converter = DocumentConverter(
                format_options={
                    InputFormat.PDF: PdfFormatOption(
                        pipeline_options=pipeline_options
                    )
                }
            )
            return {"status": "ok", "converter": converter}
        except Exception as exc:
            return {
                "status": "failed",
                "error_kind": "ocr_dependency_missing",
                "message": f"Could not initialize Docling OCR profile: {exc.__class__.__name__}",
            }

    try:
        return {"status": "ok", "converter": DocumentConverter()}
    except Exception as exc:
        return {
            "status": "failed",
            "error_kind": "docling_converter_failed",
            "message": f"Could not initialize Docling converter: {exc.__class__.__name__}",
        }


def _parse_one(
    item: dict[str, Any],
    converter: Any,
    *,
    parser_profile: str,
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

    try:
        result = converter.convert(item["source_uri"])
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
        return {
            "status": "failed",
            "doc_id": doc_id,
            "source_item_id": source_item_id,
            "relative_path": item["relative_path"],
            "error_kind": "docling_convert_failed",
            "redacted_detail": exc.__class__.__name__,
        }

    return {
        "status": "parsed",
        "doc_id": doc_id,
        "artifact_count": 1,
        "object_count": object_count,
    }


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
