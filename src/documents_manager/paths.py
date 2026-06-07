"""Shared filesystem locations for documents-manager."""

from __future__ import annotations

from pathlib import Path


WORKSPACE_DIR_NAME = ".documents-manager"


def workspace_root() -> Path:
    """Return the caller-workspace documents-manager storage root."""

    return Path.cwd() / WORKSPACE_DIR_NAME


def fixed_cache_root() -> Path:
    """Return the generated storage root.

    Internal modules still call this while the storage contract is being
    renamed. It now points at the caller workspace, not the user's home cache.
    """

    return workspace_root()


def catalog_path() -> Path:
    """Return the workspace-local SQLite catalog path."""

    return workspace_root() / "catalog" / "catalog.sqlite"


def results_root() -> Path:
    """Return the workspace-local command results directory root."""

    return workspace_root() / "results"


def reports_root() -> Path:
    """Return the workspace-local optional HTML reports directory root."""

    return workspace_root() / "reports"
