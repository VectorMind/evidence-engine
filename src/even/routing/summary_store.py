"""Summary-node read/write plus the row-budgeting (entry selection) layer."""

from __future__ import annotations

import json
import math
from typing import Any

from even.db import catalog_connection
from even.routing.shared import (
    _NEGATIVE_ROLLUP_IMPORTANCE,
    RESERVED_KINDS,
    _json_object,
    _routing_defaults,
)


def _upsert_summary_row(
    *,
    summary_id: str,
    root_id: str,
    scope_id: str,
    source_item_id: str | None,
    title: str,
    summary_text: str,
    routing_meta: dict[str, Any],
    source_refs: list[str],
    source_count: int,
    sample_count: int,
    coverage_estimate: float,
    sample_policy: str,
    producer: str,
    profile: str,
    watermark: str,
    status: str,
    attrs: dict[str, Any],
    now: str,
    created_at: str | None,
    parent_summary_id: str | None = None,
    doc_id: str | None = None,
    kind: str = "root_summary",
    modality: str = "text",
    media_kind: str | None = None,
    container_kind: str = "root",
    summary_level: int = 0,
    importance: float | None = None,
) -> None:
    with catalog_connection() as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute(
            """
            INSERT INTO "summary_nodes"
            (summary_id, root_id, scope_id, parent_summary_id, source_item_id,
             doc_id, kind, modality, media_kind, container_kind, summary_level,
             title, summary_text, routing_meta, source_refs_json, source_count,
             sample_count, coverage_estimate, sample_policy, producer, profile,
             source_high_watermark, summary_status, confidence, importance,
             attrs_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(summary_id) DO UPDATE SET
                root_id = excluded.root_id,
                scope_id = excluded.scope_id,
                parent_summary_id = excluded.parent_summary_id,
                source_item_id = excluded.source_item_id,
                doc_id = excluded.doc_id,
                kind = excluded.kind,
                modality = excluded.modality,
                media_kind = excluded.media_kind,
                container_kind = excluded.container_kind,
                summary_level = excluded.summary_level,
                title = excluded.title,
                summary_text = excluded.summary_text,
                routing_meta = excluded.routing_meta,
                source_refs_json = excluded.source_refs_json,
                source_count = excluded.source_count,
                sample_count = excluded.sample_count,
                coverage_estimate = excluded.coverage_estimate,
                sample_policy = excluded.sample_policy,
                producer = excluded.producer,
                profile = excluded.profile,
                source_high_watermark = excluded.source_high_watermark,
                summary_status = excluded.summary_status,
                confidence = excluded.confidence,
                importance = excluded.importance,
                attrs_json = excluded.attrs_json,
                created_at = excluded.created_at,
                updated_at = excluded.updated_at
            """,
            (
                summary_id,
                root_id,
                scope_id,
                parent_summary_id,
                source_item_id,
                doc_id,
                kind,
                modality,
                media_kind,
                container_kind,
                summary_level,
                title,
                summary_text,
                json.dumps(routing_meta, sort_keys=True),
                json.dumps(source_refs, sort_keys=True),
                source_count,
                sample_count,
                coverage_estimate,
                sample_policy,
                producer,
                profile,
                watermark,
                status,
                None,
                importance,
                json.dumps(attrs, sort_keys=True),
                created_at or now,
                now,
            ),
        )
        conn.commit()


def _summary_state(summary_id: str) -> dict[str, Any] | None:
    with catalog_connection() as conn:
        row = conn.execute(
            """
            SELECT source_high_watermark, summary_status, created_at
            FROM "summary_nodes"
            WHERE summary_id = ?
            """,
            (summary_id,),
        ).fetchone()
    if not row:
        return None
    return {
        "source_high_watermark": row["source_high_watermark"],
        "summary_status": row["summary_status"],
        "created_at": row["created_at"],
    }


def _current_summary_rows() -> list[dict[str, Any]]:
    with catalog_connection() as conn:
        rows = conn.execute(
            """
            SELECT s.summary_id, s.root_id, s.scope_id, s.kind, s.modality,
                   s.title, s.summary_text, s.routing_meta, s.source_refs_json,
                   s.source_high_watermark, s.updated_at, sr.root_label,
                   s.media_kind, s.container_kind, s.source_count,
                   s.coverage_estimate, s.importance
            FROM "summary_nodes" s
            JOIN "source_roots" sr ON sr.root_id = s.root_id
            WHERE s.summary_status = 'current'
            ORDER BY s.root_id, s.scope_id, s.summary_id
            """
        ).fetchall()
    result = []
    for row in rows:
        summary_text = row["summary_text"] or ""
        routing_meta = _json_object(row["routing_meta"])
        routing_payload = _routing_payload(summary_text, routing_meta)
        if not routing_payload.strip():
            continue
        metadata = {
            "root_label": row["root_label"],
            "source_high_watermark": row["source_high_watermark"],
            "updated_at": row["updated_at"],
            "media_kind": row["media_kind"],
            "container_kind": row["container_kind"],
        }
        result.append(
            {
                "summary_id": row["summary_id"],
                "root_id": row["root_id"],
                "scope_id": row["scope_id"],
                "kind": row["kind"],
                "modality": row["modality"],
                "title": row["title"] or row["root_label"] or row["root_id"],
                "summary_text": summary_text,
                "routing_meta": routing_meta,
                "routing_payload": routing_payload,
                "source_refs_json": row["source_refs_json"] or "[]",
                "source_high_watermark": row["source_high_watermark"] or "",
                "source_count": int(row["source_count"] or 0),
                "coverage_estimate": float(row["coverage_estimate"] or 0.0),
                "importance": row["importance"],
                "metadata_json": json.dumps(metadata, sort_keys=True),
            }
        )
    return result


def _entry_budget(source_total: int, max_entries: int) -> int:
    """Log-scaled per-root entry ceiling, so a 10-file root and a 10k-file root
    differ by a few entries, never by volume."""

    items = max(int(source_total), 1)
    scaled = int(round(1 + 2 * math.log10(items)))
    return max(1, min(scaled, max(1, int(max_entries))))


def _precedence_key(row: dict[str, Any]) -> tuple[float, float, str]:
    importance = row.get("importance")
    importance = float(importance) if importance is not None else 0.0
    coverage = float(row.get("coverage_estimate") or 0.0)
    return (-importance, -coverage, str(row.get("summary_id") or ""))


def _negative_rollup(root_id: str, dropped: list[dict[str, Any]]) -> dict[str, Any]:
    """Collapse low-importance overflow into one negative_summary, so dropped units
    stay visible to the router as deprioritized rather than vanishing silently."""

    titles = sorted(
        {str(unit.get("title") or unit.get("summary_id") or "") for unit in dropped}
    )
    titles = [title for title in titles if title][:25]
    return {
        "summary_id": f"neg_{root_id}",
        "root_id": root_id,
        "scope_id": str(dropped[0].get("scope_id") or ""),
        "kind": "negative_summary",
        "modality": "mixed",
        "title": "Low-value content",
        "summary_text": "",
        "routing_meta": {"deprioritized": titles},
        "routing_payload": "Low-value or deprioritized content: " + " | ".join(titles),
        "source_refs_json": "[]",
        "source_high_watermark": "",
        "source_count": sum(int(unit.get("source_count") or 0) for unit in dropped),
        "coverage_estimate": 0.0,
        "importance": _NEGATIVE_ROLLUP_IMPORTANCE,
        "metadata_json": json.dumps({"rolled_up_count": len(dropped)}, sort_keys=True),
    }


def _select_budgeted_rows(
    rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Trim each root's representation units to its budget.

    Reserved L0 units (root_summary, album_summary) are always kept; remaining
    companions compete for the leftover budget by importance, then coverage, then
    id. Low-importance overflow is rolled up into a single negative_summary.
    Returns (selected, overflow) in a deterministic order so the FTS and the
    future semantic projection consume the identical unit set.
    """

    max_entries = int(_routing_defaults().get("max_entries", 20))
    by_root: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_root.setdefault(str(row.get("root_id") or ""), []).append(row)

    selected: list[dict[str, Any]] = []
    overflow: list[dict[str, Any]] = []
    for root_id, units in by_root.items():
        reserved = [u for u in units if str(u.get("kind")) in RESERVED_KINDS]
        companions = [u for u in units if str(u.get("kind")) not in RESERVED_KINDS]
        source_total = sum(int(u.get("source_count") or 0) for u in units)
        budget = _entry_budget(source_total, max_entries)
        remaining = max(0, budget - len(reserved))
        companions.sort(key=_precedence_key)
        dropped = companions[remaining:]
        selected.extend(reserved)
        selected.extend(companions[:remaining])
        overflow.extend(dropped)
        if dropped:
            selected.append(_negative_rollup(root_id, dropped))

    selected.sort(
        key=lambda r: (
            str(r.get("root_id") or ""),
            str(r.get("scope_id") or ""),
            str(r.get("summary_id") or ""),
        )
    )
    return selected, overflow


def _root_source_item_id(root_id: str) -> str | None:
    with catalog_connection() as conn:
        row = conn.execute(
            """
            SELECT source_item_id
            FROM "source_items"
            WHERE root_id = ?
              AND relative_path = '.'
              AND item_kind = 'folder'
            """,
            (root_id,),
        ).fetchone()
    return row["source_item_id"] if row else None


def _routing_payload(summary_text: str, meta: dict[str, Any]) -> str:
    """Assemble the flat searchable/embeddable payload from the model summary plus
    the deterministic facets. Both the FTS and the semantic projection use this so
    they index/embed the identical text (backend parity)."""

    lines: list[str] = []
    if meta.get("root"):
        lines.append(f"Root: {meta['root']}")
    if summary_text:
        lines.append(f"Summary: {summary_text}")
    for key in sorted(key for key in meta if key != "root"):
        value = meta[key]
        if isinstance(value, list):
            text = " | ".join(str(item) for item in value if str(item).strip())
        elif isinstance(value, dict):
            text = " | ".join(f"{name}={item}" for name, item in sorted(value.items()))
        else:
            text = str(value)
        if text.strip():
            label = key.replace("_", " ").capitalize()
            lines.append(f"{label}: {text}")
    return "\n".join(lines)


def _representation_policy_version() -> str:
    return str(_routing_defaults().get("representation_policy_version", "1"))


