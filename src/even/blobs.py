"""Artifact blob storage with inline/external thresholding."""

from __future__ import annotations

from datetime import datetime, timezone
import gzip
import hashlib
from pathlib import Path
import sqlite3
from typing import Any

from even.config import load_parser_config
from even.paths import workspace_root


def store_artifact_blob(
    conn: sqlite3.Connection,
    *,
    payload: bytes,
    now: str | None = None,
) -> dict[str, Any]:
    """Store payload bytes according to the configured blob policy."""

    if now is None:
        now = _iso(_utc_now())
    profile = _artifact_profile()
    sha256 = hashlib.sha256(payload).hexdigest()
    blob_id = f"blob_{sha256[:32]}"
    external_threshold = int(profile.get("external_threshold_bytes", 524288))
    compression_min = int(profile.get("inline_compression_min_bytes", 32768))
    compression = "none"
    stored_payload = payload
    storage_mode = "inline_blob"
    relative_uri = None

    if len(payload) >= compression_min and _is_zstd_available():
        try:
            import zstandard as zstd  # type: ignore[import-not-found]

            stored_payload = zstd.ZstdCompressor(level=3).compress(payload)
            compression = "zstd"
        except Exception:
            stored_payload = payload
            compression = "none"
    elif len(payload) >= compression_min:
        stored_payload = gzip.compress(payload)
        compression = "gzip"

    if len(payload) > external_threshold:
        storage_mode = "external_file"
        relative_uri = _blob_relative_uri(sha256)
        target = workspace_root() / relative_uri
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(stored_payload)
        stored_inline = None
    else:
        stored_inline = stored_payload

    conn.execute(
        """
        INSERT INTO "artifact_blobs"
        (blob_id, sha256, size_bytes, storage_mode, compression, relative_uri,
         payload, first_seen_at, last_seen_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(blob_id) DO UPDATE SET
            sha256 = excluded.sha256,
            size_bytes = excluded.size_bytes,
            storage_mode = excluded.storage_mode,
            compression = excluded.compression,
            relative_uri = excluded.relative_uri,
            payload = excluded.payload,
            last_seen_at = excluded.last_seen_at
        """,
        (
            blob_id,
            sha256,
            len(payload),
            storage_mode,
            compression,
            relative_uri,
            stored_inline,
            now,
            now,
        ),
    )
    return {
        "blob_id": blob_id,
        "sha256": sha256,
        "size_bytes": len(payload),
        "storage_mode": storage_mode,
        "compression": compression,
        "relative_uri": relative_uri,
    }


def _artifact_profile() -> dict[str, Any]:
    config = load_parser_config()
    profile_name = config["defaults"].get(
        "artifact_storage_profile", "default_artifact_blobs"
    )
    # The parser config names the profile; the exposure config owns values. Keep
    # defaults here so parse can run before PyYAML is installed.
    if profile_name == "default_artifact_blobs":
        return {
            "external_threshold_bytes": 524288,
            "inline_compression_min_bytes": 32768,
        }
    return {
        "external_threshold_bytes": 524288,
        "inline_compression_min_bytes": 32768,
    }


def _blob_relative_uri(sha256: str) -> Path:
    now = _utc_now()
    return (
        Path("blobs")
        / now.strftime("%Y")
        / now.strftime("%m")
        / sha256[:2]
        / sha256
    )


def _is_zstd_available() -> bool:
    try:
        import zstandard  # noqa: F401
    except ModuleNotFoundError:
        return False
    return True


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")
