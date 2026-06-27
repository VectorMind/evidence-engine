"""Generated indexing chunks derived from catalog document objects."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from even.db import catalog_connection
from even.references import evidence_ref


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
    with catalog_connection() as conn:
        rows = conn.execute(sql, (root_id,)).fetchall()

    chunks: list[dict[str, Any]] = []
    for row in rows:
        object_id = row["object_id"]
        doc_id = row["doc_id"]
        object_type = row["object_type"] or "paragraph"
        text = " ".join(str(row["text_preview"] or "").split())
        if not text:
            continue
        title = row["title"] or Path(row["relative_path"]).stem
        metadata = {
            "root_id": root_id,
            "root_label": row["root_label"],
            "source_item_id": row["source_item_id"],
            "relative_path": row["relative_path"],
            "parser_profile": row["parser_profile"],
            "source_sha256": row["source_sha256"],
            "object_order_index": row["order_index"],
        }
        chunk_id = stable_id("chunk", scope_id, doc_id, object_id, chunk_profile)
        chunks.append(
            {
                "chunk_id": chunk_id,
                "doc_id": doc_id,
                "object_id": object_id,
                "asset_id": "",
                "ref": evidence_ref("document_objects", object_id),
                "scope_id": scope_id,
                "chunk_profile": chunk_profile,
                "content_type": content_type(object_type),
                "page_start": row["page_start"],
                "page_end": row["page_end"],
                "title": title,
                "heading_path": row["heading_path"] or "",
                "body": text,
                "metadata_json": json.dumps(metadata, sort_keys=True),
                "source_sha256": row["source_sha256"],
            }
        )
    return chunks


def media_chunks_for_root(
    *, root_id: str, scope_id: str, chunk_profile: str
) -> list[dict[str, Any]]:
    """Text chunks for media assets: caption, media-kind, and filename text.

    Lets media participate in `search text` / `semantic` / `hybrid` without an
    image model. Each chunk references its media asset, not a document object.
    """

    sql = """
        SELECT a.asset_id, si.source_item_id, si.relative_path, sr.root_label,
               si.media_type, si.source_sha256,
               cap.value_text AS caption, knd.value_text AS media_kind
        FROM "media_assets" a
        JOIN "source_items" si ON si.source_item_id = a.source_item_id
        JOIN "source_roots" sr ON sr.root_id = si.root_id
        LEFT JOIN "media_observations" cap
            ON cap.asset_id = a.asset_id AND cap.observation_kind = 'caption'
        LEFT JOIN "media_observations" knd
            ON knd.asset_id = a.asset_id AND knd.observation_kind = 'media_kind'
        WHERE si.root_id = ?
          AND si.inventory_status IN ('current', 'unchanged', 'changed')
        ORDER BY si.relative_path, a.asset_id
    """
    with catalog_connection() as conn:
        rows = conn.execute(sql, (root_id,)).fetchall()

    chunks: list[dict[str, Any]] = []
    for row in rows:
        asset_id = row["asset_id"]
        relative_path = row["relative_path"]
        caption = row["caption"]
        media_kind = row["media_kind"]
        stem = Path(relative_path).stem.replace("_", " ").replace("-", " ")
        body_parts = [part for part in (caption, media_kind, stem) if part]
        body = " ".join(" ".join(str(part).split()) for part in body_parts)
        if not body:
            continue
        metadata = {
            "root_id": root_id,
            "root_label": row["root_label"],
            "source_item_id": row["source_item_id"],
            "relative_path": relative_path,
            "media_type": row["media_type"],
        }
        chunk_id = stable_id("mchunk", scope_id, asset_id, chunk_profile)
        chunks.append(
            {
                "chunk_id": chunk_id,
                "doc_id": asset_id,
                "object_id": "",
                "asset_id": asset_id,
                "ref": evidence_ref("media_assets", asset_id),
                "scope_id": scope_id,
                "chunk_profile": chunk_profile,
                "content_type": "media_caption" if caption else "media_metadata",
                "page_start": None,
                "page_end": None,
                "title": Path(relative_path).stem,
                "heading_path": "",
                "body": body,
                "metadata_json": json.dumps(metadata, sort_keys=True),
                "source_sha256": row["source_sha256"],
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
