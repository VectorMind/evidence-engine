"""Routed text search: scope selection, RRF fusion, recursive deepening, traces."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from even.db import catalog_connection
from even.routing.medoids import _mean_vector
from even.routing.representative_search import (
    _search_global_representatives,
    _search_global_representatives_semantic,
    _search_global_representatives_siglip,
)
from even.routing.shared import (
    _embedding_profile_name,
    _fts_profile,
    _image_profile_name,
    _routing_defaults,
)


def _visual_route_from_images(
    image_paths: tuple[str, ...], *, limit: int
) -> dict[str, Any]:
    """Embed example images with SigLIP and rank albums by the mean query vector.

    The cross-modal probe entrypoint (B4): turns `search text --image` into a
    visual route that joins routing. Needs the image-search extra at query time.
    """

    from even import image_index

    if image_index.image_runtime_status()["status"] != "ok":
        return {"status": "unavailable", "reasons": ["image_runtime_unavailable"]}
    profile = _image_profile_name()
    try:
        embedder = image_index._load_embedder(profile)
        vectors = [
            embedder.embed_image(Path(path).read_bytes()) for path in image_paths
        ]
    except Exception:  # noqa: BLE001 - query embedding boundary.
        return {"status": "unavailable", "reasons": ["image_query_embed_failed"]}
    if not vectors:
        return {"status": "unavailable", "reasons": ["no_query_images"]}
    query_vector = _mean_vector(vectors)
    route = _search_global_representatives_siglip(
        query_vector, image_profile_name=profile, limit=limit
    )
    if route.get("status") == "ok":
        route["query_vector"] = query_vector
    return route


def _scoped_image_hits(
    query_vector: list[float] | None,
    scope_ids: list[str],
    *,
    profile: str,
    limit: int,
) -> list[dict[str, Any]]:
    """Image hits from the central image union, restricted to the routed scopes.

    Proves the image side of a cross-modal probe (spec: per-root FTS for text, the
    central image index for images), reusing the registered per-scope image stores.
    """

    if not query_vector or not scope_ids:
        return []
    from even import image_index

    wanted = set(scope_ids)
    stores = [
        store
        for store in image_index._current_image_stores(profile)
        if store.get("scope_id") in wanted
    ]
    hits: list[dict[str, Any]] = []
    for store in stores:
        result = image_index._search_one_image_store(store, query_vector, max(1, limit))
        if result["status"] == "ok":
            hits.extend(result["hits"])
    hits.sort(key=lambda hit: float(hit.get("distance", 0.0)))
    return hits[: max(1, limit)]


def search_text_with_routing(query: str, options: Any) -> dict[str, Any]:
    """Route text search through global representatives when they are current.

    The query-time budget controls fanout: ``low`` searches the single best scope,
    ``mid`` (default) the top routed scopes, ``high`` widens further. When deep
    search returns no hits, the representative hits are attached as
    ``routing_suggestions`` instead of an empty result.
    """

    from even import fts

    config = _routing_defaults()
    budget = _query_budget(options)
    top_k = int(config["representative_top_k"])
    max_scopes = _budget_max_scopes(budget, int(config["max_routed_scopes"]))

    fts_route = _search_global_representatives(query, fts_profile=_fts_profile(), limit=top_k)
    semantic_route = _search_global_representatives_semantic(
        query, embedding_profile_name=_embedding_profile_name(), limit=top_k
    )
    image_paths = tuple(getattr(options, "image_paths", ()) or ())
    visual_route = (
        _visual_route_from_images(image_paths, limit=top_k) if image_paths else None
    )
    fts_ok = fts_route.get("status") == "ok"
    semantic_ok = semantic_route.get("status") == "ok"
    visual_ok = bool(visual_route and visual_route.get("status") == "ok")

    # Single-route FTS path (no vector route active) keeps the original shape.
    if fts_ok and not semantic_ok and not visual_ok:
        return _routed_fts_only(query, options, fts_route, max_scopes, budget, config)

    if not (fts_ok or semantic_ok or visual_ok):
        fallback = fts.search_all_text_indexes(query, options)
        fallback["route_trace"] = _fallback_trace(
            fts_route.get("reasons", [])
            or semantic_route.get("reasons", [])
            or (visual_route.get("reasons", []) if visual_route else [])
        )
        return _finalize_route(fallback, budget)

    # Fused multi-route path (semantic and/or SigLIP visual route is current).
    routes: list[dict[str, Any]] = []
    hit_lists: list[tuple[str, list[dict[str, Any]]]] = []
    route_specs: list[tuple[str, dict[str, Any]]] = [
        ("global_representative_fts", fts_route),
        ("global_representative_semantic", semantic_route),
    ]
    if visual_route is not None:
        route_specs.append(("global_representative_siglip", visual_route))
    for mode, route in route_specs:
        if route.get("status") == "ok":
            routes.append(
                {
                    "mode": mode,
                    "status": "used",
                    "representative_index_uri": route.get("representative_index_uri"),
                    "representative_hits": route.get("hits", [])[:12],
                }
            )
            hit_lists.append((mode, route.get("hits", [])))
        else:
            routes.append(
                {"mode": mode, "status": "unavailable", "reasons": route.get("reasons", [])}
            )

    fused = _fuse_representative_hits(hit_lists)
    selected_scopes = _selected_scopes(fused, max_scopes=max_scopes)
    if not selected_scopes:
        fallback = fts.search_all_text_indexes(query, options)
        fallback["route_trace"] = _multi_route_trace(
            routes, selected_scopes, None, budget,
            status="fallback_all_scopes",
            widening_status={
                "status": "fallback_all_scopes",
                "reasons": ["no_representative_scopes"],
                "skipped_rungs": [],
            },
            representative_hits=fused,
        )
        return _finalize_route(fallback, budget, fused)

    scope_ids = [scope["scope_id"] for scope in selected_scopes]
    scoped = fts.search_all_text_indexes(query, options, scope_ids=scope_ids)
    if visual_ok:
        # Cross-modal probe: prove the image side against the routed scopes and
        # return those hits alongside the text hits. The visual route justified the
        # scopes, so weak text alone does not trigger an all-scopes text fallback.
        image_hits = _scoped_image_hits(
            visual_route.get("query_vector"),
            scope_ids,
            profile=_image_profile_name(),
            limit=int(getattr(options, "limit", 30) or 30),
        )
        scoped["hits"] = list(scoped.get("hits", [])) + image_hits
        scoped.setdefault("counts", {})["image_hits_returned"] = len(image_hits)
    weak_reasons = (
        []
        if visual_ok
        else _weak_route_reasons(
            representative_hits=fused, deep_hits=scoped.get("hits", []), config=config
        )
    )
    if weak_reasons:
        fallback = fts.search_all_text_indexes(query, options)
        fallback["route_trace"] = _multi_route_trace(
            routes, selected_scopes, scoped, budget,
            status="fallback_all_scopes",
            widening_status={
                "status": "fallback_all_scopes",
                "reasons": weak_reasons,
                "skipped_rungs": [],
            },
            representative_hits=fused,
        )
        return _finalize_route(fallback, budget, fused)

    scoped["route_trace"] = _multi_route_trace(
        routes, selected_scopes, scoped, budget,
        status="used",
        widening_status={"status": "not_needed", "reasons": [], "skipped_rungs": []},
        representative_hits=fused,
    )
    return _finalize_route(scoped, budget, fused)


def _routed_fts_only(
    query: str,
    options: Any,
    route: dict[str, Any],
    max_scopes: int,
    budget: str,
    config: dict[str, Any],
) -> dict[str, Any]:
    from even import fts

    suggestions = route["hits"]
    selected_scopes = _selected_scopes(route["hits"], max_scopes=max_scopes)
    if not selected_scopes:
        fallback = fts.search_all_text_indexes(query, options)
        fallback["route_trace"] = _fallback_trace(["no_representative_scopes"])
        return _finalize_route(fallback, budget, suggestions)

    scoped = fts.search_all_text_indexes(
        query, options, scope_ids=[scope["scope_id"] for scope in selected_scopes]
    )
    weak_reasons = _weak_route_reasons(
        representative_hits=route["hits"], deep_hits=scoped.get("hits", []), config=config
    )
    if weak_reasons:
        fallback = fts.search_all_text_indexes(query, options)
        fallback["route_trace"] = _route_trace(
            route=route,
            selected_scopes=selected_scopes,
            deep_result=scoped,
            budget=budget,
            status="fallback_all_scopes",
            widening_status={
                "status": "fallback_all_scopes",
                "reasons": weak_reasons,
                "skipped_rungs": [],
            },
        )
        return _finalize_route(fallback, budget, suggestions)

    scoped["route_trace"] = _route_trace(
        route=route,
        selected_scopes=selected_scopes,
        deep_result=scoped,
        budget=budget,
        status="used",
        widening_status={"status": "not_needed", "reasons": [], "skipped_rungs": []},
    )
    return _finalize_route(scoped, budget, suggestions)


def _fuse_representative_hits(
    hit_lists: list[tuple[str, list[dict[str, Any]]]], k: int = 60
) -> list[dict[str, Any]]:
    """Reciprocal-rank fusion of representative hit lists into one ranking (F4)."""

    entries: dict[str, dict[str, Any]] = {}
    for mode, hits in hit_lists:
        for hit in hits:
            summary_id = hit.get("summary_id")
            rank = int(hit.get("rank") or 0)
            if not summary_id or rank <= 0:
                continue
            entry = entries.setdefault(
                str(summary_id),
                {"score": 0.0, "hit": hit, "modes": set(), "best_rank": rank},
            )
            entry["score"] += 1.0 / (k + rank)
            entry["modes"].add(mode)
            if rank < entry["best_rank"]:
                entry["best_rank"] = rank
                entry["hit"] = hit
    ordered = sorted(
        entries.values(),
        key=lambda entry: (-entry["score"], str(entry["hit"].get("summary_id"))),
    )
    fused = []
    for rank, entry in enumerate(ordered, start=1):
        hit = dict(entry["hit"])
        hit["rank"] = rank
        hit["rrf_score"] = round(entry["score"], 6)
        hit["contributing_modes"] = sorted(entry["modes"])
        fused.append(hit)
    return fused


def _multi_route_trace(
    routes: list[dict[str, Any]],
    selected_scopes: list[dict[str, Any]],
    deep_result: dict[str, Any] | None,
    budget: str,
    *,
    status: str,
    widening_status: dict[str, Any],
    representative_hits: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    hits = deep_result.get("hits", []) if deep_result else []
    trace = {
        "budget": budget,
        "status": status,
        "routes": routes,
        "fused_selection": [
            {
                "scope_id": scope["scope_id"],
                "rank": scope.get("rank"),
                "rrf_score": scope.get("rrf_score"),
                "contributing_modes": scope.get("contributing_modes"),
            }
            for scope in selected_scopes
        ],
        "deep_searches": _deep_searches(selected_scopes, hits, deep_result or {}),
        "widening_status": widening_status,
    }
    recursive = _recursive_deepening_trace(
        representative_hits or [], selected_scopes, budget
    )
    if recursive is not None:
        trace["recursive_deepening"] = recursive
    return trace


def _query_budget(options: Any) -> str:
    budget = str(getattr(options, "budget", "mid") or "mid").lower()
    return budget if budget in {"low", "mid", "high"} else "mid"


def _budget_max_scopes(budget: str, base: int) -> int:
    """Map the query budget to routed-scope fanout. `high` recursive deepening into
    companion summaries is added once those exist (D2+); for now it widens fanout."""

    if budget == "low":
        return 1
    if budget == "high":
        return max(base, base * 2)
    return base


def _finalize_route(
    result: dict[str, Any], budget: str, suggestions: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    trace = result.get("route_trace")
    if isinstance(trace, dict):
        trace["budget"] = budget
    if suggestions and not result.get("hits"):
        result["routing_suggestions"] = suggestions
    return result


def _selected_scopes(
    hits: list[dict[str, Any]],
    *,
    max_scopes: int,
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    seen: set[str] = set()
    for hit in hits:
        scope_id = str(hit.get("scope_id") or "")
        if not scope_id or scope_id in seen:
            continue
        seen.add(scope_id)
        selected.append(
            {
                "scope_id": scope_id,
                "reason": "representative_hit",
                "rank": hit.get("rank"),
                "summary_id": hit.get("summary_id"),
                "rrf_score": hit.get("rrf_score"),
                "contributing_modes": hit.get("contributing_modes"),
            }
        )
        if len(selected) >= max(1, max_scopes):
            break
    return selected


def _weak_route_reasons(
    *,
    representative_hits: list[dict[str, Any]],
    deep_hits: list[dict[str, Any]],
    config: dict[str, Any],
) -> list[str]:
    reasons: list[str] = []
    hydrated_hits = [hit for hit in deep_hits if hit.get("ref")]
    if len(hydrated_hits) < int(config["min_hydrated_deep_hits"]):
        reasons.append("too_few_hydrated_deep_hits")
    if len(representative_hits) > 1:
        gap = float(representative_hits[0].get("score", 0.0)) - float(
            representative_hits[1].get("score", 0.0)
        )
        if gap < float(config["min_representative_score_gap"]):
            reasons.append("weak_representative_score_gap")
    return reasons


def _recursive_deepening_trace(
    representative_hits: list[dict[str, Any]],
    selected_scopes: list[dict[str, Any]],
    budget: str,
) -> dict[str, Any] | None:
    """For high-budget queries, expose lower summary nodes inside routed scopes."""

    if budget != "high" or not selected_scopes:
        return None
    scope_ids = [str(scope.get("scope_id") or "") for scope in selected_scopes]
    scope_ids = [scope_id for scope_id in scope_ids if scope_id]
    if not scope_ids:
        return None

    rows = _summary_region_rows(scope_ids)
    if rows is None:
        return {
            "status": "unavailable",
            "reason": "summary_nodes_unavailable",
            "matched_summaries": [],
            "region_listing": [],
        }
    lower_rows = [row for row in rows if int(row.get("summary_level") or 0) > 0]
    if not lower_rows:
        return {
            "status": "no_lower_summaries",
            "matched_summaries": [],
            "region_listing": [],
            "skipped_rungs": ["no_current_lower_summary_nodes"],
        }

    hit_rank = {
        str(hit.get("summary_id")): int(hit.get("rank") or 999_999)
        for hit in representative_hits
        if hit.get("summary_id")
    }
    matched = [row for row in lower_rows if row["summary_id"] in hit_rank]
    if not matched:
        matched = sorted(lower_rows, key=_summary_region_precedence)[:5]
    else:
        matched = sorted(
            matched,
            key=lambda row: (
                hit_rank.get(str(row["summary_id"]), 999_999),
                _summary_region_precedence(row),
            ),
        )

    return {
        "status": "used",
        "matched_summaries": [
            _summary_region_payload(row, hit_rank) for row in matched[:12]
        ],
        "region_listing": [
            _summary_region_payload(row, hit_rank)
            for row in sorted(lower_rows, key=_summary_region_precedence)[:24]
        ],
        "skipped_rungs": [],
    }


def _summary_region_rows(scope_ids: list[str]) -> list[dict[str, Any]] | None:
    placeholders = ", ".join("?" for _ in scope_ids)
    try:
        with catalog_connection() as conn:
            rows = conn.execute(
                f"""
                SELECT summary_id, root_id, scope_id, parent_summary_id, kind,
                       modality, media_kind, container_kind, summary_level, title,
                       source_count, sample_count, coverage_estimate, importance
                FROM "summary_nodes"
                WHERE summary_status = 'current'
                  AND scope_id IN ({placeholders})
                ORDER BY scope_id, summary_level, kind, title, summary_id
                """,
                scope_ids,
            ).fetchall()
    except sqlite3.Error:
        return None
    return [
        {
            "summary_id": row["summary_id"],
            "root_id": row["root_id"],
            "scope_id": row["scope_id"],
            "parent_summary_id": row["parent_summary_id"],
            "kind": row["kind"],
            "modality": row["modality"],
            "media_kind": row["media_kind"],
            "container_kind": row["container_kind"],
            "summary_level": int(row["summary_level"] or 0),
            "title": row["title"],
            "source_count": int(row["source_count"] or 0),
            "sample_count": int(row["sample_count"] or 0),
            "coverage_estimate": float(row["coverage_estimate"] or 0.0),
            "importance": row["importance"],
        }
        for row in rows
    ]


def _summary_region_precedence(row: dict[str, Any]) -> tuple[int, float, float, str]:
    importance = row.get("importance")
    importance_value = float(importance) if importance is not None else 0.0
    return (
        int(row.get("summary_level") or 0),
        -importance_value,
        -float(row.get("coverage_estimate") or 0.0),
        str(row.get("summary_id") or ""),
    )


def _summary_region_payload(
    row: dict[str, Any], hit_rank: dict[str, int]
) -> dict[str, Any]:
    summary_id = str(row.get("summary_id") or "")
    payload = {
        "summary_id": summary_id,
        "parent_summary_id": row.get("parent_summary_id"),
        "scope_id": row.get("scope_id"),
        "kind": row.get("kind"),
        "modality": row.get("modality"),
        "media_kind": row.get("media_kind"),
        "container_kind": row.get("container_kind"),
        "summary_level": row.get("summary_level"),
        "title": row.get("title"),
        "source_count": row.get("source_count"),
        "sample_count": row.get("sample_count"),
        "coverage_estimate": row.get("coverage_estimate"),
        "importance": row.get("importance"),
    }
    if summary_id in hit_rank:
        payload["representative_rank"] = hit_rank[summary_id]
    return payload


def _route_trace(
    *,
    route: dict[str, Any],
    selected_scopes: list[dict[str, Any]],
    deep_result: dict[str, Any],
    budget: str,
    status: str,
    widening_status: dict[str, Any],
) -> dict[str, Any]:
    hits = deep_result.get("hits", [])
    trace = {
        "mode": "global_representative_fts",
        "status": status,
        "representative_index_uri": route.get("representative_index_uri"),
        "representative_hits": route.get("hits", [])[:12],
        "selected_scopes": selected_scopes,
        "deep_searches": _deep_searches(selected_scopes, hits, deep_result),
        "widening_status": widening_status,
    }
    recursive = _recursive_deepening_trace(route.get("hits", []), selected_scopes, budget)
    if recursive is not None:
        trace["recursive_deepening"] = recursive
    return trace


def _fallback_trace(reasons: list[str]) -> dict[str, Any]:
    return {
        "mode": "fallback_all_current_fts",
        "status": "routing_unavailable",
        "reasons": reasons,
        "widening_status": {"status": "fallback_all_scopes"},
    }


def _deep_searches(
    selected_scopes: list[dict[str, Any]],
    hits: list[dict[str, Any]],
    deep_result: dict[str, Any],
) -> list[dict[str, Any]]:
    counts_by_scope: dict[str, int] = {}
    fts_by_scope: dict[str, str] = {}
    for hit in hits:
        scope_id = str(hit.get("scope_id") or "")
        if not scope_id:
            continue
        counts_by_scope[scope_id] = counts_by_scope.get(scope_id, 0) + 1
        if hit.get("fts_index_id"):
            fts_by_scope[scope_id] = str(hit["fts_index_id"])
    failures = {
        str(failure.get("scope_id") or ""): failure
        for failure in deep_result.get("failures", [])
    }
    searches = []
    for selected in selected_scopes:
        scope_id = str(selected["scope_id"])
        failure = failures.get(scope_id)
        searches.append(
            {
                "scope_id": scope_id,
                "fts_index_id": fts_by_scope.get(scope_id),
                "status": "failed" if failure else "ok",
                "hits_returned": counts_by_scope.get(scope_id, 0),
            }
        )
    return searches


