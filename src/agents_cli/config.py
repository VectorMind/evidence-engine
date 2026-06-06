"""Runtime access to repository configuration contracts."""

from __future__ import annotations

import re
from typing import Any

from agents_cli.contracts import read_contract_text


def load_parser_config() -> dict[str, Any]:
    """Load parser defaults from config/parser.yaml."""

    text = read_contract_text("config/parser.yaml")
    try:
        import yaml  # type: ignore[import-not-found]
    except ModuleNotFoundError:
        return _load_parser_config_fallback(text)

    return yaml.safe_load(text)


def _load_parser_config_fallback(text: str) -> dict[str, Any]:
    return {
        "defaults": {
            "parser_profile": _scalar(text, "parser_profile", "docling_default"),
            "artifact_storage_profile": _scalar(
                text, "artifact_storage_profile", "default_artifact_blobs"
            ),
            "artifact_outputs": _list(text, "artifact_outputs", []),
            "fts_profile": _scalar(text, "fts_profile", "tantivy_default_en"),
            "embedding_profile": _scalar(
                text, "embedding_profile", "fastembed_bge_small_en_v1_5"
            ),
            "chunk_profile": _scalar(text, "chunk_profile", "docling_hybrid_v1"),
            "store_policy": _scalar(text, "store_policy", "one_per_root"),
            "scan_mode": _scalar(text, "scan_mode", "folder_tree"),
            "create_index_for_folder_root": _scalar(
                text, "create_index_for_folder_root", True
            ),
            "results_format": _scalar(text, "results_format", "jsonl"),
        },
        "folder_safeguards": {
            "max_files_default": _scalar(text, "max_files_default", 5000),
            "max_files_requires_override": _scalar(
                text, "max_files_requires_override", True
            ),
            "max_bytes_default": _scalar(text, "max_bytes_default", 10737418240),
            "max_parse_seconds_default": _scalar(
                text, "max_parse_seconds_default", 3600
            ),
            "max_depth_default": _scalar(text, "max_depth_default", None),
            "follow_symlinks_default": _scalar(
                text, "follow_symlinks_default", False
            ),
            "include_globs_default": _list(text, "include_globs_default", []),
            "exclude_globs_default": _list(text, "exclude_globs_default", []),
        },
        "parser_profiles": [
            {
                "name": "docling_default",
                "description": "Default balanced Docling parse profile.",
                "ocr": "auto",
                "table_structure": True,
                "picture_classification": True,
                "picture_description": False,
            },
            {
                "name": "docling_ocr",
                "description": "OCR-enabled Docling profile for scanned or low-text documents.",
                "ocr": True,
                "table_structure": True,
                "picture_classification": True,
                "picture_description": False,
            },
            {
                "name": "docling_fast_text",
                "description": "Faster text-first profile for simple markup or text-heavy sources.",
                "ocr": False,
                "table_structure": False,
                "picture_classification": False,
                "picture_description": False,
            },
        ],
    }


def _scalar(text: str, key: str, default: Any) -> Any:
    match = re.search(rf"^\s*{re.escape(key)}:\s*(.+?)\s*$", text, re.MULTILINE)
    if not match:
        return default
    return _parse_value(match.group(1))


def _list(text: str, key: str, default: list[str]) -> list[str]:
    value = _scalar(text, key, default)
    if isinstance(value, list):
        return [str(item) for item in value]
    return default


def _parse_value(raw: str) -> Any:
    value = raw.strip()
    if value in {"null", "~"}:
        return None
    if value == "true":
        return True
    if value == "false":
        return False
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [_parse_value(part.strip()) for part in inner.split(",")]
    if value.startswith('"') and value.endswith('"'):
        return value[1:-1]
    if value.startswith("'") and value.endswith("'"):
        return value[1:-1]
    try:
        return int(value)
    except ValueError:
        return value
