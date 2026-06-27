"""Image embedding index and visual search.

Builds a LanceDB store of SigLIP 2 image vectors for media image assets, and
serves ``search image`` (image->image, the primary use) plus text->image queries
over the same joint space. Sources are read in place and never modified.

SigLIP 2 runs through transformers + torch (already present via docling). The
same model serves laptop (CPU) and station (GPU); only device/batch differ.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import importlib.util
import io
import os
from pathlib import Path
from typing import Any

from even.catalog import ensure_catalog
from even.db import catalog_connection
from even.inventory import ScanOptions, scan_folder_to_catalog
from even.media import _ensure_media_asset
from even.paths import model_cache_root, workspace_root
from even.references import evidence_ref
from even.semantic import _quiet_output

os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
os.environ.setdefault("TRANSFORMERS_NO_ADVISORY_WARNINGS", "1")

DEFAULT_IMAGE_PROFILE = "siglip2_base"
_IMAGE_MODELS = {
    "siglip2_base": "google/siglip2-base-patch16-224",
}
TABLE_NAME = "images"
_IMAGE_RUNTIME = ("torch", "transformers", "lancedb", "PIL")

_embedder_cache: dict[str, "_SiglipEmbedder"] = {}


@dataclass(frozen=True)
class ImageIndexOptions:
    force: bool = False
    profile: str = DEFAULT_IMAGE_PROFILE
    limit: int | None = None


@dataclass(frozen=True)
class ImageSearchOptions:
    limit: int = 30
    text: str | None = None
    profile: str | None = None


def image_runtime_status() -> dict[str, Any]:
    missing = [m for m in _IMAGE_RUNTIME if importlib.util.find_spec(m) is None]
    if missing:
        return {
            "status": "failed",
            "error_kind": "image_dependencies_missing",
            "message": "Install the image-search extra (transformers, torch) first.",
            "missing": ",".join(missing),
        }
    return {"status": "ok"}


def index_scope_to_image(path: Path, options: ImageIndexOptions) -> dict[str, Any]:
    """Build or refresh the image-embedding store for a folder scope."""

    runtime = image_runtime_status()
    if runtime["status"] != "ok":
        return runtime
    if options.profile not in _IMAGE_MODELS:
        return {
            "status": "failed",
            "error_kind": "unknown_image_profile",
            "image_profile": options.profile,
        }

    ensure_report = ensure_catalog()
    if ensure_report["status"] not in {"created", "current"}:
        return {
            "status": "failed",
            "error_kind": "catalog_unavailable",
            "catalog_status": ensure_report["status"],
        }

    scan_result = scan_folder_to_catalog(
        path, ScanOptions(max_files=None, max_bytes=None, max_depth=None)
    )
    if scan_result["status"] != "ok":
        return {
            "status": scan_result["status"],
            "error_kind": "auto_scan_failed",
            "scan_result": scan_result,
        }

    root_id = scan_result["root_id"]
    scope_id = scan_result["scope_id"]
    root_label = scan_result.get("root_label") or ""
    assets = _image_assets_for_root(root_id, scope_id, root_label, options.limit)
    if not assets:
        return {
            "status": "deferred",
            "error_kind": "no_image_assets",
            "message": "No image source items were found to embed.",
            "root_id": root_id,
            "scope_id": scope_id,
            "image_profile": options.profile,
            "counts": {"assets_planned": 0, "assets_indexed": 0},
        }

    model_id = _IMAGE_MODELS[options.profile]
    store_uri = f"semantic/image/{options.profile}/{scope_id}.lancedb"
    store_dir = workspace_root() / store_uri
    image_store_id = _stable_id("img", scope_id, options.profile)
    watermark = _watermark(assets, options.profile, model_id)
    existing = _image_registry_state(image_store_id)

    if (
        not options.force
        and existing
        and existing["status"] == "current"
        and existing["source_high_watermark"] == watermark
        and _lancedb_store_exists(store_dir)
    ):
        return {
            "status": "ok",
            "index_backend": "image",
            "root_id": root_id,
            "scope_id": scope_id,
            "image_store_id": image_store_id,
            "image_profile": options.profile,
            "embedding_model": model_id,
            "store_uri": store_uri,
            "table_name": TABLE_NAME,
            "index_status": "current",
            "vector_dimension": existing.get("vector_dimension"),
            "source_high_watermark": watermark,
            "counts": {"assets_planned": len(assets), "assets_indexed": 0,
                       "assets_unchanged": len(assets)},
        }

    build = _write_image_store(store_dir, assets, options.profile, model_id)
    now = _iso(_utc_now())
    if build["status"] != "ok":
        _upsert_image_registry(
            image_store_id, scope_id, options.profile, store_uri, 0, len(assets),
            watermark, "failed", now,
        )
        return {
            "status": "failed",
            "error_kind": build["error_kind"],
            "image_store_id": image_store_id,
            "image_profile": options.profile,
            "redacted_detail": build.get("redacted_detail"),
        }

    # Register the embedded assets so refs resolve even before media inspect.
    with catalog_connection() as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        for asset in assets:
            _ensure_media_asset(conn, asset["asset_id"], asset, now)
        conn.commit()

    _upsert_image_registry(
        image_store_id, scope_id, options.profile, store_uri,
        build["vector_dimension"], len(assets), watermark, "current", now,
    )
    return {
        "status": "ok",
        "index_backend": "image",
        "root_id": root_id,
        "scope_id": scope_id,
        "image_store_id": image_store_id,
        "image_profile": options.profile,
        "embedding_model": model_id,
        "store_uri": store_uri,
        "table_name": TABLE_NAME,
        "index_status": "rebuilt" if options.force else "refreshed",
        "vector_dimension": build["vector_dimension"],
        "source_high_watermark": watermark,
        "counts": {"assets_planned": len(assets), "assets_indexed": len(assets),
                   "assets_unchanged": 0},
    }


def search_image_stores(
    image_path: str | None, options: ImageSearchOptions
) -> dict[str, Any]:
    """Search image stores by example image or by text."""

    runtime = image_runtime_status()
    if runtime["status"] != "ok":
        return runtime

    stores = _current_image_stores(options.profile)
    if not stores:
        return {
            "status": "ok",
            "search_backend": "image",
            "counts": {"indexes_searched": 0, "hits_returned": 0},
            "hits": [],
            "message": "No current image stores were registered.",
        }

    skipped: list[dict[str, Any]] = []
    supported_stores = []
    for store in stores:
        if store["image_profile"] not in _IMAGE_MODELS:
            skipped.append(
                _skipped_image_store(
                    store,
                    "unknown_image_profile",
                    image_profile=store.get("image_profile"),
                )
            )
        else:
            supported_stores.append(store)
    if not supported_stores:
        return {
            "status": "ok",
            "search_backend": "image",
            "counts": {
                "indexes_searched": 0,
                "indexes_skipped": len(skipped),
                "hits_returned": 0,
            },
            "hits": [],
            "skipped": skipped[:10],
            "message": "No supported current image stores were registered.",
        }

    profile_name = supported_stores[0]["image_profile"]
    profile_stores = []
    for store in supported_stores:
        if store["image_profile"] != profile_name:
            skipped.append(
                _skipped_image_store(
                    store,
                    "image_profile_incompatible",
                    expected_image_profile=profile_name,
                    image_profile=store.get("image_profile"),
                )
            )
        else:
            profile_stores.append(store)

    try:
        embedder = _load_embedder(profile_name)
        if options.text is not None:
            query_vector = embedder.embed_text(options.text)
            query_kind = "text"
        else:
            query_vector = embedder.embed_image(Path(image_path).read_bytes())
            query_kind = "image"
    except Exception as exc:  # noqa: BLE001 - query embedding boundary.
        return {
            "status": "failed",
            "error_kind": "image_query_embed_failed",
            "redacted_detail": exc.__class__.__name__,
        }

    limit = max(1, int(options.limit or 30))
    query_dimension = len(query_vector)
    searchable_stores = []
    for store in profile_stores:
        store_dimension = _store_vector_dimension(store)
        if store_dimension != query_dimension:
            skipped.append(
                _skipped_image_store(
                    store,
                    "image_vector_dimension_incompatible",
                    vector_dimension=store_dimension,
                    query_dimension=query_dimension,
                )
            )
            continue
        if not _lancedb_store_exists(workspace_root() / store["store_uri"]):
            skipped.append(_skipped_image_store(store, "image_store_unavailable"))
            continue
        searchable_stores.append(store)

    hits: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    for store in searchable_stores:
        result = _search_one_image_store(store, query_vector, limit)
        if result["status"] == "ok":
            hits.extend(result["hits"])
        else:
            failures.append(result)

    hits = sorted(hits, key=lambda hit: float(hit.get("distance", 0)))[:limit]
    return {
        "status": "ok" if not failures else "partial",
        "search_backend": "image",
        "query_kind": query_kind,
        "counts": {
            "indexes_searched": len(searchable_stores),
            "indexes_skipped": len(skipped),
            "index_failures": len(failures),
            "hits_returned": len(hits),
        },
        "hits": hits,
        "failures": failures[:10],
        "skipped": skipped[:10],
    }


# --------------------------------------------------------------------------- #
# Embedding
# --------------------------------------------------------------------------- #


class _SiglipEmbedder:
    def __init__(self, model: Any, processor: Any, torch: Any) -> None:
        self._model = model
        self._processor = processor
        self._torch = torch

    def embed_image(self, image_bytes: bytes) -> list[float]:
        from PIL import Image  # type: ignore[import-not-found]

        with _quiet_output():
            with Image.open(io.BytesIO(image_bytes)) as image:
                rgb = image.convert("RGB")
                inputs = self._processor(images=rgb, return_tensors="pt")
                with self._torch.no_grad():
                    output = self._model.get_image_features(**inputs)
            return self._normalize(self._pooled(output))

    def embed_text(self, text: str) -> list[float]:
        with _quiet_output():
            inputs = self._processor(
                text=[text], return_tensors="pt", padding="max_length"
            )
            with self._torch.no_grad():
                output = self._model.get_text_features(**inputs)
            return self._normalize(self._pooled(output))

    def _pooled(self, output: Any) -> Any:
        # transformers may return a bare tensor or a pooled model output object.
        pooler = getattr(output, "pooler_output", None)
        tensor = pooler if pooler is not None else output
        return tensor[0]

    def _normalize(self, vector: Any) -> list[float]:
        normed = vector / vector.norm()
        return [float(value) for value in normed.tolist()]


def _load_embedder(profile_name: str) -> _SiglipEmbedder:
    if profile_name in _embedder_cache:
        return _embedder_cache[profile_name]
    import torch  # type: ignore[import-not-found]
    from transformers import AutoModel, AutoProcessor  # type: ignore[import-not-found]

    model_id = _IMAGE_MODELS[profile_name]
    cache_dir = str(model_cache_root() / "siglip")
    with _quiet_output():
        model = AutoModel.from_pretrained(model_id, cache_dir=cache_dir)
        model.eval()
        processor = AutoProcessor.from_pretrained(model_id, cache_dir=cache_dir)
    embedder = _SiglipEmbedder(model, processor, torch)
    _embedder_cache[profile_name] = embedder
    return embedder


def _write_image_store(
    store_dir: Path, assets: list[dict[str, Any]], profile_name: str, model_id: str
) -> dict[str, Any]:
    try:
        import lancedb  # type: ignore[import-not-found]

        embedder = _load_embedder(profile_name)
        rows = []
        for asset in assets:
            vector = embedder.embed_image(Path(asset["source_uri"]).read_bytes())
            rows.append(
                {
                    "asset_id": asset["asset_id"],
                    "scope_id": asset["scope_id"],
                    "image_profile": profile_name,
                    "vector": vector,
                    "relative_path": asset["relative_path"],
                    "root_label": asset["root_label"],
                    "media_type": asset["media_type"],
                }
            )
        store_dir.mkdir(parents=True, exist_ok=True)
        with _quiet_output():
            db = lancedb.connect(str(store_dir))
            db.create_table(TABLE_NAME, data=rows, mode="overwrite")
    except Exception as exc:  # noqa: BLE001 - build boundary.
        return {
            "status": "failed",
            "error_kind": "image_write_failed",
            "redacted_detail": exc.__class__.__name__,
        }
    return {"status": "ok", "vector_dimension": len(rows[0]["vector"]) if rows else 0}


def _search_one_image_store(
    store: dict[str, Any], query_vector: list[float], limit: int
) -> dict[str, Any]:
    try:
        import lancedb  # type: ignore[import-not-found]

        with _quiet_output():
            db = lancedb.connect(str(workspace_root() / store["store_uri"]))
            table = db.open_table(store["table_name"])
            results = table.search(query_vector).limit(limit).to_list()
        hits = [_hit_from_image_row(store, row) for row in results]
    except Exception as exc:  # noqa: BLE001 - search boundary.
        return {
            "status": "failed",
            "error_kind": "image_search_failed",
            "image_store_id": store.get("image_store_id"),
            "redacted_detail": exc.__class__.__name__,
        }
    return {"status": "ok", "hits": hits}


def _store_vector_dimension(store: dict[str, Any]) -> int:
    try:
        return int(store.get("vector_dimension") or 0)
    except (TypeError, ValueError):
        return 0


def _skipped_image_store(
    store: dict[str, Any], error_kind: str, **details: Any
) -> dict[str, Any]:
    return {
        "status": "skipped",
        "error_kind": error_kind,
        "image_store_id": store.get("image_store_id"),
        **details,
    }


def _hit_from_image_row(store: dict[str, Any], row: dict[str, Any]) -> dict[str, Any]:
    distance = float(row.get("_distance", 0.0) or 0.0)
    asset_id = row.get("asset_id")
    return {
        "score": 1.0 / (1.0 + distance),
        "distance": distance,
        "asset_id": asset_id,
        "ref": evidence_ref("media_assets", asset_id) if asset_id else None,
        "scope_id": row.get("scope_id") or store["scope_id"],
        "image_store_id": store["image_store_id"],
        "image_profile": store["image_profile"],
        "media_type": row.get("media_type"),
        "root_label": row.get("root_label"),
        "relative_path": row.get("relative_path"),
    }


# --------------------------------------------------------------------------- #
# Catalog access
# --------------------------------------------------------------------------- #


def _image_assets_for_root(
    root_id: str, scope_id: str, root_label: str, limit: int | None
) -> list[dict[str, Any]]:
    sql = """
        SELECT source_item_id, relative_path, source_uri, media_type
        FROM "source_items"
        WHERE root_id = ?
          AND item_kind = 'file'
          AND inventory_status IN ('current', 'unchanged', 'changed')
          AND media_type LIKE 'image/%'
        ORDER BY relative_path
    """
    params: list[Any] = [root_id]
    if limit is not None:
        sql += " LIMIT ?"
        params.append(limit)
    with catalog_connection() as conn:
        rows = conn.execute(sql, params).fetchall()
    assets = []
    for row in rows:
        source_item_id = row["source_item_id"]
        assets.append(
            {
                "source_item_id": source_item_id,
                "asset_id": _stable_id("asset", source_item_id),
                "relative_path": row["relative_path"],
                "source_uri": row["source_uri"],
                "media_type": row["media_type"],
                "media_class": "image",
                "scope_id": scope_id,
                "root_label": root_label,
            }
        )
    return assets


def _image_registry_state(image_store_id: str) -> dict[str, Any] | None:
    with catalog_connection() as conn:
        row = conn.execute(
            """
            SELECT source_high_watermark, status, vector_dimension
            FROM "image_stores" WHERE image_store_id = ?
            """,
            (image_store_id,),
        ).fetchone()
    if not row:
        return None
    return {
        "source_high_watermark": row["source_high_watermark"],
        "status": row["status"],
        "vector_dimension": row["vector_dimension"],
    }


def _current_image_stores(profile_name: str | None) -> list[dict[str, Any]]:
    sql = """
        SELECT image_store_id, scope_id, image_profile, store_uri, table_name,
               vector_dimension, indexed_asset_count, source_high_watermark
        FROM "image_stores" WHERE status = 'current'
    """
    params: list[Any] = []
    if profile_name:
        sql += " AND image_profile = ?"
        params.append(profile_name)
    sql += " ORDER BY updated_at DESC, image_store_id"
    with catalog_connection() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [
        {
            "image_store_id": row["image_store_id"],
            "scope_id": row["scope_id"],
            "image_profile": row["image_profile"],
            "store_uri": row["store_uri"],
            "table_name": row["table_name"],
            "vector_dimension": row["vector_dimension"],
            "indexed_asset_count": row["indexed_asset_count"],
            "source_high_watermark": row["source_high_watermark"],
        }
        for row in rows
    ]


def _upsert_image_registry(
    image_store_id: str,
    scope_id: str,
    image_profile: str,
    store_uri: str,
    vector_dimension: int,
    indexed_asset_count: int,
    source_high_watermark: str,
    status: str,
    updated_at: str,
) -> None:
    with catalog_connection() as conn:
        conn.execute(
            """
            INSERT INTO "image_stores"
            (image_store_id, scope_id, image_profile, store_uri, table_name,
             vector_dimension, indexed_asset_count, source_high_watermark,
             status, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(image_store_id) DO UPDATE SET
                scope_id = excluded.scope_id,
                image_profile = excluded.image_profile,
                store_uri = excluded.store_uri,
                table_name = excluded.table_name,
                vector_dimension = excluded.vector_dimension,
                indexed_asset_count = excluded.indexed_asset_count,
                source_high_watermark = excluded.source_high_watermark,
                status = excluded.status,
                updated_at = excluded.updated_at
            """,
            (
                image_store_id,
                scope_id,
                image_profile,
                store_uri,
                TABLE_NAME,
                vector_dimension,
                indexed_asset_count,
                source_high_watermark,
                status,
                updated_at,
            ),
        )
        conn.commit()


def read_scope_image_vectors(
    scope_id: str, profile: str = DEFAULT_IMAGE_PROFILE
) -> dict[str, dict[str, Any]] | None:
    """Return the per-scope image proof vectors keyed by ``asset_id``.

    Reads the per-root image store written by ``index scope --image`` and reuses
    its already-computed SigLIP vectors (no model load). Returns ``None`` when no
    store exists for the scope, so callers degrade to no visual fingerprint.
    """

    store_dir = workspace_root() / f"semantic/image/{profile}/{scope_id}.lancedb"
    if not _lancedb_store_exists(store_dir):
        return None
    try:
        import lancedb  # type: ignore[import-not-found]

        with _quiet_output():
            db = lancedb.connect(str(store_dir))
            rows = db.open_table(TABLE_NAME).to_arrow().to_pylist()
    except Exception:  # noqa: BLE001 - read boundary.
        return None
    vectors: dict[str, dict[str, Any]] = {}
    for row in rows:
        asset_id = row.get("asset_id")
        if not asset_id:
            continue
        vectors[str(asset_id)] = {
            "vector": [float(value) for value in (row.get("vector") or [])],
            "relative_path": row.get("relative_path"),
            "root_label": row.get("root_label"),
            "media_type": row.get("media_type"),
        }
    return vectors


def _lancedb_store_exists(store_dir: Path) -> bool:
    try:
        import lancedb  # type: ignore[import-not-found]

        if not store_dir.exists():
            return False
        db = lancedb.connect(str(store_dir))
        return TABLE_NAME in db.table_names()
    except Exception:  # noqa: BLE001
        return False


def _watermark(assets: list[dict[str, Any]], profile: str, model_id: str) -> str:
    parts = [profile, model_id, str(len(assets))]
    parts.extend(sorted(asset["source_item_id"] for asset in assets))
    return hashlib.sha256("\0".join(parts).encode("utf-8")).hexdigest()[:32]


def _stable_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256("\0".join(parts).encode("utf-8")).hexdigest()[:32]
    return f"{prefix}_{digest}"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")
