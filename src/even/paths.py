"""Shared filesystem locations for even."""

from __future__ import annotations

import os
from pathlib import Path


WORKSPACE_DIR_NAME = ".cache"
DEFAULT_HOME_DIR_NAME = ".even"
DOTENV_NAME = ".env"


def even_home() -> Path:
    """Return the shared even home for runtime-level state."""

    configured = _configured_value("EVEN_HOME")
    if configured:
        return _expand_path(configured)
    return Path.home() / DEFAULT_HOME_DIR_NAME


def workspace_root() -> Path:
    """Return the even evidence cache root for the current command.

    ``EVEN_CACHE`` selects the catalog/index/result cache. A value in the
    current directory's ``.env`` overrides the process environment. When unset,
    the cache stays local to the caller's current directory.
    """

    configured = _configured_value("EVEN_CACHE")
    if configured:
        return _expand_path(configured)
    return Path.cwd() / WORKSPACE_DIR_NAME


def fixed_cache_root() -> Path:
    """Return the generated storage root.

    Internal modules still call this while the storage contract is being renamed.
    It now points at ``EVEN_CACHE`` or the caller-local default.
    """

    return workspace_root()


def model_cache_root() -> Path:
    """Return the shared model cache root under ``EVEN_HOME``."""

    return even_home() / "models"


def catalog_path() -> Path:
    """Return the workspace-local SQLite catalog path."""

    return workspace_root() / "catalog" / "catalog.sqlite"


def results_root() -> Path:
    """Return the workspace-local command results directory root."""

    return workspace_root() / "results"


def calibration_path() -> Path:
    """Return the workspace-local machine-calibration file (e.g. tokens/sec)."""

    return workspace_root() / "calibration.json"


def reports_root() -> Path:
    """Return the workspace-local optional HTML reports directory root."""

    return workspace_root() / "reports"


def _configured_value(name: str) -> str | None:
    dotenv = _dotenv_values()
    if name in dotenv:
        return dotenv[name]
    return os.environ.get(name)


def _dotenv_values() -> dict[str, str]:
    path = Path.cwd() / DOTENV_NAME
    if not path.exists():
        return {}

    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        value = value.strip().strip('"').strip("'")
        values[key] = value
    return values


def _expand_path(value: str) -> Path:
    return Path(os.path.expandvars(value)).expanduser()
