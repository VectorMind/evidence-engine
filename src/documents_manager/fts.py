"""Full-text indexing and search."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import importlib
import json
from pathlib import Path
import sqlite3
from typing import Any

from documents_manager.catalog import ensure_catalog
from documents_manager.chunks import chunks_for_root, document_count, high_watermark, stable_id
from documents_manager.config import load_parser_config
from documents_manager.inventory import ScanOptions, scan_folder_to_catalog
from documents_manager.paths import catalog_path, workspace_root


@dataclass(frozen=True)
class IndexOptions:
    force: bool = False


@dataclass(frozen=True)
class SearchOptions:
    limit: int = 30


def index_scope_to_fts(path: Path, options: IndexOptions) -> dict[str, Any]:
    """Build or refresh the FTS island for a folder root."""

    runtime = _tantivy_runtime_status()
    if runtime["status"] != "ok":
        return runtime

    ensure_report = ensure_catalog()
    if ensure_report["status"] not in {"created", "current"}:
        return {
            "status": "failed",
            "error_kind": "catalog_unavailable",
            "catalog_status": ensure_report["status"],
        }

    scan_result = scan_folder_to_catalog(
        path,
        ScanOptions(max_files=None, max_bytes=None, max_depth=None),
    )
    if scan_result["status"] != "ok":
        return {
            "status": scan_result["status"],
            "error_kind": "auto_scan_failed",
            "auto_scan_status": scan_result["status"],
            "scan_result": scan_result,
        }

    config = load_parser_config()
    defaults = config["defaults"]
    fts_profile = defaults.get("fts_profile", "text_default_en")
    chunk_profile = defaults.get("chunk_profile", "docling_hybrid_v1")
    root_id = scan_result["root_id"]
    scope_id = scan_result["scope_id"]
    chunks = chunks_for_root(
        root_id=root_id,
        scope_id=scope_id,
        chunk_profile=chunk_profile,
    )
    if not chunks:
        return {
            "status": "deferred",
            "error_kind": "no_parsed_documents",
            "message": "No parsed document objects were available. Run docs parse first.",
            "root_id": root_id,
            "root_label": scan_result.get("root_label"),
            "scope_id": scope_id,
            "fts_profile": fts_profile,
            "chunk_profile": chunk_profile,
            "auto_scan_status": scan_result["status"],
            "counts": {
                "documents_indexed": 0,
                "chunks_planned": 0,
                "chunks_indexed": 0,
                "chunks_unchanged": 0,
            },
        }

    index_uri = f"fts/{fts_profile}/{scope_id}"
    index_dir = workspace_root() / index_uri
    source_high_watermark = high_watermark(chunks, fts_profile)
    fts_index_id = stable_id("fts", scope_id, fts_profile)
    existing = _fts_registry_state(fts_index_id)

    if (
        not options.force
        and existing
        and existing["status"] == "current"
        and existing["source_high_watermark"] == source_high_watermark
        and _tantivy_index_exists(index_dir)
    ):
        return {
            "status": "ok",
            "root_id": root_id,
            "root_label": scan_result.get("root_label"),
            "scope_id": scope_id,
            "fts_index_id": fts_index_id,
            "fts_profile": fts_profile,
            "chunk_profile": chunk_profile,
            "template_name": "fts_chunk_document",
            "index_uri": index_uri,
            "auto_scan_status": scan_result["status"],
            "index_status": "current",
            "source_high_watermark": source_high_watermark,
            "counts": {
                "documents_indexed": document_count(chunks),
                "chunks_planned": len(chunks),
                "chunks_indexed": 0,
                "chunks_unchanged": len(chunks),
            },
        }

    build = _write_tantivy_index(index_dir, chunks)
    now = _iso(_utc_now())
    _upsert_fts_registry(
        fts_index_id=fts_index_id,
        scope_id=scope_id,
        fts_profile=fts_profile,
        chunk_profile=chunk_profile,
        index_uri=index_uri,
        indexed_chunk_count=len(chunks),
        source_high_watermark=source_high_watermark,
        status="current" if build["status"] == "ok" else "failed",
        updated_at=now,
    )
    if build["status"] != "ok":
        return {
            "status": "failed",
            "error_kind": build["error_kind"],
            "root_id": root_id,
            "root_label": scan_result.get("root_label"),
            "scope_id": scope_id,
            "fts_index_id": fts_index_id,
            "fts_profile": fts_profile,
            "chunk_profile": chunk_profile,
            "auto_scan_status": scan_result["status"],
            "redacted_detail": build.get("redacted_detail"),
        }

    return {
        "status": "ok",
        "root_id": root_id,
        "root_label": scan_result.get("root_label"),
        "scope_id": scope_id,
        "fts_index_id": fts_index_id,
        "fts_profile": fts_profile,
        "chunk_profile": chunk_profile,
        "template_name": "fts_chunk_document",
        "index_uri": index_uri,
        "auto_scan_status": scan_result["status"],
        "index_status": "rebuilt" if options.force else "refreshed",
        "source_high_watermark": source_high_watermark,
        "counts": {
            "documents_indexed": document_count(chunks),
            "chunks_planned": len(chunks),
            "chunks_indexed": len(chunks),
            "chunks_unchanged": 0,
        },
    }


def search_text_indexes(query: str, options: SearchOptions) -> dict[str, Any]:
    """Search all current FTS islands and hydrate stored provenance."""

    runtime = _tantivy_runtime_status()
    if runtime["status"] != "ok":
        return runtime

    indexes = _current_fts_indexes()
    if not indexes:
        return {
            "status": "ok",
            "query": query,
            "counts": {
                "indexes_searched": 0,
                "hits_returned": 0,
            },
            "hits": [],
            "message": "No current text indexes were registered.",
        }

    limit = max(1, int(options.limit or 30))
    hits: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    for index_row in indexes:
        result = _search_one_index(index_row, query, limit)
        if result["status"] == "ok":
            hits.extend(result["hits"])
        else:
            failures.append(result)

    hits = sorted(hits, key=lambda hit: (-float(hit["score"]), hit["chunk_id"]))[:limit]
    return {
        "status": "ok" if not failures else "partial",
        "query": query,
        "counts": {
            "indexes_searched": len(indexes),
            "index_failures": len(failures),
            "hits_returned": len(hits),
        },
        "hits": hits,
        "failures": failures[:10],
    }


def _tantivy_runtime_status() -> dict[str, str]:
    try:
        importlib.import_module("tantivy")
    except ModuleNotFoundError:
        return {
            "status": "failed",
            "error_kind": "fts_dependency_missing",
            "message": "Install the fts extra before running index or search commands.",
        }
    return {"status": "ok"}


def _write_tantivy_index(index_dir: Path, chunks: list[dict[str, Any]]) -> dict[str, Any]:
    try:
        import tantivy  # type: ignore[import-not-found]

        index_dir.mkdir(parents=True, exist_ok=True)
        index = tantivy.Index(_schema(), path=str(index_dir), reuse=True)
        writer = index.writer(heap_size=50_000_000)
        writer.delete_all_documents()
        for chunk in chunks:
            document = tantivy.Document()
            for field in (
                "chunk_id",
                "doc_id",
                "object_id",
                "scope_id",
                "chunk_profile",
                "content_type",
                "title",
                "heading_path",
                "body",
                "metadata_json",
            ):
                document.add_text(field, str(chunk.get(field) or ""))
            if chunk.get("page_start") is not None:
                document.add_integer("page_start", int(chunk["page_start"]))
            if chunk.get("page_end") is not None:
                document.add_integer("page_end", int(chunk["page_end"]))
            writer.add_document(document)
        writer.commit()
        index.reload()
    except Exception as exc:
        return {
            "status": "failed",
            "error_kind": "fts_write_failed",
            "redacted_detail": exc.__class__.__name__,
        }
    return {"status": "ok"}


def _schema() -> Any:
    import tantivy  # type: ignore[import-not-found]

    builder = tantivy.SchemaBuilder()
    for field in (
        "chunk_id",
        "doc_id",
        "object_id",
        "scope_id",
        "chunk_profile",
        "content_type",
    ):
        builder.add_text_field(
            field,
            stored=True,
            tokenizer_name="raw",
            index_option="basic",
        )
    builder.add_integer_field("page_start", stored=True, indexed=True)
    builder.add_integer_field("page_end", stored=True, indexed=True)
    builder.add_text_field("title", stored=True, tokenizer_name="default")
    builder.add_text_field("heading_path", stored=True, tokenizer_name="default")
    builder.add_text_field("body", stored=True, tokenizer_name="default")
    builder.add_text_field(
        "metadata_json",
        stored=True,
        tokenizer_name="raw",
        index_option="basic",
    )
    return builder.build()


def _search_one_index(
    index_row: dict[str, Any], query: str, limit: int
) -> dict[str, Any]:
    try:
        import tantivy  # type: ignore[import-not-found]

        index_path = workspace_root() / index_row["index_uri"]
        index = tantivy.Index.open(str(index_path))
        parsed, errors = index.parse_query_lenient(
            query,
            default_field_names=["title", "heading_path", "body"],
        )
        searcher = index.searcher()
        result = searcher.search(parsed, limit=limit)
        hits = []
        for score, doc_address in result.hits:
            stored = searcher.doc(doc_address).to_dict()
            metadata = _json_field(stored, "metadata_json")
            hits.append(
                {
                    "score": float(score),
                    "chunk_id": _first(stored, "chunk_id"),
                    "doc_id": _first(stored, "doc_id"),
                    "object_id": _first(stored, "object_id"),
                    "scope_id": index_row["scope_id"],
                    "fts_index_id": index_row["fts_index_id"],
                    "title": _first(stored, "title"),
                    "body_preview": _first(stored, "body")[:500],
                    "content_type": _first(stored, "content_type"),
                    "page_start": _first(stored, "page_start"),
                    "page_end": _first(stored, "page_end"),
                    "root_label": metadata.get("root_label"),
                    "relative_path": metadata.get("relative_path"),
                }
            )
    except Exception as exc:
        return {
            "status": "failed",
            "error_kind": "fts_search_failed",
            "fts_index_id": index_row.get("fts_index_id"),
            "redacted_detail": exc.__class__.__name__,
        }
    return {
        "status": "ok",
        "fts_index_id": index_row["fts_index_id"],
        "query_errors": [str(error) for error in errors],
        "hits": hits,
    }


def _fts_registry_state(fts_index_id: str) -> dict[str, Any] | None:
    with sqlite3.connect(catalog_path()) as conn:
        row = conn.execute(
            """
            SELECT source_high_watermark, status
            FROM "fts_indexes"
            WHERE fts_index_id = ?
            """,
            (fts_index_id,),
        ).fetchone()
    if not row:
        return None
    return {"source_high_watermark": row[0], "status": row[1]}


def _current_fts_indexes() -> list[dict[str, Any]]:
    with sqlite3.connect(catalog_path()) as conn:
        rows = conn.execute(
            """
            SELECT fts_index_id, scope_id, fts_profile, chunk_profile,
                   template_name, index_uri, indexed_chunk_count,
                   source_high_watermark
            FROM "fts_indexes"
            WHERE status = 'current'
            ORDER BY updated_at DESC, fts_index_id
            """
        ).fetchall()
    return [
        {
            "fts_index_id": row[0],
            "scope_id": row[1],
            "fts_profile": row[2],
            "chunk_profile": row[3],
            "template_name": row[4],
            "index_uri": row[5],
            "indexed_chunk_count": row[6],
            "source_high_watermark": row[7],
        }
        for row in rows
    ]


def _upsert_fts_registry(
    *,
    fts_index_id: str,
    scope_id: str,
    fts_profile: str,
    chunk_profile: str,
    index_uri: str,
    indexed_chunk_count: int,
    source_high_watermark: str,
    status: str,
    updated_at: str,
) -> None:
    with sqlite3.connect(catalog_path()) as conn:
        conn.execute(
            """
            INSERT INTO "fts_indexes"
            (fts_index_id, scope_id, fts_profile, chunk_profile, template_name,
             index_uri, indexed_chunk_count, source_high_watermark, status,
             updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(fts_index_id) DO UPDATE SET
                scope_id = excluded.scope_id,
                fts_profile = excluded.fts_profile,
                chunk_profile = excluded.chunk_profile,
                template_name = excluded.template_name,
                index_uri = excluded.index_uri,
                indexed_chunk_count = excluded.indexed_chunk_count,
                source_high_watermark = excluded.source_high_watermark,
                status = excluded.status,
                updated_at = excluded.updated_at
            """,
            (
                fts_index_id,
                scope_id,
                fts_profile,
                chunk_profile,
                "fts_chunk_document",
                index_uri,
                indexed_chunk_count,
                source_high_watermark,
                status,
                updated_at,
            ),
        )
        conn.commit()


def _tantivy_index_exists(index_dir: Path) -> bool:
    try:
        import tantivy  # type: ignore[import-not-found]

        return bool(index_dir.exists() and tantivy.Index.exists(str(index_dir)))
    except Exception:
        return False


def _json_field(stored: dict[str, Any], field: str) -> dict[str, Any]:
    raw = _first(stored, field)
    if not raw:
        return {}
    try:
        value = json.loads(str(raw))
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _first(stored: dict[str, Any], field: str) -> Any:
    value = stored.get(field)
    if isinstance(value, list):
        return value[0] if value else None
    return value


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")
