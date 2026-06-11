"""Contract file discovery helpers."""

from __future__ import annotations

from importlib import resources
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def read_contract_text(relative_path: str) -> str:
    """Read a packaged or source-tree contract file."""

    source_path = _repo_root() / relative_path
    if source_path.exists():
        return source_path.read_text(encoding="utf-8")

    package_path = "contracts/" + relative_path.replace("\\", "/")
    return resources.files("even").joinpath(package_path).read_text(
        encoding="utf-8"
    )
