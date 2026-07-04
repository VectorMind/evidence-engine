from __future__ import annotations

from pathlib import Path

import pytest

from even.entities import (
    AddAliasOptions,
    AddEntityOptions,
    AddLinkOptions,
    FindEntityEvidenceOptions,
    ListEntitiesOptions,
    add_alias,
    add_entity,
    add_link,
    find_entity_evidence,
    list_entities,
    review_target,
    show_entity,
)
from even.inventory import ScanOptions, scan_folder_to_catalog
from even.references import evidence_ref, resolve_ref


def test_add_entity_creates_row_and_defaults_to_unreviewed() -> None:
    result = add_entity("Northwind Salvage", AddEntityOptions(kind="organization"))

    assert result["status"] == "ok"
    assert result["entity"]["canonical_name"] == "Northwind Salvage"
    assert result["entity"]["entity_kind"] == "organization"
    assert result["entity"]["entity_status"] == "proposed"
    assert result["entity"]["review_status"] == "unreviewed"


def test_add_entity_rejects_unknown_kind() -> None:
    result = add_entity("Bad Kind", AddEntityOptions(kind="not_a_kind"))

    assert result["status"] == "failed"
    assert result["error_kind"] == "invalid_entity_kind"


def test_list_entities_filters_by_kind_and_status() -> None:
    add_entity("Org One", AddEntityOptions(kind="organization"))
    add_entity("Person One", AddEntityOptions(kind="person"))

    result = list_entities(ListEntitiesOptions(kind="organization"))

    assert result["status"] == "ok"
    assert result["counts"]["entities_returned"] == 1
    assert result["entities"][0]["canonical_name"] == "Org One"


def test_add_alias_requires_existing_entity() -> None:
    result = add_alias("ent_missing", "Alias", AddAliasOptions())

    assert result["status"] == "not_found"
    assert result["error_kind"] == "entity_not_found"


def test_add_alias_normalizes_lookup_text() -> None:
    created = add_entity("Northwind Salvage", AddEntityOptions(kind="organization"))
    entity_id = created["entity_id"]

    result = add_alias(entity_id, "  N.W. Salvage  ", AddAliasOptions(kind="abbreviation"))

    assert result["status"] == "ok"
    shown = show_entity(entity_id)
    alias = shown["aliases"][0]
    assert alias["alias_text"] == "  N.W. Salvage  "
    assert alias["normalized_alias"] == "n.w. salvage"


def test_add_link_rejects_unresolvable_ref() -> None:
    created = add_entity("Northwind Salvage", AddEntityOptions(kind="organization"))
    entity_id = created["entity_id"]

    result = add_link(entity_id, "corpus_cache.document_objects.does-not-exist", AddLinkOptions())

    assert result["status"] == "failed"
    assert result["error_kind"] == "evidence_ref_not_found"


def test_add_link_accepts_ref_to_real_media_asset(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    pil = pytest.importorskip("PIL.Image")
    monkeypatch.chdir(tmp_path)
    data = tmp_path / "data"
    data.mkdir()
    pil.new("RGB", (16, 16), color=(10, 20, 30)).save(data / "photo.png")
    scan = scan_folder_to_catalog(data, ScanOptions(max_files=None, max_bytes=None, max_depth=None))
    assert scan["status"] == "ok"

    from even.media import InspectOptions, inspect_folder_to_catalog

    inspect_result = inspect_folder_to_catalog(data, InspectOptions())
    assert inspect_result["status"] == "ok"

    import sqlite3

    from even.paths import catalog_path

    with sqlite3.connect(catalog_path()) as conn:
        asset_id = conn.execute("SELECT asset_id FROM media_assets").fetchone()[0]

    ref = evidence_ref("media_assets", asset_id)
    assert resolve_ref(ref) is not None

    created = add_entity("Northwind Salvage", AddEntityOptions(kind="organization"))
    entity_id = created["entity_id"]

    result = add_link(entity_id, ref, AddLinkOptions(role="visual_match"))

    assert result["status"] == "ok"
    shown = show_entity(entity_id)
    assert len(shown["links"]) == 1
    link = shown["links"][0]
    assert link["evidence_ref"] == ref
    assert link["link_role"] == "visual_match"
    assert link["evidence"]["asset_id"] == asset_id


def test_review_target_updates_entity_review_status() -> None:
    created = add_entity("Northwind Salvage", AddEntityOptions(kind="organization"))
    entity_id = created["entity_id"]

    result = review_target(entity_id, "accept")

    assert result["status"] == "ok"
    assert result["review_status"] == "accepted"
    shown = show_entity(entity_id)
    assert shown["entity"]["review_status"] == "accepted"


def test_review_target_updates_link_status_without_touching_evidence(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    pil = pytest.importorskip("PIL.Image")
    monkeypatch.chdir(tmp_path)
    data = tmp_path / "data"
    data.mkdir()
    pil.new("RGB", (16, 16), color=(10, 20, 30)).save(data / "photo.png")
    scan_folder_to_catalog(data, ScanOptions(max_files=None, max_bytes=None, max_depth=None))

    from even.media import InspectOptions, inspect_folder_to_catalog

    inspect_folder_to_catalog(data, InspectOptions())

    import sqlite3

    from even.paths import catalog_path

    with sqlite3.connect(catalog_path()) as conn:
        asset_id = conn.execute("SELECT asset_id FROM media_assets").fetchone()[0]
    ref = evidence_ref("media_assets", asset_id)

    created = add_entity("Northwind Salvage", AddEntityOptions(kind="organization"))
    entity_id = created["entity_id"]
    link_result = add_link(entity_id, ref, AddLinkOptions())
    link_id = link_result["link_id"]

    before = resolve_ref(ref)
    result = review_target(link_id, "reject")
    after = resolve_ref(ref)

    assert result["status"] == "ok"
    assert result["link_status"] == "rejected"
    assert before == after  # reviewing the link never mutates the evidence row


def test_review_target_reports_unknown_target_kind() -> None:
    result = review_target("bogus_123", "accept")

    assert result["status"] == "failed"
    assert result["error_kind"] == "unknown_target_kind"


def test_review_target_reports_missing_target() -> None:
    result = review_target("ent_doesnotexist", "accept")

    assert result["status"] == "not_found"
    assert result["error_kind"] == "target_not_found"


def test_find_entity_evidence_requires_existing_entity() -> None:
    result = find_entity_evidence("ent_missing", "salvage", FindEntityEvidenceOptions())

    assert result["status"] == "not_found"
    assert result["error_kind"] == "entity_not_found"


def test_resolve_ref_returns_none_for_malformed_or_unknown_table() -> None:
    assert resolve_ref("not-a-ref") is None
    assert resolve_ref("corpus_cache.not_a_table.row1") is None
    assert resolve_ref("other_dataset.entities.row1") is None
