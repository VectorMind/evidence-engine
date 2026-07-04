"""Generic Layer-4 entity runtime.

CRUD and review helpers over the catalog tables from ``catalog.yaml``:
``entities``, ``entity_aliases``, ``entity_evidence_links``, and
``review_tasks``. Every write goes through this module; the CLI layer never
runs ad hoc SQL. Links store ``ref: corpus_cache.<table>.<row_id>`` strings
only, per the Reference Contract in
``specifications/corpus-cache-cli/spec.md`` -- never a copy of the referenced
row. Producers are humans and the search-assisted ``find_entity_evidence``
bridge; model-driven proposal pipelines are out of scope here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
from typing import Any
import uuid

from even.catalog import ensure_catalog
from even.db import catalog_connection
from even.references import attach_hit_refs, resolve_ref

ENTITY_KINDS = (
    "person",
    "organization",
    "place",
    "event",
    "object",
    "document",
    "account",
    "concept",
    "collection",
    "unknown",
    "other",
)
ENTITY_STATUSES = ("proposed", "active", "merged", "rejected", "archived")
REVIEW_STATUSES = ("unreviewed", "accepted", "rejected", "deferred")
ALIAS_KINDS = ("name", "label", "identifier", "handle", "filename_hint", "abbreviation", "other")
LINK_ROLES = (
    "mention",
    "identifier",
    "visual_match",
    "location",
    "source",
    "support",
    "contradiction",
    "context",
    "other",
)
LINK_STATUSES = ("proposed", "accepted", "rejected", "deferred")

_REVIEW_DECISIONS = {"accept": "accepted", "reject": "rejected", "defer": "deferred"}

# Maps a target id's prefix to the table/primary-key/status column that
# `review_target` updates. Only covers rows this module writes.
_REVIEW_TARGETS: dict[str, tuple[str, str, str]] = {
    "ent": ("entities", "entity_id", "review_status"),
    "alias": ("entity_aliases", "alias_id", "review_status"),
    "link": ("entity_evidence_links", "link_id", "link_status"),
    "task": ("review_tasks", "task_id", "task_status"),
}
# Only these tables carry an `updated_at` column to refresh on review.
_TABLES_WITH_UPDATED_AT = {"entities", "review_tasks"}


@dataclass(frozen=True)
class AddEntityOptions:
    kind: str
    description: str | None = None
    status: str = "proposed"
    producer: str = "human"


@dataclass(frozen=True)
class ListEntitiesOptions:
    kind: str | None = None
    status: str | None = None
    review_status: str | None = None
    limit: int = 100


@dataclass(frozen=True)
class AddAliasOptions:
    kind: str = "name"
    language: str | None = None
    evidence_ref: str | None = None


@dataclass(frozen=True)
class AddLinkOptions:
    role: str = "mention"
    status: str = "proposed"
    confidence: float | None = None
    producer: str = "human"


@dataclass(frozen=True)
class FindEntityEvidenceOptions:
    limit: int = 30
    budget: str = "mid"
    image_paths: tuple[str, ...] = field(default_factory=tuple)
    propose: bool = False
    role: str = "mention"


def add_entity(name: str, options: AddEntityOptions) -> dict[str, Any]:
    """Create a new entity row. Always inserts a new row; never dedupes."""

    if options.kind not in ENTITY_KINDS:
        return _invalid("entity_kind", options.kind, ENTITY_KINDS)
    if options.status not in ENTITY_STATUSES:
        return _invalid("entity_status", options.status, ENTITY_STATUSES)

    catalog_state = ensure_catalog()
    if catalog_state["status"] not in {"created", "current"}:
        return _catalog_not_ready(catalog_state)

    now = _iso(_utc_now())
    entity_id = _new_id("ent")
    with catalog_connection() as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute(
            """
            INSERT INTO "entities"
            (entity_id, entity_kind, canonical_name, description, entity_status,
             review_status, confidence, producer, created_at, updated_at, attrs_json)
            VALUES (?, ?, ?, ?, ?, 'unreviewed', NULL, ?, ?, ?, NULL)
            """,
            (
                entity_id,
                options.kind,
                name,
                options.description,
                options.status,
                options.producer,
                now,
                now,
            ),
        )
    return {"status": "ok", "entity_id": entity_id, "entity": _fetch_entity(entity_id)}


def list_entities(options: ListEntitiesOptions) -> dict[str, Any]:
    """List entities, optionally filtered by kind, lifecycle, or review state."""

    catalog_state = ensure_catalog()
    if catalog_state["status"] not in {"created", "current"}:
        return _catalog_not_ready(catalog_state)

    clauses = []
    params: list[Any] = []
    if options.kind is not None:
        clauses.append("entity_kind = ?")
        params.append(options.kind)
    if options.status is not None:
        clauses.append("entity_status = ?")
        params.append(options.status)
    if options.review_status is not None:
        clauses.append("review_status = ?")
        params.append(options.review_status)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    limit = max(1, int(options.limit or 100))
    sql = f'SELECT * FROM "entities" {where} ORDER BY created_at DESC LIMIT ?'
    params.append(limit)

    with catalog_connection(read_only=True) as conn:
        rows = conn.execute(sql, params).fetchall()
    entities = [dict(row) for row in rows]
    return {
        "status": "ok",
        "entities": entities,
        "counts": {"entities_returned": len(entities)},
    }


def show_entity(entity_id: str) -> dict[str, Any]:
    """Return one entity hydrated with its aliases, links, relationships, and tasks.

    Linked/aliased evidence references are resolved by reading the referenced
    row, per the Reference Contract -- never a stored copy.
    """

    catalog_state = ensure_catalog()
    if catalog_state["status"] not in {"created", "current"}:
        return _catalog_not_ready(catalog_state)

    entity = _fetch_entity(entity_id)
    if entity is None:
        return {"status": "not_found", "error_kind": "entity_not_found", "entity_id": entity_id}

    with catalog_connection(read_only=True) as conn:
        aliases = [
            dict(row)
            for row in conn.execute(
                'SELECT * FROM "entity_aliases" WHERE entity_id = ? ORDER BY alias_id',
                (entity_id,),
            ).fetchall()
        ]
        links = [
            dict(row)
            for row in conn.execute(
                'SELECT * FROM "entity_evidence_links" WHERE entity_id = ? ORDER BY created_at',
                (entity_id,),
            ).fetchall()
        ]
        classifications = [
            dict(row)
            for row in conn.execute(
                'SELECT * FROM "entity_classifications" WHERE entity_id = ? ORDER BY classification_id',
                (entity_id,),
            ).fetchall()
        ]
        attributes = [
            dict(row)
            for row in conn.execute(
                'SELECT * FROM "entity_attributes" WHERE entity_id = ? ORDER BY attribute_id',
                (entity_id,),
            ).fetchall()
        ]
        relationships = [
            dict(row)
            for row in conn.execute(
                """
                SELECT * FROM "entity_relationships"
                WHERE subject_entity_id = ? OR object_entity_id = ?
                ORDER BY relationship_id
                """,
                (entity_id, entity_id),
            ).fetchall()
        ]
        tasks = [
            dict(row)
            for row in conn.execute(
                'SELECT * FROM "review_tasks" WHERE entity_id = ? ORDER BY created_at',
                (entity_id,),
            ).fetchall()
        ]

    for link in links:
        link["evidence"] = resolve_ref(link["evidence_ref"]) if link.get("evidence_ref") else None
    for alias in aliases:
        alias["evidence"] = resolve_ref(alias["evidence_ref"]) if alias.get("evidence_ref") else None

    return {
        "status": "ok",
        "entity": entity,
        "aliases": aliases,
        "links": links,
        "classifications": classifications,
        "attributes": attributes,
        "relationships": relationships,
        "review_tasks": tasks,
    }


def add_alias(entity_id: str, alias_text: str, options: AddAliasOptions) -> dict[str, Any]:
    """Add an alternate name/label/identifier to an existing entity."""

    if options.kind not in ALIAS_KINDS:
        return _invalid("alias_kind", options.kind, ALIAS_KINDS)

    catalog_state = ensure_catalog()
    if catalog_state["status"] not in {"created", "current"}:
        return _catalog_not_ready(catalog_state)

    if _fetch_entity(entity_id) is None:
        return {"status": "not_found", "error_kind": "entity_not_found", "entity_id": entity_id}

    alias_id = _new_id("alias")
    with catalog_connection() as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute(
            """
            INSERT INTO "entity_aliases"
            (alias_id, entity_id, alias_text, normalized_alias, alias_kind,
             language, review_status, evidence_ref, attrs_json)
            VALUES (?, ?, ?, ?, ?, ?, 'unreviewed', ?, NULL)
            """,
            (
                alias_id,
                entity_id,
                alias_text,
                alias_text.strip().lower(),
                options.kind,
                options.language,
                options.evidence_ref,
            ),
        )
    return {"status": "ok", "alias_id": alias_id}


def add_link(entity_id: str, ref: str, options: AddLinkOptions) -> dict[str, Any]:
    """Bind an entity to an evidence row by its ``corpus_cache.<table>.<row_id>`` ref.

    The ref must resolve to a current catalog row; this module never links to
    a dangling reference. No evidence is copied -- only the ref string is
    stored.
    """

    if options.role not in LINK_ROLES:
        return _invalid("link_role", options.role, LINK_ROLES)
    if options.status not in LINK_STATUSES:
        return _invalid("link_status", options.status, LINK_STATUSES)

    catalog_state = ensure_catalog()
    if catalog_state["status"] not in {"created", "current"}:
        return _catalog_not_ready(catalog_state)

    if _fetch_entity(entity_id) is None:
        return {"status": "not_found", "error_kind": "entity_not_found", "entity_id": entity_id}

    if resolve_ref(ref) is None:
        return {
            "status": "failed",
            "error_kind": "evidence_ref_not_found",
            "evidence_ref": ref,
            "message": "The referenced evidence row could not be resolved.",
        }

    now = _iso(_utc_now())
    link_id = _new_id("link")
    with catalog_connection() as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute(
            """
            INSERT INTO "entity_evidence_links"
            (link_id, entity_id, evidence_ref, link_role, link_status,
             confidence, producer, created_at, attrs_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL)
            """,
            (
                link_id,
                entity_id,
                ref,
                options.role,
                options.status,
                options.confidence,
                options.producer,
                now,
            ),
        )
    return {"status": "ok", "link_id": link_id}


def review_target(target_id: str, decision: str) -> dict[str, Any]:
    """Record accept/reject/defer on an entity, alias, link, or review task.

    Never mutates the Layer-2/3 evidence a link or task points at -- only the
    review-state column on the Layer-4 row itself.
    """

    if decision not in _REVIEW_DECISIONS:
        return _invalid("decision", decision, tuple(_REVIEW_DECISIONS))

    prefix = target_id.split("_", 1)[0]
    target = _REVIEW_TARGETS.get(prefix)
    if target is None:
        return {"status": "failed", "error_kind": "unknown_target_kind", "target_id": target_id}
    table, pk_column, status_column = target

    catalog_state = ensure_catalog()
    if catalog_state["status"] not in {"created", "current"}:
        return _catalog_not_ready(catalog_state)

    new_status = _REVIEW_DECISIONS[decision]
    now = _iso(_utc_now())
    with catalog_connection() as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        if table in _TABLES_WITH_UPDATED_AT:
            cursor = conn.execute(
                f'UPDATE "{table}" SET "{status_column}" = ?, updated_at = ? WHERE "{pk_column}" = ?',
                (new_status, now, target_id),
            )
        else:
            cursor = conn.execute(
                f'UPDATE "{table}" SET "{status_column}" = ? WHERE "{pk_column}" = ?',
                (new_status, target_id),
            )
        updated = cursor.rowcount

    if not updated:
        return {"status": "not_found", "error_kind": "target_not_found", "target_id": target_id}
    return {"status": "ok", "target_id": target_id, status_column: new_status}


def find_entity_evidence(
    entity_id: str, query: str, options: FindEntityEvidenceOptions
) -> dict[str, Any]:
    """Discover candidate evidence for an entity through the public search surface.

    Wraps `search text` (with its optional SigLIP cross-modal probe when
    `image_paths` is set) and attaches the canonical `ref` to every hit, so a
    hit can be bound with `add_link` in one follow-up call. With
    `options.propose`, ref-bearing hits are immediately written as `proposed`
    links plus open `review_tasks`, ready for `review_target`.
    """

    catalog_state = ensure_catalog()
    if catalog_state["status"] not in {"created", "current"}:
        return _catalog_not_ready(catalog_state)

    if _fetch_entity(entity_id) is None:
        return {"status": "not_found", "error_kind": "entity_not_found", "entity_id": entity_id}

    from even.fts import SearchOptions, search_text_indexes

    result = search_text_indexes(
        query,
        SearchOptions(limit=options.limit, budget=options.budget, image_paths=options.image_paths),
    )
    attach_hit_refs(result)

    proposed_links: list[dict[str, Any]] = []
    if options.propose:
        now = _iso(_utc_now())
        with catalog_connection() as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            for hit in result.get("hits", []):
                ref = hit.get("ref")
                if not ref:
                    continue
                link_id = _new_id("link")
                attrs = json.dumps(
                    {
                        "query": query,
                        "relative_path": hit.get("relative_path"),
                        "root_label": hit.get("root_label"),
                        "score": hit.get("score"),
                    }
                )
                conn.execute(
                    """
                    INSERT INTO "entity_evidence_links"
                    (link_id, entity_id, evidence_ref, link_role, link_status,
                     confidence, producer, created_at, attrs_json)
                    VALUES (?, ?, ?, ?, 'proposed', ?, ?, ?, ?)
                    """,
                    (link_id, entity_id, ref, options.role, hit.get("score"), "search:entity_find", now, attrs),
                )
                task_id = _new_id("task")
                conn.execute(
                    """
                    INSERT INTO "review_tasks"
                    (task_id, task_kind, entity_id, evidence_ref, task_status,
                     priority, producer, created_at, updated_at, attrs_json)
                    VALUES (?, 'entity_link', ?, ?, 'open', 0, ?, ?, ?, NULL)
                    """,
                    (task_id, entity_id, ref, "search:entity_find", now, now),
                )
                hit["proposed_link_id"] = link_id
                hit["proposed_task_id"] = task_id
                proposed_links.append({"link_id": link_id, "task_id": task_id, "evidence_ref": ref})

    # Pass the full search payload through (route_trace, failures, skipped, ...)
    # rather than reconstructing a subset, so search diagnostics stay visible.
    payload = dict(result)
    payload["entity_id"] = entity_id
    payload["query"] = query
    payload["proposed_links"] = proposed_links
    return payload


def _invalid(field_name: str, value: Any, allowed: tuple[str, ...]) -> dict[str, Any]:
    return {
        "status": "failed",
        "error_kind": f"invalid_{field_name}",
        field_name: value,
        "allowed": list(allowed),
    }


def _catalog_not_ready(catalog_state: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "failed",
        "error_kind": "catalog_not_ready",
        "catalog_status": catalog_state["status"],
    }


def _fetch_entity(entity_id: str) -> dict[str, Any] | None:
    with catalog_connection(read_only=True) as conn:
        row = conn.execute('SELECT * FROM "entities" WHERE entity_id = ?', (entity_id,)).fetchone()
    return dict(row) if row is not None else None


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")
