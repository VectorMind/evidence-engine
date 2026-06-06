"""Generated indexing chunks derived from catalog document objects."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any

from agents_cli.paths import catalog_path


def chunks_for_root(
    *, root_id: str, scope_id: str, chunk_profile: str
) -> list[dict[str, Any]]:
    sql = """
        SELECT o.object_id, o.doc_id, o.object_type, o.order_index, o.page_start,
               o.page_end, o.heading_path, o.text_preview, o.attrs_json,
               d.title, d.parser_profile, d.source_sha256,
               si.source_item_id, si.relative_path, sr.root_label
        FROM "document_objects" o
        JOIN "documents" d ON d.doc_id = o.doc_id
        JOIN "source_items" si ON si.source_item_id = d.source_item_id
        JOIN "source_roots" sr ON sr.root_id = si.root_id
        WHERE si.root_id = ?
          AND d.parse_status = 'parsed'
          AND si.inventory_status IN ('current', 'unchanged', 'changed')
          AND COALESCE(o.text_preview, '') <> ''
        ORDER BY si.relative_path, o.order_index, o.object_id
    """
    with sqlite3.connect(catalog_path()) as conn:
        rows = conn.execute(sql, (root_id,)).fetchall()

    chunks: list[dict[str, Any]] = []
    for row in rows:
        object_id = row[0]
        doc_id = row[1]
        object_type = row[2] or "paragraph"
        text = " ".join(str(row[7] or "").split())
        if not text:
            continue
        title = row[9] or Path(row[13]).stem
        metadata = {
            "root_id": root_id,
            "root_label": row[14],
            "source_item_id": row[12],
            "relative_path": row[13],
            "parser_profile": row[10],
            "source_sha256": row[11],
            "object_order_index": row[3],
        }
        chunk_id = stable_id("chunk", scope_id, doc_id, object_id, chunk_profile)
        chunks.append(
            {
                "chunk_id": chunk_id,
                "doc_id": doc_id,
                "object_id": object_id,
                "scope_id": scope_id,
                "chunk_profile": chunk_profile,
                "content_type": content_type(object_type),
                "page_start": row[4],
                "page_end": row[5],
                "title": title,
                "heading_path": row[6] or "",
                "body": text,
                "metadata_json": json.dumps(metadata, sort_keys=True),
                "source_sha256": row[11],
            }
        )
    return chunks


def high_watermark(chunks: list[dict[str, Any]], *extra: str) -> str:
    digest = hashlib.sha256()
    for value in extra:
        digest.update(str(value or "").encode("utf-8"))
        digest.update(b"\0")
    for chunk in chunks:
        for field in (
            "chunk_id",
            "doc_id",
            "object_id",
            "source_sha256",
            "body",
            "title",
        ):
            digest.update(str(chunk.get(field) or "").encode("utf-8"))
            digest.update(b"\0")
    return digest.hexdigest()


def document_count(chunks: list[dict[str, Any]]) -> int:
    return len({chunk["doc_id"] for chunk in chunks})


def content_type(object_type: str) -> str:
    if object_type in {
        "paragraph",
        "section",
        "table",
        "codeblock",
        "formula",
    }:
        return object_type
    if object_type in {"caption", "figure", "image", "diagram", "chart"}:
        return "figure_caption"
    return "plain_text"


def stable_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256("\0".join(parts).encode("utf-8")).hexdigest()[:32]
    return f"{prefix}_{digest}"
