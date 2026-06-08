"""Catalog reference helpers.

Implements the Reference Contract from
``specifications/corpus-cache-cli/spec.md``: a reference to an evidence row is
the catalog coordinate ``corpus_cache.<table>.<row_id>``. Search hits and result
payloads expose this string so upper layers can store it as a plain ``ref:``
column without copying lower rows. Kind, locator, and provenance stay as columns
on the referenced row and are resolved by reading it.
"""

from __future__ import annotations

from typing import Any

# Public dataset name, shared with catalog.yaml. References are namespaced with
# it so cross-catalog pointers stay unambiguous.
DATASET = "corpus_cache"


def evidence_ref(table: str, row_id: str) -> str:
    """Return the ``corpus_cache.<table>.<row_id>`` reference for a catalog row."""

    return f"{DATASET}.{table}.{row_id}"


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
