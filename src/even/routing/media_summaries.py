"""Media album and media-cluster summary generation."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from even.db import catalog_connection
from even.references import evidence_ref
from even.routing.budget import _generate_and_calibrate
from even.routing.importance import (
    _importance_learn_threshold,
    _importance_prior,
    _learn_low_prior,
    _parse_importance,
    _resolve_importance,
)
from even.routing.medoids import _album_medoids, _media_asset_clusters
from even.routing.shared import (
    MEDIA_CLUSTER_PROFILE,
    MEDIA_PROMPT_VERSION,
    MEDIA_SUMMARY_PROFILE,
    RoutingIndexOptions,
    SummaryGenerationError,
    SummaryGenerator,
    _clean_routing_meta,
    _coverage,
    _empty_watermark,
    _image_profile_name,
    _iso,
    _media_summary_id,
    _routing_defaults,
    _utc_now,
)
from even.routing.summary_store import (
    _root_source_item_id,
    _summary_state,
    _upsert_summary_row,
)


def _upsert_media_summary(
    *,
    root_id: str,
    root_label: str,
    scope_id: str,
    options: RoutingIndexOptions,
    summary_generator: SummaryGenerator,
) -> dict[str, Any]:
    config = _routing_defaults()
    sample_policy = "media_album_v1"
    model = (
        options.summary_model
        or os.environ.get("EVEN_SUMMARY_MODEL")
        or str(config["summary_model"])
    )
    url = (
        options.summary_ollama_url
        or os.environ.get("EVEN_SUMMARY_OLLAMA_URL")
        or str(config["summary_ollama_url"])
    )
    timeout = float(config["summary_timeout_seconds"])
    max_assets = int(options.limit or config["summary_sample_chunks_default"])
    assets = _media_assets_for_root(root_id)
    summary_id = _media_summary_id(scope_id)
    now = _iso(_utc_now())
    state = _summary_state(summary_id)

    if not assets:
        written = 0
        _delete_stale_media_clusters(summary_id, set(), now)
        if state:
            _upsert_summary_row(
                summary_id=summary_id,
                root_id=root_id,
                scope_id=scope_id,
                source_item_id=_root_source_item_id(root_id),
                title=f"{root_label or scope_id} media",
                summary_text="",
                routing_meta={},
                source_refs=[],
                source_count=0,
                sample_count=0,
                coverage_estimate=0.0,
                sample_policy=sample_policy,
                producer="none",
                profile=MEDIA_SUMMARY_PROFILE,
                watermark=_empty_watermark(root_id, scope_id, sample_policy),
                status="deleted",
                attrs={"error_kind": "no_media_summary_inputs"},
                now=now,
                created_at=state.get("created_at"),
                kind="album_summary",
                modality="mixed",
                container_kind="root",
            )
            written = 1
        return {
            "status": "deferred",
            "error_kind": "no_media_summary_inputs",
            "message": "No current media assets were available for routing.",
            "summary_id": summary_id,
            "summary_status": "deferred",
            "index_status": "deferred",
            "counts": {
                "media_assets_considered": 0,
                "media_assets_sampled": 0,
                "summary_nodes_written": written,
            },
        }

    watermark = _media_high_watermark(
        assets,
        sample_policy,
        model,
        str(max_assets),
        MEDIA_PROMPT_VERSION,
    )
    if (
        not options.force
        and state
        and state.get("summary_status") == "current"
        and state.get("source_high_watermark") == watermark
    ):
        cluster_result = _upsert_media_cluster_summaries(
            root_id=root_id,
            root_label=root_label,
            scope_id=scope_id,
            parent_summary_id=summary_id,
            assets=assets,
            now=now,
        )
        return {
            "status": "ok",
            "summary_id": summary_id,
            "summary_status": "current",
            "index_status": "current",
            "counts": {
                "media_assets_considered": len(assets),
                "media_assets_sampled": 0,
                "media_clusters_considered": cluster_result["counts"][
                    "media_clusters_considered"
                ],
                "media_cluster_summaries_written": cluster_result["counts"][
                    "media_cluster_summaries_written"
                ],
                "summary_nodes_written": cluster_result["counts"][
                    "media_cluster_summaries_written"
                ],
            },
        }

    samples = _sample_media_assets(assets, max_assets=max_assets)
    prompt = _media_summary_prompt(
        root_label=root_label,
        samples=samples,
        max_chars=int(config["summary_prompt_max_chars"]),
        per_asset_chars=int(config["summary_sample_chars_per_chunk"]),
    )
    modality = _media_modality(assets)
    media_kind = _dominant_media_kind(assets)
    title = f"{root_label or scope_id} media"

    try:
        summary_text = _generate_and_calibrate(
            summary_generator, prompt, model=model, url=url, timeout=timeout
        )
    except SummaryGenerationError as exc:
        _delete_stale_media_clusters(summary_id, set(), now)
        _upsert_summary_row(
            summary_id=summary_id,
            root_id=root_id,
            scope_id=scope_id,
            source_item_id=_root_source_item_id(root_id),
            title=title,
            summary_text="",
            routing_meta=_media_routing_meta(root_label, samples),
            source_refs=_media_source_refs(samples),
            source_count=len(assets),
            sample_count=len(samples),
            coverage_estimate=_coverage(len(samples), len(assets)),
            sample_policy=sample_policy,
            producer=f"ollama:{model}",
            profile=MEDIA_SUMMARY_PROFILE,
            watermark=watermark,
            status=exc.status,
            attrs=_media_summary_attrs(
                assets,
                samples,
                {"error_kind": exc.error_kind, "message": exc.message},
            ),
            now=now,
            created_at=state.get("created_at") if state else None,
            kind="album_summary",
            modality=modality,
            media_kind=media_kind,
            container_kind="root",
            importance=_importance_prior(root_label, scope_id),
        )
        return {
            "status": exc.status,
            "error_kind": exc.error_kind,
            "message": exc.message,
            "summary_id": summary_id,
            "summary_status": exc.status,
            "index_status": exc.status,
            "counts": {
                "media_assets_considered": len(assets),
                "media_assets_sampled": len(samples),
                "summary_nodes_written": 1,
            },
        }

    summary_text, parsed_importance = _parse_importance(str(summary_text or ""))
    summary_text = " ".join(summary_text.split())
    importance = _resolve_importance(parsed_importance, root_label, scope_id)
    if parsed_importance is not None and parsed_importance < _importance_learn_threshold():
        _learn_low_prior(root_label)
    if not summary_text:
        _delete_stale_media_clusters(summary_id, set(), now)
        _upsert_summary_row(
            summary_id=summary_id,
            root_id=root_id,
            scope_id=scope_id,
            source_item_id=_root_source_item_id(root_id),
            title=title,
            summary_text="",
            routing_meta=_media_routing_meta(root_label, samples),
            source_refs=_media_source_refs(samples),
            source_count=len(assets),
            sample_count=len(samples),
            coverage_estimate=_coverage(len(samples), len(assets)),
            sample_policy=sample_policy,
            producer=f"ollama:{model}",
            profile=MEDIA_SUMMARY_PROFILE,
            watermark=watermark,
            status="failed",
            attrs=_media_summary_attrs(assets, samples, {"error_kind": "empty_summary"}),
            now=now,
            created_at=state.get("created_at") if state else None,
            kind="album_summary",
            modality=modality,
            media_kind=media_kind,
            container_kind="root",
            importance=importance,
        )
        return {
            "status": "failed",
            "error_kind": "empty_summary",
            "message": "The local summary model returned no text.",
            "summary_id": summary_id,
            "summary_status": "failed",
            "index_status": "failed",
            "counts": {
                "media_assets_considered": len(assets),
                "media_assets_sampled": len(samples),
                "summary_nodes_written": 1,
            },
        }

    _upsert_summary_row(
        summary_id=summary_id,
        root_id=root_id,
        scope_id=scope_id,
        source_item_id=_root_source_item_id(root_id),
        title=title,
        summary_text=summary_text,
        routing_meta=_media_routing_meta(root_label, samples),
        source_refs=_media_source_refs(samples),
        source_count=len(assets),
        sample_count=len(samples),
        coverage_estimate=_coverage(len(samples), len(assets)),
        sample_policy=sample_policy,
        producer=f"ollama:{model}",
        profile=MEDIA_SUMMARY_PROFILE,
        watermark=watermark,
        status="current",
        attrs=_media_summary_attrs(
            assets,
            samples,
            {
                "prompt_version": MEDIA_PROMPT_VERSION,
                "model": model,
                "ollama_url": url,
                **_album_medoids(scope_id),
            },
        ),
        now=now,
        created_at=state.get("created_at") if state else None,
        kind="album_summary",
        modality=modality,
        media_kind=media_kind,
        container_kind="root",
        importance=importance,
    )
    cluster_result = _upsert_media_cluster_summaries(
        root_id=root_id,
        root_label=root_label,
        scope_id=scope_id,
        parent_summary_id=summary_id,
        assets=assets,
        now=now,
    )
    return {
        "status": "ok",
        "summary_id": summary_id,
        "summary_status": "current",
        "index_status": "rebuilt" if options.force else "refreshed",
        "counts": {
            "media_assets_considered": len(assets),
            "media_assets_sampled": len(samples),
            "media_clusters_considered": cluster_result["counts"][
                "media_clusters_considered"
            ],
            "media_cluster_summaries_written": cluster_result["counts"][
                "media_cluster_summaries_written"
            ],
            "summary_nodes_written": 1
            + cluster_result["counts"]["media_cluster_summaries_written"],
        },
    }


def _upsert_media_cluster_summaries(
    *,
    root_id: str,
    root_label: str,
    scope_id: str,
    parent_summary_id: str,
    assets: list[dict[str, Any]],
    now: str,
) -> dict[str, Any]:
    clusters = _media_asset_clusters(scope_id, assets)
    current_ids = {cluster["summary_id"] for cluster in clusters}
    _delete_stale_media_clusters(parent_summary_id, current_ids, now)
    written = 0
    for cluster in clusters:
        members = cluster["assets"]
        source_refs = _media_source_refs(members)
        summary_text = _media_cluster_summary_text(cluster)
        state = _summary_state(cluster["summary_id"])
        watermark = _media_high_watermark(
            members,
            "media_cluster_siglip_v1",
            cluster["medoid_id"],
            _image_profile_name(),
        )
        if (
            state
            and state.get("summary_status") == "current"
            and state.get("source_high_watermark") == watermark
        ):
            continue
        _upsert_summary_row(
            summary_id=cluster["summary_id"],
            root_id=root_id,
            scope_id=scope_id,
            parent_summary_id=parent_summary_id,
            source_item_id=cluster["medoid"].get("source_item_id"),
            title=cluster["title"],
            summary_text=summary_text,
            routing_meta=_media_routing_meta(root_label, members),
            source_refs=source_refs,
            source_count=len(members),
            sample_count=len(members),
            coverage_estimate=_coverage(len(members), len(assets)),
            sample_policy="media_cluster_siglip_v1",
            producer="deterministic:siglip_cluster",
            profile=MEDIA_CLUSTER_PROFILE,
            watermark=watermark,
            status="current",
            attrs=_media_cluster_attrs(cluster),
            now=now,
            created_at=state["created_at"] if state else None,
            kind="media_cluster_summary",
            modality=_media_modality(members),
            media_kind=_dominant_media_kind(members),
            container_kind="cluster",
            summary_level=1,
            importance=_media_cluster_importance(members),
        )
        written += 1
    return {
        "status": "ok" if clusters else "deferred",
        "counts": {
            "media_clusters_considered": len(clusters),
            "media_cluster_summaries_written": written,
        },
    }


def _media_assets_for_root(root_id: str) -> list[dict[str, Any]]:
    sql = """
        SELECT a.asset_id, a.source_item_id, a.media_class, a.inspect_status,
               a.attrs_json, a.updated_at, si.relative_path, si.media_type,
               si.source_sha256, si.size_bytes,
               img.format AS image_format, img.width AS image_width,
               img.height AS image_height, img.megapixels AS image_megapixels,
               img.color_mode AS image_color_mode,
               img.captured_at AS image_captured_at,
               vid.container AS video_container,
               vid.video_codec AS video_codec, vid.audio_codec AS audio_codec,
               vid.width AS video_width, vid.height AS video_height,
               vid.duration_seconds AS video_duration_seconds,
               vid.frame_rate AS video_frame_rate,
               vid.captured_at AS video_captured_at,
               mdl.format AS model_format, mdl.vertex_count AS model_vertex_count,
               mdl.face_count AS model_face_count, mdl.units AS model_units,
               (
                   SELECT value_text
                   FROM "media_observations"
                   WHERE asset_id = a.asset_id
                     AND observation_kind = 'caption'
                   ORDER BY created_at DESC, observation_id DESC
                   LIMIT 1
               ) AS caption,
               (
                   SELECT value_text
                   FROM "media_observations"
                   WHERE asset_id = a.asset_id
                     AND observation_kind = 'media_kind'
                   ORDER BY created_at DESC, observation_id DESC
                   LIMIT 1
               ) AS media_kind
        FROM "media_assets" a
        JOIN "source_items" si ON si.source_item_id = a.source_item_id
        LEFT JOIN "image_metadata" img ON img.asset_id = a.asset_id
        LEFT JOIN "video_metadata" vid ON vid.asset_id = a.asset_id
        LEFT JOIN "model3d_metadata" mdl ON mdl.asset_id = a.asset_id
        WHERE si.root_id = ?
          AND si.inventory_status IN ('current', 'unchanged', 'changed')
        ORDER BY si.relative_path, a.asset_id
    """
    with catalog_connection() as conn:
        rows = conn.execute(sql, (root_id,)).fetchall()
    return [dict(row) for row in rows]


def _sample_media_assets(
    assets: list[dict[str, Any]], *, max_assets: int
) -> list[dict[str, Any]]:
    limit = max(1, int(max_assets or 1))
    ordered = sorted(
        assets,
        key=lambda item: (
            str(item.get("media_class") or ""),
            str(item.get("relative_path") or ""),
            str(item.get("asset_id") or ""),
        ),
    )
    by_class: dict[str, list[dict[str, Any]]] = {}
    for asset in ordered:
        by_class.setdefault(str(asset.get("media_class") or "other"), []).append(asset)

    samples: list[dict[str, Any]] = []
    for media_class in sorted(by_class):
        if len(samples) >= limit:
            break
        samples.append(by_class[media_class][0])
    if len(samples) < limit:
        seen = {str(sample.get("asset_id")) for sample in samples}
        for asset in ordered:
            if len(samples) >= limit:
                break
            if str(asset.get("asset_id")) not in seen:
                samples.append(asset)
    return samples


def _media_summary_prompt(
    *,
    root_label: str,
    samples: list[dict[str, Any]],
    max_chars: int,
    per_asset_chars: int,
) -> str:
    rows = []
    for index, asset in enumerate(samples, start=1):
        caption = " ".join(str(asset.get("caption") or "").split())[:per_asset_chars]
        rows.append(
            {
                "n": index,
                "path": asset.get("relative_path") or "",
                "media_class": asset.get("media_class") or "",
                "media_type": asset.get("media_type") or "",
                "media_kind": asset.get("media_kind") or "",
                "caption": caption,
                "metadata": _media_metadata_facets(asset),
            }
        )
    prompt = (
        "Write a concise routing summary for a local media root. "
        "Use only sampled filenames, existing captions, media-kind labels, "
        "and safe metadata. Do not infer unseen visual content. Do not claim "
        "complete coverage. Return 2-4 plain sentences focused on visual "
        "topics, media types, and terms that would help route future search "
        "queries. Then, on a final separate line, rate how important this root "
        "is to represent for search routing as 'IMPORTANCE: <value>' with value "
        "between 0 and 1. State the reason inside the summary itself only for "
        "extreme cases (clearly trivial or clearly central).\n\n"
        f"Root label: {root_label}\n\n"
        f"Sampled media assets:\n{json.dumps(rows, ensure_ascii=True, indent=2)}"
    )
    return prompt[:max_chars]


def _media_metadata_facets(asset: dict[str, Any]) -> dict[str, Any]:
    facets: dict[str, Any] = {}
    if asset.get("size_bytes") is not None:
        facets["size_bytes"] = asset["size_bytes"]
    if asset.get("image_width") and asset.get("image_height"):
        facets["dimensions"] = f"{asset['image_width']}x{asset['image_height']}"
    if asset.get("image_format"):
        facets["image_format"] = asset["image_format"]
    if asset.get("image_color_mode"):
        facets["image_color_mode"] = asset["image_color_mode"]
    if asset.get("image_captured_at"):
        facets["captured_at"] = asset["image_captured_at"]
    if asset.get("video_width") and asset.get("video_height"):
        facets["video_dimensions"] = f"{asset['video_width']}x{asset['video_height']}"
    if asset.get("video_container"):
        facets["video_container"] = asset["video_container"]
    if asset.get("video_codec"):
        facets["video_codec"] = asset["video_codec"]
    if asset.get("audio_codec"):
        facets["audio_codec"] = asset["audio_codec"]
    if asset.get("video_duration_seconds") is not None:
        facets["duration_seconds"] = asset["video_duration_seconds"]
    if asset.get("video_frame_rate") is not None:
        facets["frame_rate"] = asset["video_frame_rate"]
    if asset.get("video_captured_at"):
        facets["captured_at"] = asset["video_captured_at"]
    if asset.get("model_format"):
        facets["model_format"] = asset["model_format"]
    if asset.get("model_vertex_count") is not None:
        facets["vertex_count"] = asset["model_vertex_count"]
    if asset.get("model_face_count") is not None:
        facets["face_count"] = asset["model_face_count"]
    if asset.get("model_units"):
        facets["units"] = asset["model_units"]
    return facets


def _media_routing_meta(
    root_label: str,
    samples: list[dict[str, Any]],
) -> dict[str, Any]:
    """Structured deterministic routing facets for a media root."""

    paths: set[str] = set()
    filenames: set[str] = set()
    captions: set[str] = set()
    media_classes: set[str] = set()
    media_types: set[str] = set()
    media_kinds: set[str] = set()
    dimensions: set[str] = set()
    durations: set[str] = set()
    model_formats: set[str] = set()

    for asset in samples:
        relative_path = str(asset.get("relative_path") or "")
        if relative_path:
            paths.add(relative_path)
            filenames.add(Path(relative_path).stem.replace("_", " ").replace("-", " "))
        if asset.get("caption"):
            captions.add(" ".join(str(asset["caption"]).split())[:160])
        if asset.get("media_class"):
            media_classes.add(str(asset["media_class"]))
        if asset.get("media_type"):
            media_types.add(str(asset["media_type"]))
        if asset.get("media_kind"):
            media_kinds.add(str(asset["media_kind"]))
        if asset.get("image_width") and asset.get("image_height"):
            dimensions.add(f"{asset['image_width']}x{asset['image_height']}")
        if asset.get("video_width") and asset.get("video_height"):
            dimensions.add(f"{asset['video_width']}x{asset['video_height']}")
        if asset.get("video_duration_seconds") is not None:
            durations.add(str(asset["video_duration_seconds"]))
        if asset.get("model_format"):
            model_formats.add(str(asset["model_format"]))

    return _clean_routing_meta(
        {
            "root": root_label,
            "paths": sorted(paths)[:25],
            "filenames": sorted(filenames)[:25],
            "captions": sorted(captions)[:20],
            "media_kinds": sorted(media_kinds)[:10],
            "media_classes": sorted(media_classes)[:10],
            "media_types": sorted(media_types)[:10],
            "dimensions": sorted(dimensions)[:10],
            "durations_seconds": sorted(durations)[:10],
            "model_formats": sorted(model_formats)[:10],
        }
    )


def _media_source_refs(samples: list[dict[str, Any]]) -> list[str]:
    return sorted(
        {
            evidence_ref("media_assets", str(asset["asset_id"]))
            for asset in samples
            if asset.get("asset_id")
        }
    )


def _media_high_watermark(assets: list[dict[str, Any]], *extra: str) -> str:
    digest = hashlib.sha256()
    for value in extra:
        digest.update(str(value or "").encode("utf-8"))
        digest.update(b"\0")
    fields = (
        "asset_id",
        "source_item_id",
        "media_class",
        "inspect_status",
        "updated_at",
        "relative_path",
        "media_type",
        "source_sha256",
        "caption",
        "media_kind",
        "image_format",
        "image_width",
        "image_height",
        "image_captured_at",
        "video_container",
        "video_codec",
        "audio_codec",
        "video_width",
        "video_height",
        "video_duration_seconds",
        "video_captured_at",
        "model_format",
        "model_vertex_count",
        "model_face_count",
        "model_units",
    )
    for asset in sorted(
        assets,
        key=lambda item: (
            str(item.get("relative_path") or ""),
            str(item.get("asset_id") or ""),
        ),
    ):
        for field in fields:
            digest.update(str(asset.get(field) or "").encode("utf-8"))
            digest.update(b"\0")
    return digest.hexdigest()


def _media_modality(assets: list[dict[str, Any]]) -> str:
    valid = {"image", "video", "audio", "model3d"}
    classes = {str(asset.get("media_class") or "") for asset in assets}
    known = {media_class for media_class in classes if media_class in valid}
    if len(known) == 1 and len(classes) == 1:
        return next(iter(known))
    return "mixed"


def _dominant_media_kind(assets: list[dict[str, Any]]) -> str | None:
    counts: dict[str, int] = {}
    for asset in assets:
        media_kind = str(asset.get("media_kind") or "").strip()
        if media_kind:
            counts[media_kind] = counts.get(media_kind, 0) + 1
    if not counts:
        return None
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))[0][0]


def _media_cluster_summary_text(cluster: dict[str, Any]) -> str:
    members = list(cluster["assets"])
    medoid_path = str(cluster["medoid"].get("relative_path") or "")
    captions = [
        " ".join(str(asset.get("caption") or "").split())[:120]
        for asset in members
        if asset.get("caption")
    ][:5]
    filenames = [
        Path(str(asset.get("relative_path") or "")).stem.replace("_", " ").replace("-", " ")
        for asset in members
    ][:8]
    parts = [
        f"Visual media cluster centered on {medoid_path or cluster['medoid_id']}.",
        f"Contains {len(members)} image asset{'s' if len(members) != 1 else ''}.",
    ]
    if captions:
        parts.append("Captions include: " + "; ".join(captions) + ".")
    elif filenames:
        parts.append("Filename terms include: " + "; ".join(filenames) + ".")
    return " ".join(parts)


def _media_cluster_attrs(cluster: dict[str, Any]) -> dict[str, Any]:
    members = list(cluster["assets"])
    return {
        "asset_count": len(members),
        "medoid": cluster["medoid_id"],
        "medoid_profile": _image_profile_name(),
        "asset_ids": sorted(str(asset["asset_id"]) for asset in members if asset.get("asset_id")),
        "media_classes": _value_counts(members, "media_class"),
        "media_kinds": _value_counts(members, "media_kind"),
    }


def _media_cluster_importance(assets: list[dict[str, Any]]) -> float:
    if any(str(asset.get("caption") or "").strip() for asset in assets):
        return 0.45
    return 0.35


def _delete_stale_media_clusters(
    parent_summary_id: str, current_summary_ids: set[str], now: str
) -> None:
    with catalog_connection() as conn:
        rows = conn.execute(
            """
            SELECT summary_id
            FROM "summary_nodes"
            WHERE parent_summary_id = ?
              AND kind = 'media_cluster_summary'
              AND summary_status = 'current'
            """,
            (parent_summary_id,),
        ).fetchall()
        stale_ids = [
            row["summary_id"]
            for row in rows
            if row["summary_id"] not in current_summary_ids
        ]
        if not stale_ids:
            return
        conn.executemany(
            """
            UPDATE "summary_nodes"
            SET summary_status = 'deleted',
                updated_at = ?,
                attrs_json = ?
            WHERE summary_id = ?
            """,
            [
                (
                    now,
                    json.dumps({"error_kind": "stale_media_cluster"}, sort_keys=True),
                    summary_id,
                )
                for summary_id in stale_ids
            ],
        )
        conn.commit()


def _media_summary_attrs(
    assets: list[dict[str, Any]],
    samples: list[dict[str, Any]],
    extra: dict[str, Any],
) -> dict[str, Any]:
    attrs = dict(extra)
    attrs.update(
        {
            "asset_count": len(assets),
            "sampled_asset_count": len(samples),
            "media_classes": _value_counts(assets, "media_class"),
            "media_kinds": _value_counts(assets, "media_kind"),
        }
    )
    return attrs


def _value_counts(rows: list[dict[str, Any]], field: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        value = str(row.get(field) or "").strip()
        if value:
            counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


