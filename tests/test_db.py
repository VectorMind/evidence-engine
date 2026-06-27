from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from even.db import catalog_connection
from even.paths import catalog_path


def _prepare(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    catalog_path().parent.mkdir(parents=True, exist_ok=True)


def test_catalog_connection_yields_row_factory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _prepare(tmp_path, monkeypatch)
    with catalog_connection() as conn:
        conn.execute("CREATE TABLE t (a TEXT, b INTEGER)")
        conn.execute("INSERT INTO t VALUES ('x', 1)")

    with catalog_connection() as conn:
        row = conn.execute("SELECT a, b FROM t").fetchone()

    assert row["a"] == "x"  # keyed access
    assert row["b"] == 1
    assert row[0] == "x"  # positional still works on sqlite3.Row


def test_catalog_connection_commits_on_clean_exit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _prepare(tmp_path, monkeypatch)
    with catalog_connection() as conn:
        conn.execute("CREATE TABLE t (a TEXT)")
        conn.execute("INSERT INTO t VALUES ('y')")

    with catalog_connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM t").fetchone()[0] == 1


def test_catalog_connection_rolls_back_on_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _prepare(tmp_path, monkeypatch)
    with catalog_connection() as conn:
        conn.execute("CREATE TABLE t (a TEXT)")

    with pytest.raises(RuntimeError):
        with catalog_connection() as conn:
            conn.execute("INSERT INTO t VALUES ('z')")
            raise RuntimeError("boom")

    with catalog_connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM t").fetchone()[0] == 0


def test_catalog_connection_read_only_blocks_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _prepare(tmp_path, monkeypatch)
    with catalog_connection() as conn:
        conn.execute("CREATE TABLE t (a TEXT)")

    with pytest.raises(sqlite3.OperationalError):
        with catalog_connection(read_only=True) as conn:
            conn.execute("INSERT INTO t VALUES ('x')")
