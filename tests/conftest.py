from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def isolate_even_paths(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Isolate every test from developer Even state.

    The ``EVEN_CACHE``/``EVEN_HOME`` env vars (and a cwd ``.env``) take
    precedence over ``workspace_root()``. Without forcing test-local values, a
    shell export or repository ``.env`` can make tests read or write a real
    catalog instead of their ``tmp_path`` sandbox. Tests that exercise the
    env-var feature set the vars explicitly after this autouse fixture runs.
    """

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("EVEN_CACHE", str(tmp_path / ".cache"))
    monkeypatch.setenv("EVEN_HOME", str(tmp_path / ".even-home"))
