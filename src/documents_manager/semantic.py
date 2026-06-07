"""Semantic indexing and search."""

from __future__ import annotations

from contextlib import contextmanager, redirect_stderr, redirect_stdout
from dataclasses import dataclass
from datetime import datetime, timezone
import importlib
import io
import json
import logging
import os
from pathlib import Path
import sqlite3
import sys
from typing import Any, Iterator
import warnings

from documents_manager.catalog import ensure_catalog
from documents_manager.chunks import chunks_for_root, document_count, high_watermark, stable_id
from documents_manager.config import embedding_profile, load_parser_config
from documents_manager.inventory import ScanOptions, scan_folder_to_catalog
from documents_manager.paths import catalog_path, workspace_root


os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
os.environ.setdefault("LANCE_LOG", "error")
os.environ.setdefault("RUST_LOG", "error")


@dataclass(frozen=True)
class SemanticIndexOptions:
    force: bool = False
    embedding_profile: str | None = None


@dataclass(frozen=True)
class SemanticSearchOptions:
    limit: int = 30
    embedding_profile: str | None = None


def index_scope_to_semantic(
    path: Path, options: SemanticIndexOptions
) -> dict[str, Any]:
    """Build or refresh the semantic island for a folder root."""

    runtime = _semantic_runtime_status()
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
    profile_name = options.embedding_profile or defaults.get(
        "embedding_profile", "fastembed_bge_small_en_v1_5"
    )
    profile = embedding_profile(profile_name)
    if profile is None:
        return {
            "status": "failed",
            "error_kind": "unknown_embedding_profile",
            "embedding_profile": profile_name,
        }
    if profile.get("provider") != "fastembed":
        return {
            "status": "failed",
            "error_kind": "unsupported_embedding_provider",
            "embedding_profile": profile_name,
            "provider": profile.get("provider"),
            "message": "Semantic V1 supports FastEmbed profiles only.",
        }

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
            "embedding_profile": profile_name,
            "chunk_profile": chunk_profile,
            "auto_scan_status": scan_result["status"],
            "counts": {
                "documents_indexed": 0,
                "chunks_planned": 0,
                "chunks_indexed": 0,
                "chunks_unchanged": 0,
            },
        }

    model_name = str(profile["model_name"])
    vector_dimension = int(profile.get("dimension") or 0)
    store_uri = f"semantic/{profile_name}/{scope_id}.lancedb"
    table_name = "chunks"
    store_dir = workspace_root() / store_uri
    semantic_store_id = stable_id("sem", scope_id, profile_name)
    source_high_watermark = high_watermark(chunks, profile_name, model_name)
    existing = _semantic_registry_state(semantic_store_id)

    if (
        not options.force
        and existing
        and existing["status"] == "current"
        and existing["source_high_watermark"] == source_high_watermark
        and _lancedb_store_exists(store_dir, table_name)
    ):
        return {
            "status": "ok",
            "index_backend": "semantic",
            "root_id": root_id,
            "root_label": scan_result.get("root_label"),
            "scope_id": scope_id,
            "semantic_store_id": semantic_store_id,
            "embedding_profile": profile_name,
            "embedding_model": model_name,
            "chunk_profile": chunk_profile,
            "template_name": "semantic_chunk_row",
            "store_uri": store_uri,
            "table_name": table_name,
            "auto_scan_status": scan_result["status"],
            "index_status": "current",
            "vector_dimension": existing.get("vector_dimension") or vector_dimension,
            "source_high_watermark": source_high_watermark,
            "counts": {
                "documents_indexed": document_count(chunks),
                "chunks_planned": len(chunks),
                "chunks_indexed": 0,
                "chunks_unchanged": len(chunks),
            },
        }

    build = _write_lancedb_store(
        store_dir=store_dir,
        table_name=table_name,
        chunks=chunks,
        profile=profile,
    )
    now = _iso(_utc_now())
    vector_dimension = int(build.get("vector_dimension") or vector_dimension)
    _upsert_semantic_registry(
        semantic_store_id=semantic_store_id,
        scope_id=scope_id,
        embedding_profile=profile_name,
        chunk_profile=chunk_profile,
        store_uri=store_uri,
        table_name=table_name,
        vector_dimension=vector_dimension,
        indexed_chunk_count=len(chunks),
        source_high_watermark=source_high_watermark,
        status="current" if build["status"] == "ok" else "failed",
        updated_at=now,
    )
    if build["status"] != "ok":
        return {
            "status": "failed",
            "error_kind": build["error_kind"],
            "index_backend": "semantic",
            "root_id": root_id,
            "root_label": scan_result.get("root_label"),
            "scope_id": scope_id,
            "semantic_store_id": semantic_store_id,
            "embedding_profile": profile_name,
            "chunk_profile": chunk_profile,
            "auto_scan_status": scan_result["status"],
            "redacted_detail": build.get("redacted_detail"),
        }

    return {
        "status": "ok",
        "index_backend": "semantic",
        "root_id": root_id,
        "root_label": scan_result.get("root_label"),
        "scope_id": scope_id,
        "semantic_store_id": semantic_store_id,
        "embedding_profile": profile_name,
        "embedding_model": model_name,
        "chunk_profile": chunk_profile,
        "template_name": "semantic_chunk_row",
        "store_uri": store_uri,
        "table_name": table_name,
        "auto_scan_status": scan_result["status"],
        "index_status": "rebuilt" if options.force else "refreshed",
        "vector_dimension": vector_dimension,
        "source_high_watermark": source_high_watermark,
        "counts": {
            "documents_indexed": document_count(chunks),
            "chunks_planned": len(chunks),
            "chunks_indexed": len(chunks),
            "chunks_unchanged": 0,
        },
    }


def search_semantic_indexes(
    query: str, options: SemanticSearchOptions
) -> dict[str, Any]:
    """Search current semantic stores."""

    runtime = _semantic_runtime_status()
    if runtime["status"] != "ok":
        return runtime

    stores = _current_semantic_stores(profile_name=options.embedding_profile)
    if not stores:
        return {
            "status": "ok",
            "search_backend": "semantic",
            "query": query,
            "counts": {
                "indexes_searched": 0,
                "hits_returned": 0,
            },
            "hits": [],
            "message": "No current semantic stores were registered.",
        }

    limit = max(1, int(options.limit or 30))
    hits: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    for store in stores:
        result = _search_one_store(store, query, limit)
        if result["status"] == "ok":
            hits.extend(result["hits"])
        else:
            failures.append(result)

    hits = sorted(
        hits,
        key=lambda hit: (
            float(hit.get("distance", 0)),
            str(hit.get("chunk_id", "")),
        ),
    )[:limit]
    return {
        "status": "ok" if not failures else "partial",
        "search_backend": "semantic",
        "query": query,
        "counts": {
            "indexes_searched": len(stores),
            "index_failures": len(failures),
            "hits_returned": len(hits),
        },
        "hits": hits,
        "failures": failures[:10],
    }


def _semantic_runtime_status() -> dict[str, str]:
    missing = [
        module_name
        for module_name in ("lancedb", "fastembed", "pyarrow", "numpy")
        if importlib.util.find_spec(module_name) is None
    ]
    if missing:
        return {
            "status": "failed",
            "error_kind": "semantic_dependencies_missing",
            "message": "Install the semantic and embeddings extras before running semantic commands.",
            "missing": ",".join(missing),
        }
    return {"status": "ok"}


def _write_lancedb_store(
    *,
    store_dir: Path,
    table_name: str,
    chunks: list[dict[str, Any]],
    profile: dict[str, Any],
) -> dict[str, Any]:
    try:
        import lancedb  # type: ignore[import-not-found]

        vectors = _embed_passages(profile, [str(chunk["body"]) for chunk in chunks])
        rows = [
            _row_for_chunk(chunk, vector, str(profile["name"]))
            for chunk, vector in zip(chunks, vectors)
        ]
        store_dir.mkdir(parents=True, exist_ok=True)
        with _quiet_output():
            db = lancedb.connect(str(store_dir))
            db.create_table(table_name, data=rows, mode="overwrite")
    except Exception as exc:
        return {
            "status": "failed",
            "error_kind": "semantic_write_failed",
            "redacted_detail": exc.__class__.__name__,
        }
    dimension = len(rows[0]["vector"]) if rows else 0
    return {"status": "ok", "vector_dimension": dimension}


def _search_one_store(
    store: dict[str, Any], query: str, limit: int
) -> dict[str, Any]:
    try:
        import lancedb  # type: ignore[import-not-found]

        profile = embedding_profile(store["embedding_profile"])
        if profile is None:
            return {
                "status": "failed",
                "error_kind": "unknown_embedding_profile",
                "semantic_store_id": store["semantic_store_id"],
            }
        query_vector = _embed_query(profile, query)
        db = lancedb.connect(str(workspace_root() / store["store_uri"]))
        table = db.open_table(store["table_name"])
        results = table.search(query_vector).limit(limit).to_list()
        hits = [_hit_from_row(store, row) for row in results]
    except Exception as exc:
        return {
            "status": "failed",
            "error_kind": "semantic_search_failed",
            "semantic_store_id": store.get("semantic_store_id"),
            "redacted_detail": exc.__class__.__name__,
        }
    return {
        "status": "ok",
        "semantic_store_id": store["semantic_store_id"],
        "hits": hits,
    }


def _embed_passages(profile: dict[str, Any], texts: list[str]) -> list[list[float]]:
    model = _fastembed_model(profile)
    with _quiet_output():
        vectors = model.passage_embed(texts)
        return [_vector_to_list(vector) for vector in vectors]


def _embed_query(profile: dict[str, Any], text: str) -> list[float]:
    model = _fastembed_model(profile)
    with _quiet_output():
        return _vector_to_list(next(iter(model.query_embed([text]))))


def _fastembed_model(profile: dict[str, Any]) -> Any:
    from fastembed import TextEmbedding  # type: ignore[import-not-found]

    cache_dir = workspace_root() / "models" / "fastembed"
    cache_dir.mkdir(parents=True, exist_ok=True)
    with _quiet_output():
        return TextEmbedding(
            model_name=str(profile["model_name"]),
            cache_dir=str(cache_dir),
            lazy_load=True,
        )


def _row_for_chunk(
    chunk: dict[str, Any], vector: list[float], profile_name: str
) -> dict[str, Any]:
    metadata = _json_object(chunk.get("metadata_json"))
    return {
        "chunk_id": chunk["chunk_id"],
        "doc_id": chunk["doc_id"],
        "object_id": chunk["object_id"],
        "scope_id": chunk["scope_id"],
        "embedding_profile": profile_name,
        "chunk_profile": chunk["chunk_profile"],
        "vector": vector,
        "text": chunk["body"],
        "content_type": chunk["content_type"],
        "page_start": chunk.get("page_start"),
        "page_end": chunk.get("page_end"),
        "title": chunk.get("title") or "",
        "heading_path": chunk.get("heading_path") or "",
        "root_label": metadata.get("root_label") or "",
        "relative_path": metadata.get("relative_path") or "",
        "metadata_json": chunk.get("metadata_json") or "{}",
    }


def _hit_from_row(store: dict[str, Any], row: dict[str, Any]) -> dict[str, Any]:
    distance = float(row.get("_distance", 0.0) or 0.0)
    return {
        "score": 1.0 / (1.0 + distance),
        "distance": distance,
        "chunk_id": row.get("chunk_id"),
        "doc_id": row.get("doc_id"),
        "object_id": row.get("object_id"),
        "scope_id": row.get("scope_id") or store["scope_id"],
        "semantic_store_id": store["semantic_store_id"],
        "embedding_profile": store["embedding_profile"],
        "title": row.get("title"),
        "body_preview": str(row.get("text") or "")[:500],
        "content_type": row.get("content_type"),
        "page_start": row.get("page_start"),
        "page_end": row.get("page_end"),
        "root_label": row.get("root_label"),
        "relative_path": row.get("relative_path"),
    }


def _semantic_registry_state(semantic_store_id: str) -> dict[str, Any] | None:
    with sqlite3.connect(catalog_path()) as conn:
        row = conn.execute(
            """
            SELECT source_high_watermark, status, vector_dimension
            FROM "semantic_stores"
            WHERE semantic_store_id = ?
            """,
            (semantic_store_id,),
        ).fetchone()
    if not row:
        return None
    return {
        "source_high_watermark": row[0],
        "status": row[1],
        "vector_dimension": row[2],
    }


def _current_semantic_stores(
    *, profile_name: str | None = None
) -> list[dict[str, Any]]:
    sql = """
        SELECT semantic_store_id, scope_id, embedding_profile, chunk_profile,
               template_name, store_uri, table_name, vector_dimension,
               indexed_chunk_count, source_high_watermark
        FROM "semantic_stores"
        WHERE status = 'current'
    """
    params: list[Any] = []
    if profile_name:
        sql += " AND embedding_profile = ?"
        params.append(profile_name)
    sql += " ORDER BY updated_at DESC, semantic_store_id"
    with sqlite3.connect(catalog_path()) as conn:
        rows = conn.execute(sql, params).fetchall()
    return [
        {
            "semantic_store_id": row[0],
            "scope_id": row[1],
            "embedding_profile": row[2],
            "chunk_profile": row[3],
            "template_name": row[4],
            "store_uri": row[5],
            "table_name": row[6],
            "vector_dimension": row[7],
            "indexed_chunk_count": row[8],
            "source_high_watermark": row[9],
        }
        for row in rows
    ]


def _upsert_semantic_registry(
    *,
    semantic_store_id: str,
    scope_id: str,
    embedding_profile: str,
    chunk_profile: str,
    store_uri: str,
    table_name: str,
    vector_dimension: int,
    indexed_chunk_count: int,
    source_high_watermark: str,
    status: str,
    updated_at: str,
) -> None:
    with sqlite3.connect(catalog_path()) as conn:
        conn.execute(
            """
            INSERT INTO "semantic_stores"
            (semantic_store_id, scope_id, embedding_profile, chunk_profile,
             template_name, store_uri, table_name, vector_dimension,
             indexed_chunk_count, source_high_watermark, status, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(semantic_store_id) DO UPDATE SET
                scope_id = excluded.scope_id,
                embedding_profile = excluded.embedding_profile,
                chunk_profile = excluded.chunk_profile,
                template_name = excluded.template_name,
                store_uri = excluded.store_uri,
                table_name = excluded.table_name,
                vector_dimension = excluded.vector_dimension,
                indexed_chunk_count = excluded.indexed_chunk_count,
                source_high_watermark = excluded.source_high_watermark,
                status = excluded.status,
                updated_at = excluded.updated_at
            """,
            (
                semantic_store_id,
                scope_id,
                embedding_profile,
                chunk_profile,
                "semantic_chunk_row",
                store_uri,
                table_name,
                vector_dimension,
                indexed_chunk_count,
                source_high_watermark,
                status,
                updated_at,
            ),
        )
        conn.commit()


def _lancedb_store_exists(store_dir: Path, table_name: str) -> bool:
    try:
        import lancedb  # type: ignore[import-not-found]

        if not store_dir.exists():
            return False
        db = lancedb.connect(str(store_dir))
        names = db.table_names()
        return table_name in names
    except Exception:
        return False


def _vector_to_list(vector: Any) -> list[float]:
    return [float(value) for value in list(vector)]


def _json_object(value: Any) -> dict[str, Any]:
    if not value:
        return {}
    try:
        parsed = json.loads(str(value))
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


@contextmanager
def _quiet_output() -> Iterator[None]:
    logger_names = ("fastembed", "huggingface_hub", "lancedb", "lance")
    previous_levels = {
        logger_name: logging.getLogger(logger_name).level
        for logger_name in logger_names
    }
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        for logger_name in logger_names:
            logging.getLogger(logger_name).setLevel(logging.ERROR)
        try:
            with _suppress_standard_fds():
                with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                    yield
        finally:
            for logger_name, level in previous_levels.items():
                logging.getLogger(logger_name).setLevel(level)


@contextmanager
def _suppress_standard_fds() -> Iterator[None]:
    sys.stdout.flush()
    sys.stderr.flush()
    saved_stdout = os.dup(1)
    saved_stderr = os.dup(2)
    devnull = os.open(os.devnull, os.O_WRONLY)
    try:
        os.dup2(devnull, 1)
        os.dup2(devnull, 2)
        yield
    finally:
        sys.stdout.flush()
        sys.stderr.flush()
        os.dup2(saved_stdout, 1)
        os.dup2(saved_stderr, 2)
        os.close(saved_stdout)
        os.close(saved_stderr)
        os.close(devnull)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")
