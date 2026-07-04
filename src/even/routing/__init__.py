"""Global representative routing for text search.

Builds root-level representative summaries, projects them into a fixed global
FTS map, and uses that map to choose root-scoped FTS indexes before deep search.
The summary nodes are routing hints only; final evidence still comes from the
root-scoped indexes.

Decomposed from a single ~3.6k-line ``routing.py``; see
``plans/2026-06/27-routing-decomposition``. This package ``__init__`` owns the
``index_routing`` / ``list_representatives`` orchestrators and is the stable
facade: it re-exports every name that callers (`cli.py`, `fts.py`) and
``tests/test_routing.py`` import, regardless of which submodule now owns it.
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Any

from even.catalog import ensure_catalog
from even.db import catalog_connection
from even.inventory import ScanOptions, scan_folder_to_catalog

# --- Facade re-exports (kept importable from ``even.routing``) ---------------
from even.routing.budget import (  # noqa: F401
    _blend_tokens_per_sec,
    _budget_skipped_summary,
    _build_budget_report,
    _estimate_tokens,
    _token_budget,
)
from even.routing.importance import _importance_prior, _parse_importance  # noqa: F401
from even.routing.media_summaries import _upsert_media_summary
from even.routing.medoids import _kmeans_medoids  # noqa: F401
from even.routing.representative_search import (
    _search_global_representatives_siglip,  # noqa: F401
)
from even.routing.representatives import (
    build_global_representative_fts,
    build_global_representative_semantic,
    build_global_representative_siglip,
)
from even.routing.search import (  # noqa: F401
    _fuse_representative_hits,
    search_text_with_routing,
)
from even.routing.shared import (
    RoutingIndexOptions,
    SummaryGenerationError,  # noqa: F401
    SummaryGenerator,
    _fts_profile,
    _media_summary_id,
    _routing_defaults,
    _tantivy_runtime_status,
)
from even.routing.summaries import (
    _blocked_summary_status,
    _combined_summary_counts,
    _generate_summary_text,
    _primary_summary,
    _summary_payloads,
    _upsert_root_summary,
)
from even.routing.summary_store import (  # noqa: F401
    _entry_budget,
    _select_budgeted_rows,
)

__all__ = [
    "RoutingIndexOptions",
    "SummaryGenerationError",
    "index_routing",
    "list_representatives",
    "search_text_with_routing",
]


def index_routing(
    path: Path,
    options: RoutingIndexOptions,
    *,
    summary_generator: SummaryGenerator | None = None,
) -> dict[str, Any]:
    """Build summary nodes and the global representative FTS map."""

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

    generator = summary_generator or _generate_summary_text
    max_build_seconds = (
        options.max_build_seconds
        if options.max_build_seconds is not None
        else float(_routing_defaults()["max_build_seconds"])
    )
    build_started = time.monotonic()

    # root_summary is the mandatory floor; it always runs. The media album is a
    # companion, so it is skipped once the per-root build budget is exhausted.
    document_summary = _upsert_root_summary(
        root_id=scan_result["root_id"],
        root_label=str(scan_result.get("root_label") or ""),
        scope_id=scan_result["scope_id"],
        options=options,
        summary_generator=generator,
    )
    if time.monotonic() - build_started >= max_build_seconds:
        media_summary = _budget_skipped_summary(
            _media_summary_id(scan_result["scope_id"])
        )
    else:
        media_summary = _upsert_media_summary(
            root_id=scan_result["root_id"],
            root_label=str(scan_result.get("root_label") or ""),
            scope_id=scan_result["scope_id"],
            options=options,
            summary_generator=generator,
        )
    document_summary["summary_type"] = "document"
    media_summary["summary_type"] = "media"
    summaries = [document_summary, media_summary]
    current_summaries = [
        summary
        for summary in summaries
        if summary.get("status") == "ok" and summary.get("summary_status") == "current"
    ]
    if not current_summaries:
        primary = _primary_summary(summaries)
        return {
            "status": _blocked_summary_status(summaries),
            "error_kind": primary.get("error_kind"),
            "index_backend": "routing",
            "root_id": scan_result["root_id"],
            "root_label": scan_result.get("root_label"),
            "scope_id": scan_result["scope_id"],
            "summary_id": primary["summary_id"],
            "summary_ids": [summary["summary_id"] for summary in summaries],
            "summary_status": primary["summary_status"],
            "auto_scan_status": scan_result["status"],
            "summaries": _summary_payloads(summaries),
            "counts": _combined_summary_counts(summaries),
            "message": primary.get("message", ""),
        }

    config = _routing_defaults()
    fts_profile = _fts_profile()
    projection = build_global_representative_fts(
        fts_profile=fts_profile,
        force=options.force,
    )
    if projection["status"] != "ok":
        return {
            "status": "failed",
            "error_kind": projection.get("error_kind", "global_fts_build_failed"),
            "index_backend": "routing",
            "root_id": scan_result["root_id"],
            "root_label": scan_result.get("root_label"),
            "scope_id": scan_result["scope_id"],
            "summary_id": current_summaries[0]["summary_id"],
            "summary_ids": [summary["summary_id"] for summary in summaries],
            "summary_status": "current",
            "auto_scan_status": scan_result["status"],
            "summaries": _summary_payloads(summaries),
            "global_representative_fts": projection,
            "counts": _combined_summary_counts(summaries),
        }

    semantic_projection = None
    siglip_projection = None
    if options.build_semantic:
        semantic_projection = build_global_representative_semantic(force=options.force)
        siglip_projection = build_global_representative_siglip(force=options.force)

    counts = _combined_summary_counts(summaries)
    counts.update(
        {
            "summary_nodes_indexed": projection["counts"]["summary_nodes_indexed"],
            "summary_nodes_unchanged": projection["counts"].get(
                "summary_nodes_unchanged", 0
            ),
            "representative_top_k": int(config["representative_top_k"]),
            "max_routed_scopes": int(config["max_routed_scopes"]),
        }
    )
    result = {
        "status": "ok",
        "index_backend": "routing",
        "root_id": scan_result["root_id"],
        "root_label": scan_result.get("root_label"),
        "scope_id": scan_result["scope_id"],
        "summary_id": current_summaries[0]["summary_id"],
        "summary_ids": [summary["summary_id"] for summary in summaries],
        "summary_status": "current",
        "summary_index_status": projection["index_status"],
        "global_representative_fts": projection,
        "auto_scan_status": scan_result["status"],
        "summaries": _summary_payloads(summaries),
        "representation_budget": _build_budget_report(max_build_seconds, build_started),
        "counts": counts,
    }
    if semantic_projection is not None:
        result["global_representative_semantic"] = semantic_projection
    if siglip_projection is not None:
        result["global_representative_siglip"] = siglip_projection
    return result


def list_representatives(path: Path | None = None) -> dict[str, Any]:
    """List the current representative summary_nodes hierarchy. No query, no model.

    Optional ``path`` filters to roots whose source URI contains it.
    """

    sql = """
        SELECT s.root_id, sr.root_label, s.summary_id, s.kind, s.modality,
               s.title, s.summary_level, s.importance
        FROM "summary_nodes" s
        JOIN "source_roots" sr ON sr.root_id = s.root_id
        WHERE s.summary_status = 'current'
    """
    params: list[Any] = []
    if path is not None:
        sql += " AND sr.source_uri LIKE ?"
        params.append(f"%{path}%")
    sql += " ORDER BY sr.root_label, s.root_id, s.summary_level, s.kind, s.summary_id"
    try:
        with catalog_connection() as conn:
            rows = conn.execute(sql, params).fetchall()
    except sqlite3.Error:
        return {"status": "deferred", "error_kind": "catalog_unavailable", "roots": []}

    roots: dict[str, dict[str, Any]] = {}
    for row in rows:
        root_id = row["root_id"]
        root = roots.setdefault(
            root_id,
            {"root_id": root_id, "root_label": row["root_label"], "nodes": []},
        )
        root["nodes"].append(
            {
                "summary_id": row["summary_id"],
                "kind": row["kind"],
                "modality": row["modality"],
                "title": row["title"] or row["root_label"] or root_id,
                "summary_level": int(row["summary_level"] or 0),
                "importance": row["importance"],
            }
        )
    root_list = list(roots.values())
    return {
        "status": "ok",
        "roots": root_list,
        "counts": {
            "roots": len(root_list),
            "summary_nodes": sum(len(root["nodes"]) for root in root_list),
        },
    }

