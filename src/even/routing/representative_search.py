"""Query the three global representative stores during routing."""

from __future__ import annotations

import sqlite3
from typing import Any

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
    _first,
    _json_field,
    _json_object,
    _tantivy_index_exists,
    _tantivy_runtime_status,
)
from even.routing.summary_store import _current_summary_rows, _select_budgeted_rows


def _search_global_representatives_semantic(
    query: str,
    *,
    embedding_profile_name: str,
    limit: int,
) -> dict[str, Any]:
    from even import semantic

    runtime = semantic._semantic_runtime_status()
    if runtime["status"] != "ok":
        return {"status": "unavailable", "reasons": [runtime["error_kind"]]}

    try:
        rows, _ = _select_budgeted_rows(_current_summary_rows())
    except sqlite3.Error:
        return {"status": "unavailable", "reasons": ["summary_nodes_unavailable"]}
    if not rows:
        return {"status": "unavailable", "reasons": ["no_current_summary_nodes"]}

    profile = embedding_profile(embedding_profile_name)
    if profile is None:
        return {"status": "unavailable", "reasons": ["unknown_embedding_profile"]}

    index_uri = _global_semantic_uri(embedding_profile_name)
    store_dir = workspace_root() / index_uri
    manifest_path = store_dir / GLOBAL_FTS_MANIFEST
    watermark = _representative_watermark(rows, embedding_profile_name, GLOBAL_SEMANTIC_TEMPLATE)
    if not _manifest_current(manifest_path, watermark, GLOBAL_SEMANTIC_TEMPLATE):
        return {
            "status": "unavailable",
            "reasons": ["global_representative_index_stale"],
            "representative_index_uri": index_uri,
        }
    if not semantic._lancedb_store_exists(store_dir, GLOBAL_SEMANTIC_TABLE):
        return {
            "status": "unavailable",
            "reasons": ["global_representative_index_missing"],
            "representative_index_uri": index_uri,
        }

    try:
        import lancedb  # type: ignore[import-not-found]

        query_vector = semantic._embed_query(profile, query)
        db = lancedb.connect(str(store_dir))
        table = db.open_table(GLOBAL_SEMANTIC_TABLE)
        results = table.search(query_vector).limit(max(1, limit)).to_list()
        hits = []
        for rank, row in enumerate(results, start=1):
            distance = float(row.get("_distance", 0.0) or 0.0)
            metadata = _json_object(row.get("metadata_json"))
            hits.append(
                {
                    "rank": rank,
                    "score": 1.0 / (1.0 + distance),
                    "summary_id": row.get("summary_id"),
                    "root_id": row.get("root_id"),
                    "scope_id": row.get("scope_id"),
                    "kind": row.get("kind"),
                    "modality": row.get("modality"),
                    "title": row.get("title"),
                    "root_label": metadata.get("root_label"),
                }
            )
    except Exception:  # noqa: BLE001 - backend boundary.
        return {
            "status": "unavailable",
            "reasons": ["global_representative_search_failed"],
            "representative_index_uri": index_uri,
        }
    return {"status": "ok", "representative_index_uri": index_uri, "hits": hits}


def _search_global_representatives_siglip(
    query_vector: list[float],
    *,
    image_profile_name: str,
    limit: int,
) -> dict[str, Any]:
    """Visual representative route: rank albums by a SigLIP query vector (B3).

    Returns fusable hits keyed by the owning album's `summary_id`+`scope_id`, so
    they slot into the shared RRF and scope selection. Used only for cross-modal /
    entity probes (C3); `search text` never calls this.
    """

    from even import semantic

    rows = _current_album_medoid_rows(image_profile_name)
    if not rows:
        return {"status": "unavailable", "reasons": ["no_media_representatives"]}

    index_uri = _global_siglip_uri(image_profile_name)
    store_dir = workspace_root() / index_uri
    manifest_path = store_dir / GLOBAL_FTS_MANIFEST
    watermark = _siglip_watermark(rows, image_profile_name)
    if not _manifest_current(manifest_path, watermark, GLOBAL_SIGLIP_TEMPLATE):
        return {
            "status": "unavailable",
            "reasons": ["global_representative_index_stale"],
            "representative_index_uri": index_uri,
        }
    if not semantic._lancedb_store_exists(store_dir, GLOBAL_SIGLIP_TABLE):
        return {
            "status": "unavailable",
            "reasons": ["global_representative_index_missing"],
            "representative_index_uri": index_uri,
        }

    try:
        import lancedb  # type: ignore[import-not-found]

        db = lancedb.connect(str(store_dir))
        table = db.open_table(GLOBAL_SIGLIP_TABLE)
        # Over-fetch medoids, then collapse to one hit per album by best distance.
        results = table.search(query_vector).limit(max(1, limit) * 4).to_list()
    except Exception:  # noqa: BLE001 - backend boundary.
        return {
            "status": "unavailable",
            "reasons": ["global_representative_search_failed"],
            "representative_index_uri": index_uri,
        }

    best: dict[str, dict[str, Any]] = {}
    for row in results:
        summary_id = str(row.get("summary_id") or "")
        if not summary_id:
            continue
        distance = float(row.get("_distance", 0.0) or 0.0)
        metadata = _json_object(row.get("metadata_json"))
        current = best.get(summary_id)
        if current is None or distance < current["distance"]:
            best[summary_id] = {
                "distance": distance,
                "summary_id": summary_id,
                "root_id": row.get("root_id"),
                "scope_id": row.get("scope_id"),
                "modality": row.get("modality"),
                "title": row.get("title"),
                "asset_id": row.get("asset_id"),
                "root_label": metadata.get("root_label"),
            }
    ordered = sorted(best.values(), key=lambda hit: (hit["distance"], hit["summary_id"]))
    hits = []
    for rank, hit in enumerate(ordered[: max(1, limit)], start=1):
        hits.append(
            {
                "rank": rank,
                "score": 1.0 / (1.0 + hit["distance"]),
                "summary_id": hit["summary_id"],
                "root_id": hit["root_id"],
                "scope_id": hit["scope_id"],
                "kind": "album_summary",
                "modality": hit["modality"],
                "title": hit["title"],
                "asset_id": hit["asset_id"],
                "root_label": hit["root_label"],
            }
        )
    return {"status": "ok", "representative_index_uri": index_uri, "hits": hits}


def _search_global_representatives(
    query: str,
    *,
    fts_profile: str,
    limit: int,
) -> dict[str, Any]:
    runtime = _tantivy_runtime_status()
    if runtime["status"] != "ok":
        return {"status": "unavailable", "reasons": [runtime["error_kind"]]}

    try:
        rows, _ = _select_budgeted_rows(_current_summary_rows())
    except sqlite3.Error:
        return {"status": "unavailable", "reasons": ["summary_nodes_unavailable"]}

    if not rows:
        return {"status": "unavailable", "reasons": ["no_current_summary_nodes"]}

    index_uri = _global_fts_uri(fts_profile)
    index_dir = workspace_root() / index_uri
    manifest_path = index_dir / GLOBAL_FTS_MANIFEST
    watermark = _representative_watermark(rows, fts_profile)
    if not _manifest_current(
        manifest_path, watermark, GLOBAL_FTS_TEMPLATE, fts_profile=fts_profile
    ):
        return {
            "status": "unavailable",
            "reasons": ["global_representative_index_stale"],
            "representative_index_uri": index_uri,
        }
    if not _tantivy_index_exists(index_dir):
        return {
            "status": "unavailable",
            "reasons": ["global_representative_index_missing"],
            "representative_index_uri": index_uri,
        }

    try:
        import tantivy  # type: ignore[import-not-found]

        index = tantivy.Index.open(str(index_dir))
        parsed, errors = index.parse_query_lenient(
            query,
            default_field_names=["title", "summary_text", "routing_payload"],
        )
        searcher = index.searcher()
        result = searcher.search(parsed, limit=max(1, limit))
        hits = []
        for rank, (score, doc_address) in enumerate(result.hits, start=1):
            stored = searcher.doc(doc_address).to_dict()
            metadata = _json_field(stored, "metadata_json")
            hits.append(
                {
                    "rank": rank,
                    "score": float(score),
                    "summary_id": _first(stored, "summary_id"),
                    "root_id": _first(stored, "root_id"),
                    "scope_id": _first(stored, "scope_id"),
                    "kind": _first(stored, "kind"),
                    "modality": _first(stored, "modality"),
                    "title": _first(stored, "title"),
                    "root_label": metadata.get("root_label"),
                }
            )
    except Exception:
        return {
            "status": "unavailable",
            "reasons": ["global_representative_search_failed"],
            "representative_index_uri": index_uri,
        }

    return {
        "status": "ok",
        "representative_index_uri": index_uri,
        "query_errors": [str(error) for error in errors],
        "hits": hits,
    }


