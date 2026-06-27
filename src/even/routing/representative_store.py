"""Manifest/watermark/URI and medoid-row helpers shared by the
representative build and search sides."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from even.db import catalog_connection
from even.routing.shared import (
    GLOBAL_FTS_TEMPLATE,
    GLOBAL_SIGLIP_TEMPLATE,
    _json_object,
)
from even.routing.summary_store import _representation_policy_version


def _global_semantic_uri(profile_name: str) -> str:
    return f"semantic/global_representatives/{profile_name}.lancedb"


def _global_siglip_uri(image_profile_name: str) -> str:
    return f"semantic/global_representatives/siglip/{image_profile_name}.lancedb"


def _current_album_medoid_rows(image_profile_name: str) -> list[dict[str, Any]]:
    """One row per album medoid, with the medoid's reused SigLIP vector (C2/B2).

    Reads current `album_summary` units, takes their persisted medoid asset ids,
    and fetches those assets' vectors from the per-scope image proof store. Albums
    without a medoid fingerprint (no `index scope --image` yet) contribute nothing.
    """

    from even import image_index

    with catalog_connection() as conn:
        rows = conn.execute(
            """
            SELECT s.summary_id, s.root_id, s.scope_id, s.title, s.modality,
                   s.importance, s.attrs_json, s.source_high_watermark, sr.root_label
            FROM "summary_nodes" s
            JOIN "source_roots" sr ON sr.root_id = s.root_id
            WHERE s.summary_status = 'current' AND s.kind = 'album_summary'
            ORDER BY s.root_id, s.scope_id, s.summary_id
            """
        ).fetchall()

    vectors_cache: dict[str, dict[str, dict[str, Any]]] = {}
    medoid_rows: list[dict[str, Any]] = []
    for row in rows:
        attrs = _json_object(row["attrs_json"])
        medoids = attrs.get("medoids") or []
        profile = str(attrs.get("medoid_profile") or image_profile_name)
        if not medoids or profile != image_profile_name:
            continue
        scope_id = str(row["scope_id"])
        if scope_id not in vectors_cache:
            vectors_cache[scope_id] = (
                image_index.read_scope_image_vectors(scope_id, image_profile_name) or {}
            )
        by_asset = vectors_cache[scope_id]
        for asset_id in medoids:
            asset = by_asset.get(str(asset_id))
            if not asset or not asset.get("vector"):
                continue
            medoid_rows.append(
                {
                    "summary_id": row["summary_id"],
                    "root_id": row["root_id"],
                    "scope_id": scope_id,
                    "asset_id": str(asset_id),
                    "vector": asset["vector"],
                    "modality": str(row["modality"] or "image"),
                    "title": str(row["title"] or row["root_label"] or row["root_id"]),
                    "importance": row["importance"],
                    "relative_path": asset.get("relative_path") or "",
                    "root_label": row["root_label"],
                    "source_high_watermark": row["source_high_watermark"] or "",
                }
            )
    return medoid_rows


def _siglip_watermark(rows: list[dict[str, Any]], image_profile_name: str) -> str:
    digest = hashlib.sha256()
    digest.update(image_profile_name.encode("utf-8"))
    digest.update(b"\0")
    digest.update(GLOBAL_SIGLIP_TEMPLATE.encode("utf-8"))
    digest.update(b"\0")
    digest.update(_representation_policy_version().encode("utf-8"))
    digest.update(b"\0")
    for row in sorted(
        rows,
        key=lambda r: (str(r["scope_id"]), str(r["summary_id"]), str(r["asset_id"])),
    ):
        for field in ("summary_id", "scope_id", "asset_id", "source_high_watermark"):
            digest.update(str(row.get(field) or "").encode("utf-8"))
            digest.update(b"\0")
    return digest.hexdigest()


def _representative_watermark(
    rows: list[dict[str, Any]], profile: str, template: str = GLOBAL_FTS_TEMPLATE
) -> str:
    digest = hashlib.sha256()
    digest.update(profile.encode("utf-8"))
    digest.update(b"\0")
    digest.update(template.encode("utf-8"))
    digest.update(b"\0")
    digest.update(_representation_policy_version().encode("utf-8"))
    digest.update(b"\0")
    for row in rows:
        for field in (
            "summary_id",
            "root_id",
            "scope_id",
            "source_high_watermark",
            "routing_payload",
        ):
            digest.update(str(row.get(field) or "").encode("utf-8"))
            digest.update(b"\0")
    return digest.hexdigest()


def _manifest_current(
    manifest_path: Path,
    watermark: str,
    template: str,
    *,
    fts_profile: str | None = None,
) -> bool:
    """Check a global representative manifest against the current watermark.

    All three backends validate `summary_watermark` and `template_name`. The FTS
    backend additionally pins `fts_profile`; the vector backends never validated
    their profile field, so that check stays opt-in.
    """

    if not manifest_path.exists():
        return False
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    if manifest.get("summary_watermark") != watermark:
        return False
    if manifest.get("template_name") != template:
        return False
    if fts_profile is not None and manifest.get("fts_profile") != fts_profile:
        return False
    return True


def _global_fts_uri(fts_profile: str) -> str:
    return f"fts/global_representatives/{fts_profile}"


