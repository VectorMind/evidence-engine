"""SQLite catalog creation and status reporting."""

from __future__ import annotations

from dataclasses import dataclass
import re
import sqlite3
from typing import Any

import yaml

from even.contracts import read_contract_text
from even.db import catalog_connection
from even.paths import catalog_path


CATALOG_SCHEMA_VERSION = "0.10"
CATALOG_USER_VERSION = 10


@dataclass(frozen=True)
class Column:
    name: str
    kind: str
    ref: str | None = None


@dataclass(frozen=True)
class Index:
    name: str
    columns: tuple[str, ...]
    unique: bool = False


@dataclass(frozen=True)
class Table:
    name: str
    columns: tuple[Column, ...]
    indexes: tuple[Index, ...]


def load_catalog_tables() -> list[Table]:
    """Load table definitions from catalog.yaml."""

    data = yaml.safe_load(read_contract_text("catalog.yaml"))
    tables_data = data["datasets"][0]["tables"]
    tables: list[Table] = []
    for table_data in tables_data:
        columns = tuple(
            Column(
                name=column_data["name"],
                kind=column_data["type"],
                ref=column_data.get("ref"),
            )
            for column_data in table_data.get("columns", [])
        )
        indexes = tuple(
            Index(
                name=index_data["name"],
                columns=tuple(index_data.get("columns", [])),
                unique=bool(index_data.get("unique", False)),
            )
            for index_data in table_data.get("indexes", [])
        )
        tables.append(Table(name=table_data["name"], columns=columns, indexes=indexes))
    return tables


def create_catalog() -> dict[str, Any]:
    """Create the workspace catalog if missing and return a structured report."""

    path = catalog_path()
    before_exists = path.exists()
    status_before = catalog_status_report() if before_exists else {"status": "missing"}
    if before_exists:
        if status_before["status"] == "current":
            return {
                "status": "current",
                "created": False,
                "sqlite_user_version": status_before["sqlite_user_version"],
                "expected_tables": status_before["expected_tables"],
                "table_count": status_before["table_count"],
            }
        return {
            "status": "reset_required",
            "created": False,
            "error_kind": "catalog_reset_required",
            "catalog_status": status_before["status"],
            "message": "Run catalog wipe before recreating a stale beta catalog.",
        }
    path.parent.mkdir(parents=True, exist_ok=True)
    tables = load_catalog_tables()

    with catalog_connection() as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        before_version = _user_version(conn)
        if before_version > CATALOG_USER_VERSION:
            return {
                "status": "failed",
                "error_kind": "catalog_version_ahead",
                "sqlite_user_version": before_version,
                "expected_user_version": CATALOG_USER_VERSION,
            }

        _apply_schema(conn, tables)

    return {
        "status": "created",
        "created": True,
        "sqlite_user_version_before": before_version,
        "sqlite_user_version": CATALOG_USER_VERSION,
        "expected_tables": [table.name for table in tables],
        "table_count": len(tables),
    }


def wipe_catalog() -> dict[str, Any]:
    """Delete the workspace-local catalog database if it exists."""

    path = catalog_path()
    existed = path.exists()
    if existed:
        path.unlink()
    return {
        "status": "wiped" if existed else "missing",
        "existed": existed,
        "message": "Workspace catalog was removed." if existed else "No catalog existed.",
    }


def catalog_status_report() -> dict[str, Any]:
    """Return structured status for the fixed catalog."""

    path = catalog_path()
    tables = load_catalog_tables()
    expected_table_names = [table.name for table in tables]
    if not path.exists():
        return {
            "status": "missing",
            "exists": False,
            "sqlite_user_version": None,
            "expected_user_version": CATALOG_USER_VERSION,
            "expected_tables": expected_table_names,
            "missing_tables": expected_table_names,
            "table_count": 0,
            "row_counts": {},
        }

    try:
        with catalog_connection(read_only=True) as conn:
            current_tables = {
                row["name"]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                ).fetchall()
            }
            user_version = _user_version(conn)
            row_counts = {
                table_name: conn.execute(
                    f'SELECT COUNT(*) FROM "{table_name}"'
                ).fetchone()[0]
                for table_name in expected_table_names
                if table_name in current_tables
            }
    except sqlite3.Error as exc:
        return {
            "status": "error",
            "exists": True,
            "error_kind": "sqlite_error",
            "redacted_detail": str(exc),
        }

    missing_tables = [
        table_name for table_name in expected_table_names if table_name not in current_tables
    ]
    extra_tables = sorted(current_tables - set(expected_table_names))
    if user_version > CATALOG_USER_VERSION:
        status = "ahead"
    elif missing_tables:
        status = "incomplete"
    elif user_version < CATALOG_USER_VERSION:
        status = "stale"
    else:
        status = "current"

    return {
        "status": status,
        "exists": True,
        "sqlite_user_version": user_version,
        "expected_user_version": CATALOG_USER_VERSION,
        "expected_tables": expected_table_names,
        "missing_tables": missing_tables,
        "extra_tables": extra_tables,
        "table_count": len(current_tables),
        "row_counts": row_counts,
    }


def ensure_catalog() -> dict[str, Any]:
    """Create or validate the workspace catalog before producer commands write."""

    status = catalog_status_report()
    if status["status"] == "missing":
        return create_catalog()
    if status["status"] == "current":
        return status
    if status["status"] in {"stale", "incomplete", "ahead"}:
        return {
            "status": "reset_required",
            "error_kind": "catalog_reset_required",
            "catalog_status": status["status"],
            "message": "Run catalog wipe before recreating a stale beta catalog.",
        }
    return status


def _apply_schema(conn: sqlite3.Connection, tables: list[Table]) -> None:
    for table in tables:
        conn.execute(_create_table_sql(table))
    for table in tables:
        for index in table.indexes:
            conn.execute(_create_index_sql(table.name, index))
    conn.execute(f"PRAGMA user_version = {CATALOG_USER_VERSION}")
    conn.commit()


def _create_table_sql(table: Table) -> str:
    column_sql = ", ".join(_column_sql(column) for column in table.columns)
    return f'CREATE TABLE IF NOT EXISTS "{table.name}" ({column_sql})'


def _column_sql(column: Column) -> str:
    sql_type = _sqlite_type(column.kind)
    parts = [f'"{column.name}"', sql_type]
    if column.ref:
        ref_table, ref_column = _parse_ref(column.ref)
        if ref_table and ref_column:
            parts.append(f'REFERENCES "{ref_table}"("{ref_column}")')
    return " ".join(parts)


def _create_index_sql(table_name: str, index: Index) -> str:
    unique = "UNIQUE " if index.unique else ""
    columns = ", ".join(f'"{column}"' for column in index.columns)
    return (
        f'CREATE {unique}INDEX IF NOT EXISTS "{index.name}" '
        f'ON "{table_name}" ({columns})'
    )


def _sqlite_type(kind: str) -> str:
    normalized = kind.lower()
    if normalized in {"text", "enum", "timestamp", "json"}:
        return "TEXT"
    if normalized == "integer":
        return "INTEGER"
    if normalized == "real":
        return "REAL"
    if normalized == "blob":
        return "BLOB"
    return "TEXT"


def _parse_ref(ref: str) -> tuple[str | None, str | None]:
    match = re.fullmatch(r"[^.]+\.([^.]+)\.([^.]+)", ref)
    if not match:
        return None, None
    return match.group(1), match.group(2)


def _user_version(conn: sqlite3.Connection) -> int:
    return int(conn.execute("PRAGMA user_version").fetchone()[0])
