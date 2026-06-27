"""Build the three global representative stores (FTS / semantic / SigLIP)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from even.catalog import CATALOG_SCHEMA_VERSION
from even.config import embedding_profile
from even.paths import workspace_root
from even.routing.representative_store import (
    _current_album_medoid_rows,
    _global_fts_uri,
    _global_semantic_uri,
    _global_siglip_uri,
    _manifest_current,
    _representative_watermark,
    _siglip_watermark,
)
from even.routing.shared import (
    GLOBAL_FTS_MANIFEST,
    GLOBAL_FTS_TEMPLATE,
    GLOBAL_SEMANTIC_TABLE,
    GLOBAL_SEMANTIC_TEMPLATE,
    GLOBAL_SIGLIP_TABLE,
    GLOBAL_SIGLIP_TEMPLATE,
    _embedding_profile_name,
    _fts_profile,
    _image_profile_name,
    _iso,
    _tantivy_index_exists,
    _tantivy_runtime_status,
    _utc_now,
)
from even.routing.summary_store import (
    _current_summary_rows,
    _representation_policy_version,
    _select_budgeted_rows,
)


def build_global_representative_fts(
    *,
    fts_profile: str | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Build the fixed-path global FTS projection from current summary nodes."""

    runtime = _tantivy_runtime_status()
    if runtime["status"] != "ok":
        return runtime

    profile = fts_profile or _fts_profile()
    rows, overflow = _select_budgeted_rows(_current_summary_rows())
    index_uri = _global_fts_uri(profile)
    index_dir = workspace_root() / index_uri
    manifest_path = index_dir / GLOBAL_FTS_MANIFEST
    watermark = _representative_watermark(rows, profile)

    if not rows:
        return {
            "status": "deferred",
            "error_kind": "no_current_summary_nodes",
            "index_uri": index_uri,
            "template_name": GLOBAL_FTS_TEMPLATE,
            "counts": {"summary_nodes_planned": 0, "summary_nodes_indexed": 0},
        }

    if (
        not force
        and _manifest_current(
            manifest_path, watermark, GLOBAL_FTS_TEMPLATE, fts_profile=profile
        )
        and _tantivy_index_exists(index_dir)
    ):
        return {
            "status": "ok",
            "index_backend": "routing",
            "index_status": "current",
            "index_uri": index_uri,
            "template_name": GLOBAL_FTS_TEMPLATE,
            "source_high_watermark": watermark,
            "counts": {
                "summary_nodes_planned": len(rows),
                "summary_nodes_indexed": 0,
                "summary_nodes_unchanged": len(rows),
                "summary_nodes_overflow": len(overflow),
            },
        }

    build = _write_global_fts_index(index_dir, rows)
    if build["status"] != "ok":
        return {
            "status": "failed",
            "error_kind": build["error_kind"],
            "index_uri": index_uri,
            "template_name": GLOBAL_FTS_TEMPLATE,
            "redacted_detail": build.get("redacted_detail"),
            "counts": {
                "summary_nodes_planned": len(rows),
                "summary_nodes_indexed": 0,
            },
        }

    _write_manifest(
        manifest_path,
        template=GLOBAL_FTS_TEMPLATE,
        profile_field="fts_profile",
        profile_value=profile,
        watermark=watermark,
        row_count=len(rows),
        extra={"overflow_count": len(overflow)},
    )
    return {
        "status": "ok",
        "index_backend": "routing",
        "index_status": "rebuilt" if force else "refreshed",
        "index_uri": index_uri,
        "template_name": GLOBAL_FTS_TEMPLATE,
        "source_high_watermark": watermark,
        "counts": {
            "summary_nodes_planned": len(rows),
            "summary_nodes_indexed": len(rows),
            "summary_nodes_unchanged": 0,
            "summary_nodes_overflow": len(overflow),
        },
    }


def build_global_representative_semantic(
    *,
    embedding_profile_name: str | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Build the fixed-path global semantic projection from current summary nodes.

    Embeds each selected unit's derived `routing_payload` fresh (DP1), over the
    identical budgeted unit set the FTS projection uses (backend parity)."""

    from even import semantic

    runtime = semantic._semantic_runtime_status()
    if runtime["status"] != "ok":
        return runtime

    profile_name = embedding_profile_name or _embedding_profile_name()
    profile = embedding_profile(profile_name)
    if profile is None or profile.get("provider") != "fastembed":
        return {
            "status": "failed",
            "error_kind": "unsupported_embedding_profile",
            "embedding_profile": profile_name,
        }

    rows, overflow = _select_budgeted_rows(_current_summary_rows())
    index_uri = _global_semantic_uri(profile_name)
    store_dir = workspace_root() / index_uri
    manifest_path = store_dir / GLOBAL_FTS_MANIFEST
    watermark = _representative_watermark(rows, profile_name, GLOBAL_SEMANTIC_TEMPLATE)

    if not rows:
        return {
            "status": "deferred",
            "error_kind": "no_current_summary_nodes",
            "index_uri": index_uri,
            "template_name": GLOBAL_SEMANTIC_TEMPLATE,
            "counts": {"summary_nodes_planned": 0, "summary_nodes_indexed": 0},
        }

    if (
        not force
        and _manifest_current(manifest_path, watermark, GLOBAL_SEMANTIC_TEMPLATE)
        and semantic._lancedb_store_exists(store_dir, GLOBAL_SEMANTIC_TABLE)
    ):
        return {
            "status": "ok",
            "index_backend": "routing",
            "index_status": "current",
            "index_uri": index_uri,
            "embedding_profile": profile_name,
            "template_name": GLOBAL_SEMANTIC_TEMPLATE,
            "source_high_watermark": watermark,
            "counts": {
                "summary_nodes_planned": len(rows),
                "summary_nodes_indexed": 0,
                "summary_nodes_unchanged": len(rows),
                "summary_nodes_overflow": len(overflow),
            },
        }

    build = _write_global_semantic_index(store_dir, rows, profile, profile_name)
    if build["status"] != "ok":
        return {
            "status": "failed",
            "error_kind": build["error_kind"],
            "index_uri": index_uri,
            "template_name": GLOBAL_SEMANTIC_TEMPLATE,
            "redacted_detail": build.get("redacted_detail"),
            "counts": {"summary_nodes_planned": len(rows), "summary_nodes_indexed": 0},
        }

    _write_manifest(
        manifest_path,
        template=GLOBAL_SEMANTIC_TEMPLATE,
        profile_field="embedding_profile",
        profile_value=profile_name,
        watermark=watermark,
        row_count=len(rows),
        extra={"overflow_count": len(overflow)},
    )
    return {
        "status": "ok",
        "index_backend": "routing",
        "index_status": "rebuilt" if force else "refreshed",
        "index_uri": index_uri,
        "embedding_profile": profile_name,
        "template_name": GLOBAL_SEMANTIC_TEMPLATE,
        "source_high_watermark": watermark,
        "counts": {
            "summary_nodes_planned": len(rows),
            "summary_nodes_indexed": len(rows),
            "summary_nodes_unchanged": 0,
            "summary_nodes_overflow": len(overflow),
        },
    }


def _write_global_semantic_index(
    store_dir: Path,
    rows: list[dict[str, Any]],
    profile: dict[str, Any],
    profile_name: str,
) -> dict[str, Any]:
    from even import semantic

    try:
        import lancedb  # type: ignore[import-not-found]

        payloads = [str(row.get("routing_payload") or "") for row in rows]
        vectors = semantic._embed_passages(profile, payloads)
        data = [
            _semantic_row(row, vector, profile_name)
            for row, vector in zip(rows, vectors)
        ]
        store_dir.mkdir(parents=True, exist_ok=True)
        with semantic._quiet_output():
            db = lancedb.connect(str(store_dir))
            db.create_table(GLOBAL_SEMANTIC_TABLE, data=data, mode="overwrite")
    except Exception as exc:  # noqa: BLE001 - backend boundary.
        return {
            "status": "failed",
            "error_kind": "global_semantic_write_failed",
            "redacted_detail": exc.__class__.__name__,
        }
    return {"status": "ok"}


def _semantic_row(
    row: dict[str, Any], vector: list[float], profile_name: str
) -> dict[str, Any]:
    return {
        "summary_id": row["summary_id"],
        "root_id": row["root_id"],
        "scope_id": row["scope_id"],
        "kind": str(row.get("kind") or ""),
        "modality": str(row.get("modality") or ""),
        "embedding_profile": profile_name,
        "vector": vector,
        "title": str(row.get("title") or ""),
        "routing_payload": str(row.get("routing_payload") or ""),
        "source_refs_json": row.get("source_refs_json") or "[]",
        "metadata_json": row.get("metadata_json") or "{}",
    }


def _siglip_row(row: dict[str, Any], image_profile_name: str) -> dict[str, Any]:
    return {
        "summary_id": row["summary_id"],
        "root_id": row["root_id"],
        "scope_id": row["scope_id"],
        "asset_id": row["asset_id"],
        "image_profile": image_profile_name,
        "vector": row["vector"],
        "modality": str(row.get("modality") or "image"),
        "title": str(row.get("title") or ""),
        "relative_path": str(row.get("relative_path") or ""),
        "metadata_json": json.dumps(
            {"root_label": row.get("root_label"), "importance": row.get("importance")},
            sort_keys=True,
        ),
    }


def build_global_representative_siglip(
    *,
    image_profile_name: str | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Build the global SigLIP representative store from album medoids (B2).

    Reuses the medoids' per-scope proof vectors (no re-embed, no torch). Separate
    space per image profile (S3), budgeted by the medoid `k` clamp applied at
    summary build, not by the text `max_entries`.
    """

    profile_name = image_profile_name or _image_profile_name()
    rows = _current_album_medoid_rows(profile_name)
    index_uri = _global_siglip_uri(profile_name)
    store_dir = workspace_root() / index_uri
    manifest_path = store_dir / GLOBAL_FTS_MANIFEST

    if not rows:
        return {
            "status": "deferred",
            "error_kind": "no_media_representatives",
            "index_uri": index_uri,
            "template_name": GLOBAL_SIGLIP_TEMPLATE,
            "counts": {"media_representatives_planned": 0, "media_representatives_indexed": 0},
        }

    watermark = _siglip_watermark(rows, profile_name)
    albums = len({row["summary_id"] for row in rows})

    from even import semantic

    if (
        not force
        and _manifest_current(manifest_path, watermark, GLOBAL_SIGLIP_TEMPLATE)
        and semantic._lancedb_store_exists(store_dir, GLOBAL_SIGLIP_TABLE)
    ):
        return {
            "status": "ok",
            "index_backend": "routing",
            "index_status": "current",
            "index_uri": index_uri,
            "image_profile": profile_name,
            "template_name": GLOBAL_SIGLIP_TEMPLATE,
            "source_high_watermark": watermark,
            "counts": {
                "media_representatives_planned": len(rows),
                "media_representatives_indexed": 0,
                "media_representatives_unchanged": len(rows),
                "albums": albums,
            },
        }

    build = _write_global_siglip_index(store_dir, rows, profile_name)
    if build["status"] != "ok":
        return {
            "status": "failed",
            "error_kind": build["error_kind"],
            "index_uri": index_uri,
            "template_name": GLOBAL_SIGLIP_TEMPLATE,
            "redacted_detail": build.get("redacted_detail"),
            "counts": {"media_representatives_planned": len(rows), "media_representatives_indexed": 0},
        }

    _write_manifest(
        manifest_path,
        template=GLOBAL_SIGLIP_TEMPLATE,
        profile_field="image_profile",
        profile_value=profile_name,
        watermark=watermark,
        row_count=len(rows),
        extra={"album_count": albums},
    )
    return {
        "status": "ok",
        "index_backend": "routing",
        "index_status": "rebuilt" if force else "refreshed",
        "index_uri": index_uri,
        "image_profile": profile_name,
        "template_name": GLOBAL_SIGLIP_TEMPLATE,
        "source_high_watermark": watermark,
        "counts": {
            "media_representatives_planned": len(rows),
            "media_representatives_indexed": len(rows),
            "media_representatives_unchanged": 0,
            "albums": albums,
        },
    }


def _write_global_siglip_index(
    store_dir: Path, rows: list[dict[str, Any]], image_profile_name: str
) -> dict[str, Any]:
    from even import semantic

    try:
        import lancedb  # type: ignore[import-not-found]

        data = [_siglip_row(row, image_profile_name) for row in rows]
        store_dir.mkdir(parents=True, exist_ok=True)
        with semantic._quiet_output():
            db = lancedb.connect(str(store_dir))
            db.create_table(GLOBAL_SIGLIP_TABLE, data=data, mode="overwrite")
    except Exception as exc:  # noqa: BLE001 - backend boundary.
        return {
            "status": "failed",
            "error_kind": "global_siglip_write_failed",
            "redacted_detail": exc.__class__.__name__,
        }
    return {"status": "ok"}


def _write_global_fts_index(
    index_dir: Path,
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    try:
        import tantivy  # type: ignore[import-not-found]

        index_dir.mkdir(parents=True, exist_ok=True)
        index = tantivy.Index(_global_fts_schema(), path=str(index_dir), reuse=True)
        writer = index.writer(heap_size=50_000_000)
        writer.delete_all_documents()
        for row in rows:
            document = tantivy.Document()
            for field in (
                "summary_id",
                "root_id",
                "scope_id",
                "kind",
                "modality",
                "title",
                "summary_text",
                "routing_payload",
                "source_refs_json",
                "metadata_json",
            ):
                document.add_text(field, str(row.get(field) or ""))
            writer.add_document(document)
        writer.commit()
        index.reload()
    except Exception as exc:  # noqa: BLE001 - backend boundary.
        return {
            "status": "failed",
            "error_kind": "global_fts_write_failed",
            "redacted_detail": exc.__class__.__name__,
        }
    return {"status": "ok"}


def _global_fts_schema() -> Any:
    import tantivy  # type: ignore[import-not-found]

    builder = tantivy.SchemaBuilder()
    for field in ("summary_id", "root_id", "scope_id", "kind", "modality"):
        builder.add_text_field(
            field,
            stored=True,
            tokenizer_name="raw",
            index_option="basic",
        )
    builder.add_text_field("title", stored=True, tokenizer_name="default")
    builder.add_text_field("summary_text", stored=True, tokenizer_name="default")
    builder.add_text_field("routing_payload", stored=True, tokenizer_name="default")
    builder.add_text_field(
        "source_refs_json",
        stored=True,
        tokenizer_name="raw",
        index_option="basic",
    )
    builder.add_text_field(
        "metadata_json",
        stored=True,
        tokenizer_name="raw",
        index_option="basic",
    )
    return builder.build()


def _write_manifest(
    manifest_path: Path,
    *,
    template: str,
    profile_field: str,
    profile_value: str,
    watermark: str,
    row_count: int,
    extra: dict[str, Any] | None = None,
) -> None:
    """Write a global representative manifest shared by all three backends.

    `profile_field` names the backend's profile key (`fts_profile`,
    `embedding_profile`, or `image_profile`); `extra` carries the backend's
    extra count (`overflow_count` for text, `album_count` for media).
    """

    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "built_at": _iso(_utc_now()),
        profile_field: profile_value,
        "template_name": template,
        "summary_watermark": watermark,
        "row_count": row_count,
        "representation_policy_version": _representation_policy_version(),
        "schema_version": CATALOG_SCHEMA_VERSION,
    }
    if extra:
        payload.update(extra)
    manifest_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8"
    )


