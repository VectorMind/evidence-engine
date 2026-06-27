"""Cross-cutting helpers, config accessors, module constants, and shared types
for the routing package."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from even.chunks import stable_id
from even.config import load_parser_config, load_routing_config

GLOBAL_FTS_TEMPLATE = "fts_summary_node"


GLOBAL_SEMANTIC_TEMPLATE = "semantic_summary_node"


GLOBAL_SEMANTIC_TABLE = "summary_nodes"


GLOBAL_SIGLIP_TEMPLATE = "siglip_summary_node"


GLOBAL_SIGLIP_TABLE = "media_representatives"


GLOBAL_FTS_MANIFEST = "manifest.json"


PROMPT_VERSION = "summary_prompt_v2"


MEDIA_PROMPT_VERSION = "media_summary_prompt_v2"


MEDIA_SUMMARY_PROFILE = "media_album_summary_v1"


MEDIA_CLUSTER_PROFILE = "media_cluster_summary_v1"


# Trailing structured importance marker emitted as a summary side output, e.g.
# "IMPORTANCE: 0.8" on its own line. Parsed out of the model text and stored in
# summary_nodes.importance.
_IMPORTANCE_RE = re.compile(
    r"(?im)^\s*importance\s*[:=]\s*(\d+(?:\.\d+)?|\.\d+)\s*$"
)


@dataclass(frozen=True)
class RoutingIndexOptions:
    force: bool = False
    limit: int | None = None
    summary_model: str | None = None
    summary_ollama_url: str | None = None
    max_build_seconds: float | None = None
    build_semantic: bool = False


class SummaryGenerationError(Exception):
    def __init__(self, status: str, error_kind: str, message: str = "") -> None:
        super().__init__(message or error_kind)
        self.status = status
        self.error_kind = error_kind
        self.message = message or error_kind


SummaryGenerator = Callable[..., str]


def _embedding_profile_name() -> str:
    defaults = load_parser_config().get("defaults", {})
    return str(defaults.get("embedding_profile") or "fastembed_bge_small_en_v1_5")


RESERVED_KINDS = ("root_summary", "album_summary")


_NEGATIVE_ROLLUP_IMPORTANCE = 0.05


def _image_profile_name() -> str:
    return str(_routing_defaults().get("image_profile") or "siglip2_base")


def _clean_routing_meta(meta: dict[str, Any]) -> dict[str, Any]:
    """Drop empty facets so routing_meta stays compact and inspectable."""

    return {key: value for key, value in meta.items() if value not in (None, "", [], {})}


def _coverage(sample_count: int, source_count: int) -> float:
    if source_count <= 0:
        return 0.0
    return round(sample_count / source_count, 6)


CALIBRATION_DEFAULT_TPS = 50.0


# Ignore near-instant generations (fake/cached) so they do not skew calibration.
_CALIBRATION_MIN_ELAPSED = 0.05


def _summary_id(scope_id: str) -> str:
    return stable_id("sum", scope_id, "root_summary", "text")


def _media_summary_id(scope_id: str) -> str:
    return stable_id("sum", scope_id, "album_summary", "media")


def _media_cluster_summary_id(scope_id: str, medoid_asset_id: str) -> str:
    return stable_id("sum", scope_id, "media_cluster_summary", medoid_asset_id)


def _empty_watermark(root_id: str, scope_id: str, sample_policy: str) -> str:
    return hashlib.sha256(
        "\0".join([root_id, scope_id, sample_policy, "empty"]).encode("utf-8")
    ).hexdigest()


def _routing_defaults() -> dict[str, Any]:
    return dict(load_routing_config().get("defaults", {}))


def _fts_profile() -> str:
    defaults = load_parser_config().get("defaults", {})
    return str(defaults.get("fts_profile") or "text_default_en")


def _chunk_profile() -> str:
    defaults = load_parser_config().get("defaults", {})
    return str(defaults.get("chunk_profile") or "docling_hybrid_v1")


def _tantivy_runtime_status() -> dict[str, str]:
    try:
        import tantivy  # noqa: F401  # type: ignore[import-not-found]
    except ModuleNotFoundError:
        return {
            "status": "failed",
            "error_kind": "fts_dependency_missing",
            "message": "Install the fts extra before running routing commands.",
        }
    return {"status": "ok"}


def _tantivy_index_exists(index_dir: Path) -> bool:
    try:
        import tantivy  # type: ignore[import-not-found]

        return bool(index_dir.exists() and tantivy.Index.exists(str(index_dir)))
    except Exception:
        return False


def _json_field(stored: dict[str, Any], field: str) -> dict[str, Any]:
    return _json_object(_first(stored, field))


def _json_object(value: Any) -> dict[str, Any]:
    if not value:
        return {}
    try:
        parsed = json.loads(str(value))
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _first(stored: dict[str, Any], field: str) -> Any:
    value = stored.get(field)
    if isinstance(value, list):
        return value[0] if value else None
    return value


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


