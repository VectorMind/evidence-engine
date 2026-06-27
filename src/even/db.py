"""Shared catalog database access.

A single place to open the workspace catalog so every module reads rows by
column name (``sqlite3.Row``) instead of fragile positional indexing, and so the
connection is always closed. A bare ``with sqlite3.connect(...) as conn`` only
wraps a transaction; it leaves the connection open. ``catalog_connection``
commits on a clean exit, rolls back on error, and closes either way.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
import sqlite3

from even.paths import catalog_path


@contextmanager
def catalog_connection(*, read_only: bool = False) -> Iterator[sqlite3.Connection]:
    """Open the workspace catalog with column-name row access.

    The yielded connection uses ``sqlite3.Row`` so callers index rows by name
    (``row["object_id"]``) as well as by position. Pass ``read_only=True`` to
    open the database with SQLite ``mode=ro``. The transaction is committed on a
    clean exit and rolled back on an exception; the connection is always closed.
    """

    if read_only:
        conn = sqlite3.connect(f"file:{catalog_path()}?mode=ro", uri=True)
    else:
        conn = sqlite3.connect(catalog_path())
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()
