"""SQLite catalog creation and status reporting."""

from __future__ import annotations

from dataclasses import dataclass
import re
import sqlite3
from typing import Any

from even.contracts import read_contract_text
from even.paths import catalog_path


CATALOG_SCHEMA_VERSION = "0.7"
CATALOG_USER_VERSION = 7


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
    """Load table definitions from catalog.yaml.

    PyYAML is the normal parser once base dependencies are installed. The
    fallback parser handles this repository's deliberately simple schema shape
    so catalog commands can run in the stdlib-only scaffold environment.
    """

    text = read_contract_text("catalog.yaml")
    try:
        import yaml  # type: ignore[import-not-found]
    except ModuleNotFoundError:
        return _load_catalog_tables_fallback(text)

    data = yaml.safe_load(text)
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


def _load_catalog_tables_fallback(text: str) -> list[Table]:
    tables: list[Table] = []
    current_table: str | None = None
    current_columns: list[Column] = []
    current_indexes: list[Index] = []
    in_columns = False
    in_indexes = False
    pending_index_name: str | None = None
    pending_index_columns: tuple[str, ...] | None = None
    pending_index_unique = False

    def flush_index() -> None:
        nonlocal pending_index_name, pending_index_columns, pending_index_unique
        if pending_index_name and pending_index_columns is not None:
            current_indexes.append(
                Index(
                    name=pending_index_name,
                    columns=pending_index_columns,
                    unique=pending_index_unique,
                )
            )
        pending_index_name = None
        pending_index_columns = None
        pending_index_unique = False

    def flush_table() -> None:
        nonlocal current_table, current_columns, current_indexes
        if current_table:
            flush_index()
            tables.append(
                Table(
                    name=current_table,
                    columns=tuple(current_columns),
                    indexes=tuple(current_indexes),
                )
            )
        current_table = None
        current_columns = []
        current_indexes = []

    for line in text.splitlines():
        stripped = line.strip()
        indent = len(line) - len(line.lstrip(" "))

        if indent == 6 and stripped.startswith("- name: "):
            flush_table()
            current_table = stripped.removeprefix("- name: ").strip()
            in_columns = False
            in_indexes = False
            continue

        if current_table is None:
            continue

        if indent == 8 and stripped == "columns:":
            flush_index()
            in_columns = True
            in_indexes = False
            continue

        if indent == 8 and stripped == "indexes:":
            in_columns = False
            in_indexes = True
            continue

        if in_columns and indent == 10 and stripped.startswith("- {"):
            current_columns.append(_parse_column_line(stripped))
            continue

        if in_indexes and indent == 10 and stripped.startswith("- name: "):
            flush_index()
            pending_index_name = stripped.removeprefix("- name: ").strip()
            continue

        if in_indexes and indent == 12 and stripped.startswith("columns: "):
            value = stripped.removeprefix("columns: ").strip()
            pending_index_columns = tuple(
                part.strip()
                for part in value.removeprefix("[").removesuffix("]").split(",")
                if part.strip()
            )
            continue

        if in_indexes and indent == 12 and stripped.startswith("unique: "):
            pending_index_unique = stripped.removeprefix("unique: ").strip() == "true"

    flush_table()
    return tables


def _parse_column_line(line: str) -> Column:
    inner = line.removeprefix("- {").removesuffix("}")
    fields = _split_inline_mapping(inner)
    return Column(
        name=fields["name"],
        kind=fields["type"],
        ref=fields.get("ref"),
    )


def _split_inline_mapping(value: str) -> dict[str, str]:
    parts: list[str] = []
    current: list[str] = []
    quote = False
    bracket_depth = 0
    for char in value:
        if char == '"':
            quote = not quote
        elif not quote and char == "[":
            bracket_depth += 1
        elif not quote and char == "]":
            bracket_depth -= 1
        elif not quote and bracket_depth == 0 and char == ",":
            parts.append("".join(current).strip())
            current = []
            continue
        current.append(char)
    if current:
        parts.append("".join(current).strip())

    fields: dict[str, str] = {}
    for part in parts:
        key, raw = part.split(":", 1)
        cleaned = raw.strip()
        if cleaned.startswith('"') and cleaned.endswith('"'):
            cleaned = cleaned[1:-1]
        fields[key.strip()] = cleaned
    return fields


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

    with sqlite3.connect(path) as conn:
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
        with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as conn:
            current_tables = {
                row[0]
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
