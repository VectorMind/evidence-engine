"""Catalog reference helpers.

Implements the Reference Contract from
``specifications/corpus-cache-cli/spec.md``: a reference to an evidence row is
the catalog coordinate ``corpus_cache.<table>.<row_id>``. Search hits and result
payloads expose this string so upper layers can store it as a plain ``ref:``
column without copying lower rows. Kind, locator, and provenance stay as columns
on the referenced row and are resolved by reading it.
"""

from __future__ import annotations

import re
import sqlite3
from typing import Any

from even.catalog import load_catalog_tables
from even.db import catalog_connection

# Public dataset name, shared with catalog.yaml. References are namespaced with
# it so cross-catalog pointers stay unambiguous.
DATASET = "corpus_cache"

_REF_PATTERN = re.compile(r"([^.]+)\.([^.]+)\.([^.]+)")


def evidence_ref(table: str, row_id: str) -> str:
    """Return the ``corpus_cache.<table>.<row_id>`` reference for a catalog row."""

    return f"{DATASET}.{table}.{row_id}"


def parse_ref(ref: str) -> tuple[str, str, str] | None:
    """Split a ``dataset.table.row_id`` reference, or ``None`` if malformed."""

    match = _REF_PATTERN.fullmatch(ref)
    if not match:
        return None
    return match.group(1), match.group(2), match.group(3)


def resolve_ref(ref: str) -> dict[str, Any] | None:
    """Resolve a reference to its current catalog row, per the Reference Contract.

    Reads the live row so kind, locator, and provenance columns reflect current
    state rather than a stale copy. Returns ``None`` when the reference is
    malformed, points at an unknown table, the catalog does not exist yet, or
    the row is gone.
    """

    parsed = parse_ref(ref)
    if parsed is None:
        return None
    dataset, table, row_id = parsed
    if dataset != DATASET:
        return None
    tables = {t.name: t for t in load_catalog_tables("corpus_cache")}
    target = tables.get(table)
    if target is None:
        return None
    pk_column = _primary_key_column(target)
    if pk_column is None:
        return None
    try:
        with catalog_connection(read_only=True) as conn:
            row = conn.execute(
                f'SELECT * FROM "{table}" WHERE "{pk_column}" = ?', (row_id,)
            ).fetchone()
    except sqlite3.Error:
        return None
    return dict(row) if row is not None else None


def _primary_key_column(table: Any) -> str | None:
    for index in table.indexes:
        if index.name == f"pk_{table.name}" and index.unique and index.columns:
            return index.columns[0]
    return None


def attach_hit_refs(payload: dict[str, Any]) -> dict[str, Any]:
    """Add a canonical ``ref`` to every hit in a search result payload.

    A search hit's evidence row is its normalized document object, so the
    reference points at ``corpus_cache.document_objects.<object_id>``. Hits that
    already carry a ``ref`` (for example media hits pointing at ``media_assets``)
    keep it; hits with no object id and no ref get a null ref rather than a
    fabricated one. Mutates and returns the payload.
    """

    for hit in payload.get("hits", []):
        if hit.get("ref"):
            continue
        object_id = hit.get("object_id")
        hit["ref"] = evidence_ref("document_objects", object_id) if object_id else None
    return payload
