"""Media metadata extraction into the catalog.

Deterministic metadata extraction dispatched by media class:

- images  -> ``media_assets`` + ``image_metadata`` + thumbnail (Pillow)
- video   -> ``media_assets`` + ``video_metadata`` (pymediainfo)
- 3D      -> ``media_assets`` + ``model3d_metadata`` (built-in OBJ/STL parsers)

No model is involved. Thumbnails are stored through the shared blob store
(``media_artifacts`` -> ``artifact_blobs``). Model-based work (`describe`) and
duplicate detection (`dedupe`) are separate commands.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import struct
from typing import Any

from even.blobs import store_artifact_blob
from even.catalog import ensure_catalog
from even.db import catalog_connection
from even.inventory import ScanOptions, scan_folder_to_catalog
from even.ollama import DEFAULT_MODEL, DEFAULT_URL, generate_from_image, ollama_available

IMAGE_MEDIA_TYPES = {
    "image/jpeg",
    "image/png",
    "image/gif",
    "image/bmp",
    "image/tiff",
    "image/webp",
    "image/heic",
    "image/heif",
}

THUMBNAIL_MAX_EDGE = 256

# 3D formats parsed without an external dependency. Other formats (gltf, glb,
# ply) are inventoried as assets but deferred until a parser is added.
_NATIVE_MODEL3D_SUFFIXES = {".obj", ".stl"}


@dataclass
class InspectOptions:
    limit: int | None = None
    thumbnails: bool = True


# Closed media-kind vocabulary. Subject taxonomy stays out; upper layers extract
# subjects from the free-text caption.
MEDIA_KINDS = (
    "photo",
    "screenshot",
    "document_scan",
    "diagram",
    "chart",
    "illustration",
    "map",
    "render",
)

CAPTION_PROMPT = "Describe this image in one short, factual sentence."
KIND_PROMPT = (
    "Classify this image into exactly one of these categories and answer with "
    "only that single word: " + ", ".join(MEDIA_KINDS) + "."
)

DESCRIBE_PROFILE = "media_describe"


_HASH_METHODS = ("phash", "dhash", "ahash")


@dataclass
class DedupeOptions:
    limit: int | None = None
    max_distance: int = 5
    method: str = "phash"


@dataclass
class DescribeOptions:
    limit: int | None = None
    model: str = DEFAULT_MODEL
    ollama_url: str = DEFAULT_URL
    classify_kind: bool = False
    timeout: float = 300.0
    # Downscale the longest edge before the VLM call. Full-resolution photos are
    # far slower with no caption-quality gain, and tiling vision models explode
    # their image-token count above their single-tile resolution: granite3.2-vision
    # caps at 16384 ctx and only fits images at ~<=384 px longest edge (1024 px is
    # ~35k tokens -> HTTP 400). Keep this aligned with the model's tile size. 0
    # disables downscaling. (`num_ctx` cannot be raised — Ollama ignores it here.)
    max_edge: int = 384


def inspect_folder_to_catalog(path: Path, options: InspectOptions) -> dict[str, Any]:
    """Auto-scan a folder and extract metadata from current media source items."""

    catalog_state = ensure_catalog()
    if catalog_state["status"] not in {"created", "current"}:
        return {
            "status": "failed",
            "error_kind": "catalog_not_ready",
            "catalog_status": catalog_state["status"],
        }

    scan_result = scan_folder_to_catalog(
        path,
        ScanOptions(max_files=None, max_bytes=None, max_depth=None),
    )
    if scan_result["status"] != "ok":
        return {
            "status": scan_result["status"],
            "error_kind": "auto_scan_failed",
            "scan_result": scan_result,
        }

    root_id = scan_result["root_id"]
    items = _media_items_for_root(root_id, options.limit)
    now = _iso(_utc_now())
    counts = {
        "media_planned": len(items),
        "assets_written": 0,
        "thumbnails_written": 0,
        "assets_failed": 0,
        "assets_deferred": 0,
    }
    failures: list[dict[str, Any]] = []

    image_module = _load_pillow()

    with catalog_connection() as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        for item in items:
            media_class = item["media_class"]
            try:
                if media_class == "image":
                    if image_module is None:
                        raise _BackendMissing("pillow_missing")
                    wrote_thumb = _inspect_image(
                        conn, item, image_module, thumbnails=options.thumbnails, now=now
                    )
                    counts["assets_written"] += 1
                    counts["thumbnails_written"] += 1 if wrote_thumb else 0
                elif media_class == "video":
                    _inspect_video(conn, item, now=now)
                    counts["assets_written"] += 1
                elif media_class == "model3d":
                    deferred = _inspect_model3d(conn, item, now=now)
                    if deferred:
                        counts["assets_deferred"] += 1
                    counts["assets_written"] += 1
            except _BackendMissing as exc:
                counts["assets_failed"] += 1
                failures.append(
                    {
                        "relative_path": item["relative_path"],
                        "error_kind": str(exc),
                    }
                )
            except Exception as exc:  # noqa: BLE001 - per-file boundary.
                counts["assets_failed"] += 1
                failures.append(
                    {
                        "relative_path": item["relative_path"],
                        "error_kind": f"{media_class}_inspect_failed",
                        "redacted_detail": exc.__class__.__name__,
                    }
                )
        conn.commit()

    if counts["assets_failed"] == 0:
        status = "ok"
    elif counts["assets_written"] > 0:
        status = "partial"
    else:
        status = "failed"
    return {
        "status": status,
        "root_id": root_id,
        "root_label": scan_result.get("root_label"),
        "scope_id": scan_result.get("scope_id"),
        "auto_scan_status": scan_result["status"],
        "counts": counts,
        "failures": failures,
    }


class _BackendMissing(Exception):
    """Raised when an optional extraction backend is not installed."""


# --------------------------------------------------------------------------- #
# Dedupe (perceptual hashing)
# --------------------------------------------------------------------------- #


def dedupe_folder_to_catalog(path: Path, options: DedupeOptions) -> dict[str, Any]:
    """Find near-duplicate image candidates via perceptual hashing.

    Deterministic and model-free: hashes each image's pixels and writes pairs
    within ``max_distance`` Hamming distance to ``media_dedupe_candidates`` for
    review. Sources are read in place, never modified.
    """

    if options.method not in _HASH_METHODS:
        return {
            "status": "failed",
            "error_kind": "unknown_hash_method",
            "method": options.method,
        }

    catalog_state = ensure_catalog()
    if catalog_state["status"] not in {"created", "current"}:
        return {
            "status": "failed",
            "error_kind": "catalog_not_ready",
            "catalog_status": catalog_state["status"],
        }

    image_module = _load_pillow()
    imagehash = _load_imagehash()
    if image_module is None or imagehash is None:
        return {
            "status": "failed",
            "error_kind": "hash_backend_missing",
            "message": "Install the media extra (run uv sync) to dedupe images.",
        }

    scan_result = scan_folder_to_catalog(
        path,
        ScanOptions(max_files=None, max_bytes=None, max_depth=None),
    )
    if scan_result["status"] != "ok":
        return {
            "status": scan_result["status"],
            "error_kind": "auto_scan_failed",
            "scan_result": scan_result,
        }

    root_id = scan_result["root_id"]
    items = [
        item
        for item in _media_items_for_root(root_id, None)
        if item["media_class"] == "image"
    ]
    if options.limit is not None:
        items = items[: options.limit]

    now = _iso(_utc_now())
    hash_func = _hash_func(imagehash, options.method)
    counts = {
        "images_planned": len(items),
        "images_hashed": 0,
        "candidates_written": 0,
        "images_failed": 0,
    }
    failures: list[dict[str, Any]] = []
    hashed: list[tuple[str, Any]] = []

    with catalog_connection() as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        for item in items:
            try:
                with image_module.open(Path(item["source_uri"])) as image:
                    fingerprint = hash_func(image)
                asset_id = _asset_id(item)
                _ensure_media_asset(conn, asset_id, item, now)
                hashed.append((asset_id, fingerprint))
                counts["images_hashed"] += 1
            except Exception as exc:  # noqa: BLE001 - per-image boundary.
                counts["images_failed"] += 1
                failures.append(
                    {
                        "relative_path": item["relative_path"],
                        "error_kind": "hash_failed",
                        "redacted_detail": exc.__class__.__name__,
                    }
                )

        for i in range(len(hashed)):
            for j in range(i + 1, len(hashed)):
                distance = int(hashed[i][1] - hashed[j][1])
                if distance <= options.max_distance:
                    _write_dedupe_candidate(
                        conn,
                        hashed[i][0],
                        hashed[j][0],
                        options.method,
                        distance,
                        now,
                    )
                    counts["candidates_written"] += 1
        conn.commit()

    status = "ok" if counts["images_failed"] == 0 else (
        "partial" if counts["images_hashed"] > 0 else "failed"
    )
    return {
        "status": status,
        "method": options.method,
        "max_distance": options.max_distance,
        "root_id": root_id,
        "root_label": scan_result.get("root_label"),
        "scope_id": scan_result.get("scope_id"),
        "counts": counts,
        "failures": failures,
    }


def _hash_func(imagehash: Any, method: str) -> Any:
    return {
        "phash": imagehash.phash,
        "dhash": imagehash.dhash,
        "ahash": imagehash.average_hash,
    }[method]


def _write_dedupe_candidate(
    conn: sqlite3.Connection,
    asset_a: str,
    asset_b: str,
    method: str,
    distance: int,
    now: str,
) -> None:
    first, second = sorted((asset_a, asset_b))
    candidate_id = _stable_id("dup", first, second, method)
    conn.execute(
        """
        INSERT INTO "media_dedupe_candidates"
        (candidate_id, asset_id_a, asset_id_b, method, distance, attrs_json)
        VALUES (?, ?, ?, ?, ?, NULL)
        ON CONFLICT(candidate_id) DO UPDATE SET
            distance = excluded.distance
        """,
        (candidate_id, first, second, method, distance),
    )


def _load_imagehash() -> Any | None:
    try:
        import imagehash  # type: ignore[import-not-found]
    except ModuleNotFoundError:
        return None
    return imagehash


# --------------------------------------------------------------------------- #
# Describe (local VLM)
# --------------------------------------------------------------------------- #


def describe_folder_to_catalog(path: Path, options: DescribeOptions) -> dict[str, Any]:
    """Generate shallow VLM observations for current image source items.

    Opt-in and model-backed: reads image bytes in place, calls a local Ollama
    vision model, and writes caption (and optional media_kind) rows into
    ``media_observations``. Sources are never copied or modified.
    """

    catalog_state = ensure_catalog()
    if catalog_state["status"] not in {"created", "current"}:
        return {
            "status": "failed",
            "error_kind": "catalog_not_ready",
            "catalog_status": catalog_state["status"],
        }

    if not ollama_available(options.ollama_url):
        return {
            "status": "failed",
            "error_kind": "ollama_unreachable",
            "message": f"No local Ollama server at {options.ollama_url}.",
        }

    scan_result = scan_folder_to_catalog(
        path,
        ScanOptions(max_files=None, max_bytes=None, max_depth=None),
    )
    if scan_result["status"] != "ok":
        return {
            "status": scan_result["status"],
            "error_kind": "auto_scan_failed",
            "scan_result": scan_result,
        }

    root_id = scan_result["root_id"]
    items = [
        item
        for item in _media_items_for_root(root_id, None)
        if item["media_class"] == "image"
    ]
    if options.limit is not None:
        items = items[: options.limit]

    now = _iso(_utc_now())
    counts = {
        "images_planned": len(items),
        "captions_written": 0,
        "kinds_written": 0,
        "images_failed": 0,
    }
    failures: list[dict[str, Any]] = []
    elapsed_samples: list[float] = []
    image_module = _load_pillow()

    with catalog_connection() as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        for item in items:
            try:
                raw_bytes = Path(item["source_uri"]).read_bytes()
                image_bytes = _vlm_image_bytes(
                    raw_bytes, image_module, options.max_edge
                )
                asset_id = _asset_id(item)
                _ensure_media_asset(conn, asset_id, item, now)

                caption = generate_from_image(
                    image_bytes,
                    CAPTION_PROMPT,
                    model=options.model,
                    url=options.ollama_url,
                    timeout=options.timeout,
                )
                elapsed_samples.append(caption["elapsed_ms"])
                _write_observation(
                    conn, asset_id, "caption", caption["text"], options.model, now
                )
                counts["captions_written"] += 1

                if options.classify_kind:
                    kind = generate_from_image(
                        image_bytes,
                        KIND_PROMPT,
                        model=options.model,
                        url=options.ollama_url,
                        timeout=options.timeout,
                    )
                    elapsed_samples.append(kind["elapsed_ms"])
                    _write_observation(
                        conn,
                        asset_id,
                        "media_kind",
                        _normalize_kind(kind["text"]),
                        options.model,
                        now,
                    )
                    counts["kinds_written"] += 1
            except Exception as exc:  # noqa: BLE001 - per-image boundary.
                counts["images_failed"] += 1
                failures.append(
                    {
                        "relative_path": item["relative_path"],
                        "error_kind": "describe_failed",
                        "redacted_detail": exc.__class__.__name__,
                    }
                )
        conn.commit()

    if counts["images_failed"] == 0:
        status = "ok"
    elif counts["captions_written"] > 0:
        status = "partial"
    else:
        status = "failed"
    return {
        "status": status,
        "model": options.model,
        "root_id": root_id,
        "root_label": scan_result.get("root_label"),
        "scope_id": scan_result.get("scope_id"),
        "counts": counts,
        "timing_ms": _timing_summary(elapsed_samples),
        "failures": failures,
    }


def _vlm_image_bytes(raw: bytes, image_module: Any, max_edge: int) -> bytes:
    """Downscale image bytes for the VLM call, read-only and in memory.

    The source is never modified; only the bytes sent to the model are resized.
    Falls back to the original bytes if Pillow is unavailable or the image
    cannot be decoded.
    """

    if image_module is None or not max_edge:
        return raw
    try:
        with image_module.open(io.BytesIO(raw)) as image:
            if max(image.size) <= max_edge:
                return raw
            resized = image.convert("RGB")
            resized.thumbnail((max_edge, max_edge))
            buffer = io.BytesIO()
            resized.save(buffer, format="JPEG", quality=85)
            return buffer.getvalue()
    except Exception:  # noqa: BLE001 - downscale is best-effort.
        return raw


def _normalize_kind(text: str) -> str:
    token = text.strip().lower().split()[0].strip(".,:;\"'") if text.strip() else ""
    return token if token in MEDIA_KINDS else "other"


def _timing_summary(samples: list[float]) -> dict[str, Any]:
    if not samples:
        return {"calls": 0, "avg_ms": None, "p50_ms": None, "max_ms": None}
    ordered = sorted(samples)
    return {
        "calls": len(samples),
        "avg_ms": round(sum(samples) / len(samples), 1),
        "p50_ms": ordered[len(ordered) // 2],
        "max_ms": ordered[-1],
    }


def _ensure_media_asset(
    conn: sqlite3.Connection, asset_id: str, item: dict[str, Any], now: str
) -> None:
    conn.execute(
        """
        INSERT OR IGNORE INTO "media_assets"
        (asset_id, source_item_id, media_class, primary_artifact_id,
         inspect_status, attrs_json, updated_at)
        VALUES (?, ?, ?, NULL, 'pending', ?, ?)
        """,
        (
            asset_id,
            item["source_item_id"],
            item["media_class"],
            json.dumps({"media_type": item["media_type"]}),
            now,
        ),
    )


def _write_observation(
    conn: sqlite3.Connection,
    asset_id: str,
    observation_kind: str,
    value_text: str,
    model: str,
    now: str,
) -> None:
    observation_id = _stable_id("mobs", asset_id, observation_kind)
    conn.execute(
        """
        INSERT INTO "media_observations"
        (observation_id, asset_id, observation_kind, value_text, confidence,
         producer, profile, attrs_json, created_at)
        VALUES (?, ?, ?, ?, NULL, ?, ?, NULL, ?)
        ON CONFLICT(observation_id) DO UPDATE SET
            value_text = excluded.value_text,
            producer = excluded.producer,
            created_at = excluded.created_at
        """,
        (
            observation_id,
            asset_id,
            observation_kind,
            value_text,
            f"ollama:{model}",
            DESCRIBE_PROFILE,
            now,
        ),
    )


# --------------------------------------------------------------------------- #
# Images
# --------------------------------------------------------------------------- #


def _inspect_image(
    conn: sqlite3.Connection,
    item: dict[str, Any],
    image_module: Any,
    *,
    thumbnails: bool,
    now: str,
) -> bool:
    asset_id = _asset_id(item)
    source_path = Path(item["source_uri"])

    with image_module.open(source_path) as image:
        width, height = image.size
        metadata = _image_fields(image)
        thumbnail_bytes = None
        thumb_size: tuple[int, int] | None = None
        if thumbnails:
            thumbnail_bytes, thumb_size = _thumbnail_png(image)

    _write_media_asset(conn, asset_id, item, "image", now)
    conn.execute('DELETE FROM "image_metadata" WHERE asset_id = ?', (asset_id,))
    conn.execute(
        """
        INSERT INTO "image_metadata"
        (asset_id, format, width, height, megapixels, color_mode, has_alpha,
         orientation, dpi, camera_make, camera_model, captured_at, gps_lat,
         gps_lon, gps_altitude, attrs_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            asset_id,
            metadata["format"],
            width,
            height,
            round(width * height / 1_000_000, 3),
            metadata["color_mode"],
            metadata["has_alpha"],
            metadata["orientation"],
            metadata["dpi"],
            metadata["camera_make"],
            metadata["camera_model"],
            metadata["captured_at"],
            metadata["gps_lat"],
            metadata["gps_lon"],
            metadata["gps_altitude"],
            json.dumps(metadata["attrs"]),
        ),
    )

    if thumbnail_bytes is not None and thumb_size is not None:
        _store_thumbnail(conn, asset_id, thumbnail_bytes, thumb_size, now=now)
        return True
    return False


def _image_fields(image: Any) -> dict[str, Any]:
    mode = image.mode
    has_alpha = 1 if (mode in {"RGBA", "LA", "PA"} or "transparency" in image.info) else 0
    dpi_info = image.info.get("dpi")
    dpi = float(dpi_info[0]) if dpi_info else None

    try:
        exif = image.getexif()
    except Exception:  # noqa: BLE001 - corrupt EXIF must not fail the asset.
        exif = {}

    return {
        "format": image.format,
        "color_mode": mode,
        "has_alpha": has_alpha,
        "orientation": _as_int(exif.get(274)) if exif else None,
        "dpi": dpi,
        "camera_make": _as_text(exif.get(271)) if exif else None,
        "camera_model": _as_text(exif.get(272)) if exif else None,
        "captured_at": _exif_datetime(exif),
        "gps_lat": _exif_gps(exif)[0],
        "gps_lon": _exif_gps(exif)[1],
        "gps_altitude": _exif_gps(exif)[2],
        "attrs": {},
    }


def _thumbnail_png(image: Any) -> tuple[bytes, tuple[int, int]]:
    thumb = image.copy()
    thumb.thumbnail((THUMBNAIL_MAX_EDGE, THUMBNAIL_MAX_EDGE))
    if thumb.mode not in {"RGB", "RGBA"}:
        thumb = thumb.convert("RGB")
    buffer = io.BytesIO()
    thumb.save(buffer, format="PNG")
    return buffer.getvalue(), thumb.size


def _exif_datetime(exif: Any) -> str | None:
    raw = None
    if exif:
        try:
            exif_ifd = exif.get_ifd(0x8769)
            raw = exif_ifd.get(36867) or exif_ifd.get(36868)
        except Exception:  # noqa: BLE001
            raw = None
        if not raw:
            raw = exif.get(306)
    if not raw:
        return None
    try:
        return datetime.strptime(str(raw).strip(), "%Y:%m:%d %H:%M:%S").isoformat()
    except ValueError:
        return None


def _exif_gps(exif: Any) -> tuple[float | None, float | None, float | None]:
    if not exif:
        return None, None, None
    try:
        gps = exif.get_ifd(0x8825)
    except Exception:  # noqa: BLE001
        return None, None, None
    if not gps:
        return None, None, None
    lat = _gps_decimal(gps.get(2), gps.get(1))
    lon = _gps_decimal(gps.get(4), gps.get(3))
    altitude = None
    if gps.get(6) is not None:
        try:
            altitude = float(gps.get(6))
            if _as_int(gps.get(5)) == 1:
                altitude = -altitude
        except (TypeError, ValueError):
            altitude = None
    return lat, lon, altitude


def _gps_decimal(coordinate: Any, ref: Any) -> float | None:
    if not coordinate:
        return None
    try:
        degrees, minutes, seconds = (float(part) for part in coordinate)
    except (TypeError, ValueError):
        return None
    decimal = degrees + minutes / 60 + seconds / 3600
    if str(ref).upper() in {"S", "W"}:
        decimal = -decimal
    return round(decimal, 7)


# --------------------------------------------------------------------------- #
# Video
# --------------------------------------------------------------------------- #


def _inspect_video(conn: sqlite3.Connection, item: dict[str, Any], *, now: str) -> None:
    media_info = _load_pymediainfo()
    if media_info is None:
        raise _BackendMissing("video_backend_missing")
    info = media_info.parse(item["source_uri"])
    fields = _video_fields(info.tracks)

    asset_id = _asset_id(item)
    _write_media_asset(conn, asset_id, item, "video", now)
    conn.execute('DELETE FROM "video_metadata" WHERE asset_id = ?', (asset_id,))
    conn.execute(
        """
        INSERT INTO "video_metadata"
        (asset_id, container, video_codec, audio_codec, width, height,
         duration_seconds, frame_rate, bit_rate, captured_at, gps_lat, gps_lon,
         attrs_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            asset_id,
            fields["container"],
            fields["video_codec"],
            fields["audio_codec"],
            fields["width"],
            fields["height"],
            fields["duration_seconds"],
            fields["frame_rate"],
            fields["bit_rate"],
            fields["captured_at"],
            None,
            None,
            json.dumps({}),
        ),
    )


def _video_fields(tracks: list[Any]) -> dict[str, Any]:
    general = _first_track(tracks, "General")
    video = _first_track(tracks, "Video")
    audio = _first_track(tracks, "Audio")

    duration_ms = _as_float(getattr(general, "duration", None))
    return {
        "container": _as_text(getattr(general, "format", None)),
        "video_codec": _as_text(getattr(video, "format", None)),
        "audio_codec": _as_text(getattr(audio, "format", None)),
        "width": _as_int(getattr(video, "width", None)),
        "height": _as_int(getattr(video, "height", None)),
        "duration_seconds": round(duration_ms / 1000, 3) if duration_ms else None,
        "frame_rate": _as_float(getattr(video, "frame_rate", None)),
        "bit_rate": _as_int(getattr(general, "overall_bit_rate", None)),
        "captured_at": _container_datetime(general),
    }


def _first_track(tracks: list[Any], track_type: str) -> Any:
    for track in tracks:
        if getattr(track, "track_type", None) == track_type:
            return track
    return None


def _container_datetime(general: Any) -> str | None:
    raw = getattr(general, "recorded_date", None) or getattr(
        general, "tagged_date", None
    )
    if not raw:
        return None
    text = str(raw).strip().removeprefix("UTC ").strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).isoformat()
        except ValueError:
            continue
    return None


# --------------------------------------------------------------------------- #
# 3D models
# --------------------------------------------------------------------------- #


def _inspect_model3d(conn: sqlite3.Connection, item: dict[str, Any], *, now: str) -> bool:
    asset_id = _asset_id(item)
    suffix = Path(item["relative_path"]).suffix.lower()
    if suffix not in _NATIVE_MODEL3D_SUFFIXES:
        # Inventory the asset but defer typed metadata until a parser exists.
        _write_media_asset(conn, asset_id, item, "model3d", now, status="deferred")
        return True

    raw = Path(item["source_uri"]).read_bytes()
    fields = _model3d_fields_obj(raw) if suffix == ".obj" else _model3d_fields_stl(raw)

    _write_media_asset(conn, asset_id, item, "model3d", now)
    conn.execute('DELETE FROM "model3d_metadata" WHERE asset_id = ?', (asset_id,))
    conn.execute(
        """
        INSERT INTO "model3d_metadata"
        (asset_id, format, vertex_count, face_count, has_normals, has_uv,
         has_color, bbox_min, bbox_max, units, attrs_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            asset_id,
            fields["format"],
            fields["vertex_count"],
            fields["face_count"],
            fields["has_normals"],
            fields["has_uv"],
            fields["has_color"],
            _json_or_none(fields["bbox_min"]),
            _json_or_none(fields["bbox_max"]),
            fields["units"],
            json.dumps({}),
        ),
    )
    return False


def _model3d_fields_obj(raw: bytes) -> dict[str, Any]:
    text = raw.decode("utf-8", "ignore")
    vertices = faces = normals = uvs = 0
    bbox = _BBox()
    for line in text.splitlines():
        if line.startswith("v "):
            vertices += 1
            bbox.update(line[2:])
        elif line.startswith("vn "):
            normals += 1
        elif line.startswith("vt "):
            uvs += 1
        elif line.startswith("f "):
            faces += 1
    return {
        "format": "OBJ",
        "vertex_count": vertices,
        "face_count": faces,
        "has_normals": 1 if normals else 0,
        "has_uv": 1 if uvs else 0,
        "has_color": 0,
        "bbox_min": bbox.minimum(),
        "bbox_max": bbox.maximum(),
        "units": None,
    }


def _model3d_fields_stl(raw: bytes) -> dict[str, Any]:
    bbox = _BBox()
    if len(raw) >= 84:
        triangle_count = struct.unpack("<I", raw[80:84])[0]
        if len(raw) == 84 + triangle_count * 50:  # binary STL
            offset = 84
            for _ in range(triangle_count):
                # 12 bytes normal, then 3 vertices of 3 float32 each.
                for vertex in range(1, 4):
                    base = offset + 12 * vertex
                    x, y, z = struct.unpack_from("<3f", raw, base)
                    bbox.update_xyz(x, y, z)
                offset += 50
            return {
                "format": "STL",
                "vertex_count": triangle_count * 3,
                "face_count": triangle_count,
                "has_normals": 1,
                "has_uv": 0,
                "has_color": 0,
                "bbox_min": bbox.minimum(),
                "bbox_max": bbox.maximum(),
                "units": None,
            }

    text = raw.decode("ascii", "ignore")
    faces = text.count("facet normal")
    vertices = 0
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("vertex "):
            vertices += 1
            bbox.update(stripped[len("vertex ") :])
    return {
        "format": "STL",
        "vertex_count": vertices,
        "face_count": faces,
        "has_normals": 1,
        "has_uv": 0,
        "has_color": 0,
        "bbox_min": bbox.minimum(),
        "bbox_max": bbox.maximum(),
        "units": None,
    }


class _BBox:
    def __init__(self) -> None:
        self._min: list[float] | None = None
        self._max: list[float] | None = None

    def update(self, coords_text: str) -> None:
        parts = coords_text.split()
        if len(parts) < 3:
            return
        try:
            self.update_xyz(float(parts[0]), float(parts[1]), float(parts[2]))
        except ValueError:
            return

    def update_xyz(self, x: float, y: float, z: float) -> None:
        point = [x, y, z]
        if self._min is None:
            self._min = list(point)
            self._max = list(point)
            return
        for axis in range(3):
            self._min[axis] = min(self._min[axis], point[axis])
            self._max[axis] = max(self._max[axis], point[axis])

    def minimum(self) -> list[float] | None:
        return [round(value, 6) for value in self._min] if self._min else None

    def maximum(self) -> list[float] | None:
        return [round(value, 6) for value in self._max] if self._max else None


# --------------------------------------------------------------------------- #
# Shared helpers
# --------------------------------------------------------------------------- #


def _write_media_asset(
    conn: sqlite3.Connection,
    asset_id: str,
    item: dict[str, Any],
    media_class: str,
    now: str,
    *,
    status: str = "current",
) -> None:
    conn.execute(
        """
        INSERT INTO "media_assets"
        (asset_id, source_item_id, media_class, primary_artifact_id,
         inspect_status, attrs_json, updated_at)
        VALUES (?, ?, ?, NULL, ?, ?, ?)
        ON CONFLICT(asset_id) DO UPDATE SET
            source_item_id = excluded.source_item_id,
            media_class = excluded.media_class,
            inspect_status = excluded.inspect_status,
            attrs_json = excluded.attrs_json,
            updated_at = excluded.updated_at
        """,
        (
            asset_id,
            item["source_item_id"],
            media_class,
            status,
            json.dumps({"media_type": item["media_type"]}),
            now,
        ),
    )


def _store_thumbnail(
    conn: sqlite3.Connection,
    asset_id: str,
    payload: bytes,
    size: tuple[int, int],
    *,
    now: str,
) -> None:
    blob = store_artifact_blob(conn, payload=payload, now=now)
    artifact_id = _stable_id("masset", asset_id, "thumbnail")
    conn.execute(
        """
        INSERT INTO "media_artifacts"
        (artifact_id, asset_id, artifact_kind, blob_id, width, height, attrs_json)
        VALUES (?, ?, 'thumbnail', ?, ?, ?, NULL)
        ON CONFLICT(artifact_id) DO UPDATE SET
            blob_id = excluded.blob_id,
            width = excluded.width,
            height = excluded.height
        """,
        (artifact_id, asset_id, blob["blob_id"], size[0], size[1]),
    )
    conn.execute(
        'UPDATE "media_assets" SET primary_artifact_id = ? WHERE asset_id = ?',
        (artifact_id, asset_id),
    )


def _media_items_for_root(root_id: str, limit: int | None) -> list[dict[str, Any]]:
    sql = """
        SELECT source_item_id, relative_path, source_uri, media_type
        FROM "source_items"
        WHERE root_id = ?
          AND item_kind = 'file'
          AND inventory_status IN ('current', 'unchanged', 'changed')
          AND (media_type LIKE 'image/%' OR media_type LIKE 'video/%'
               OR media_type LIKE 'model/%')
        ORDER BY relative_path
    """
    params: list[Any] = [root_id]
    if limit is not None:
        sql += " LIMIT ?"
        params.append(limit)
    with catalog_connection() as conn:
        rows = conn.execute(sql, params).fetchall()
    items = []
    for row in rows:
        media_type = row["media_type"] or ""
        items.append(
            {
                "source_item_id": row["source_item_id"],
                "relative_path": row["relative_path"],
                "source_uri": row["source_uri"],
                "media_type": row["media_type"],
                "media_class": _media_class(media_type),
            }
        )
    return items


def _media_class(media_type: str) -> str | None:
    if media_type.startswith("image/"):
        return "image"
    if media_type.startswith("video/"):
        return "video"
    if media_type.startswith("model/"):
        return "model3d"
    if media_type.startswith("audio/"):
        return "audio"
    return None


def _asset_id(item: dict[str, Any]) -> str:
    return _stable_id("asset", item["source_item_id"])


def _load_pillow() -> Any | None:
    try:
        from PIL import Image  # type: ignore[import-not-found]
    except (ModuleNotFoundError, ImportError):
        return None
    try:
        from pillow_heif import register_heif_opener  # type: ignore[import-not-found]

        register_heif_opener()
    except (ModuleNotFoundError, ImportError):
        pass
    return Image


def _load_pymediainfo() -> Any | None:
    try:
        from pymediainfo import MediaInfo  # type: ignore[import-not-found]
    except (ModuleNotFoundError, ImportError):
        return None
    if not MediaInfo.can_parse():
        return None
    return MediaInfo


def _json_or_none(value: Any) -> str | None:
    return json.dumps(value) if value is not None else None


def _as_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip().strip("\x00").strip()
    return text or None


def _stable_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256("\0".join(parts).encode("utf-8")).hexdigest()[:32]
    return f"{prefix}_{digest}"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")
