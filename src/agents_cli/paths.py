"""Shared filesystem locations for agents-docs."""

from __future__ import annotations

from pathlib import Path


CACHE_DIR_NAME = "agents-docs"


def fixed_cache_root() -> Path:
    """Return the non-configurable agents-docs home cache root."""

    return Path.home() / ".cache" / CACHE_DIR_NAME


def catalog_path() -> Path:
    """Return the fixed SQLite catalog path."""

    return fixed_cache_root() / "catalog" / "catalog.sqlite"


def results_root() -> Path:
    """Return the fixed command results directory root."""

    return fixed_cache_root() / ".results"
