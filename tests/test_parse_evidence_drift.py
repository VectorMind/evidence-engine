"""Milestone 0 trust-gap regression proof.

Proves the exact defect `plans/2026-07/10-engine-improvements/plan.md`
Milestone 0 requires: today, an accepted `entity_evidence_links` row stores a
current-state ref (`corpus_cache.document_objects.<object_id>`), and
`object_id` is derived only from `doc_id` (`even.parse._stable_id("obj",
doc_id, "paragraph", "0")`), never from content. Reparsing a changed source
deletes and re-inserts the `document_objects` row under the *same*
`object_id`, so an accepted link silently resolves to the new content. Wiping
the catalog deletes the single `catalog.sqlite` file outright, including
Layer-4 entity/review rows.

Both tests below are written as plain assertions of the desired (target)
behavior and are expected to fail against today's implementation for exactly
that reason. They are marked ``xfail(strict=True)`` so the suite stays green;
Milestones 1 and 2 of the linked plan packet must remove the marker when they
land the fix (occurrence pinning for the drift test, the
`state/state.sqlite` split for the wipe test). `strict=True` makes an
unexpected pass fail loudly, so the marker cannot be forgotten.

Only ``text_preview`` is asserted for content drift: `document_objects` has no
content-hash or locator columns yet (those arrive with Milestone 2's
`evidence_occurrences` table), so a hash/locator assertion is not possible
until that milestone.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from even.entities import (
    AddEntityOptions,
    AddLinkOptions,
    add_entity,
    add_link,
    review_target,
    show_entity,
)
from even.inventory import ScanOptions, scan_folder_to_catalog
from even.parse import _stable_id, _write_parsed_document
from even.paths import catalog_path
from even.references import evidence_ref, resolve_ref


def _scan_one_source_item(tmp_path: Path) -> str:
    data = tmp_path / "data"
    data.mkdir()
    (data / "report.txt").write_text("placeholder", encoding="utf-8")
    scan = scan_folder_to_catalog(data, ScanOptions(max_files=None, max_bytes=None, max_depth=None))
    assert scan["status"] == "ok"

    import sqlite3

    with sqlite3.connect(catalog_path()) as conn:
        row = conn.execute(
            "SELECT source_item_id FROM source_items WHERE item_kind = 'file'"
        ).fetchone()
    assert row is not None
    return row[0]


def _write_revision(source_item_id: str, *, source_sha256: str, text_preview: str) -> str:
    doc_id = _stable_id("doc", source_item_id)
    _write_parsed_document(
        source_item_id=source_item_id,
        doc_id=doc_id,
        source_sha256=source_sha256,
        parser_profile="docling_default",
        title="report",
        text_preview=text_preview,
        payload=text_preview.encode("utf-8"),
        now="2026-07-10T00:00:00Z",
    )
    return _stable_id("obj", doc_id, "paragraph", "0")


@pytest.mark.xfail(
    strict=True,
    reason=(
        "Milestone 0 trust-gap proof: entity links pin a mutable "
        "document_objects row today, so reparsing revision B overwrites the "
        "content an accepted link resolves to. Fixed by Milestone 1/2 "
        "occurrence pinning (OP-003); see plan.md."
    ),
)
def test_accepted_link_survives_reparse_to_changed_source(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    source_item_id = _scan_one_source_item(tmp_path)

    object_id = _write_revision(
        source_item_id, source_sha256="sha-revision-a", text_preview="revision A content"
    )
    ref = evidence_ref("document_objects", object_id)

    created = add_entity("Northwind Salvage", AddEntityOptions(kind="organization"))
    entity_id = created["entity_id"]
    link_result = add_link(entity_id, ref, AddLinkOptions())
    assert link_result["status"] == "ok"
    link_id = link_result["link_id"]

    review_result = review_target(link_id, "accept")
    assert review_result["status"] == "ok"

    reparsed_object_id = _write_revision(
        source_item_id, source_sha256="sha-revision-b", text_preview="revision B content"
    )
    assert reparsed_object_id == object_id  # object_id is content-independent today

    hydrated = resolve_ref(ref)
    assert hydrated is not None
    assert hydrated["text_preview"] == "revision A content", (
        "accepted link must keep resolving to the reviewed revision A content, "
        "not whatever the current reparse wrote"
    )

    shown = show_entity(entity_id)
    shown_link = next(link for link in shown["links"] if link["link_id"] == link_id)
    assert shown_link["evidence"]["text_preview"] == "revision A content"


@pytest.mark.xfail(
    strict=True,
    reason=(
        "Milestone 0 trust-gap proof: catalog wipe deletes the single "
        "catalog.sqlite file, including durable Layer-4 entity/review rows. "
        "Fixed by Milestone 1's state/state.sqlite split (OP-004); see plan.md."
    ),
)
def test_ordinary_wipe_preserves_accepted_link_and_evidence(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from even.catalog import wipe_catalog

    monkeypatch.chdir(tmp_path)
    source_item_id = _scan_one_source_item(tmp_path)
    object_id = _write_revision(
        source_item_id, source_sha256="sha-revision-a", text_preview="revision A content"
    )
    ref = evidence_ref("document_objects", object_id)

    created = add_entity("Northwind Salvage", AddEntityOptions(kind="organization"))
    entity_id = created["entity_id"]
    link_result = add_link(entity_id, ref, AddLinkOptions())
    link_id = link_result["link_id"]
    assert review_target(link_id, "accept")["status"] == "ok"

    wipe_catalog()

    shown = show_entity(entity_id)
    assert shown["status"] == "ok", "ordinary wipe must not delete durable entity/review rows"
    shown_link = next(link for link in shown["links"] if link["link_id"] == link_id)
    assert shown_link["link_status"] == "accepted"
    assert shown_link["evidence"] is not None, (
        "accepted evidence must still hydrate after ordinary catalog wipe"
    )
