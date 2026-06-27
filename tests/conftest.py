from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def clear_even_path_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Isolate every test from the developer's even path environment.

    The ``EVEN_CACHE``/``EVEN_HOME`` env vars (and a cwd ``.env``) take
    precedence over ``workspace_root()``. Without clearing them, a shell that
    exports either var makes tests read the real ``~/.even`` catalog instead of
    their ``tmp_path`` sandbox. Tests that exercise the env-var feature set the
    vars explicitly after this autouse fixture has cleared the inherited ones.
    """

    for name in ("EVEN_CACHE", "EVEN_HOME"):
        monkeypatch.delenv(name, raising=False)
