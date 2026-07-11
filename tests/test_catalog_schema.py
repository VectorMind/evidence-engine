from __future__ import annotations

import sqlite3

import pytest

from even.catalog import CATALOG_SCHEMA_VERSION, CATALOG_USER_VERSION, create_catalog
from even.catalog import load_all_catalog_tables, load_catalog_tables
from even.paths import catalog_path


ENTITY_TABLES = {
    "entities",
    "entity_aliases",
    "entity_evidence_links",
    "entity_classifications",
    "entity_attributes",
    "entity_relationships",
    "review_tasks",
}


def test_catalog_contract_declares_entity_layer_tables() -> None:
    tables = {table.name: table for table in load_all_catalog_tables()}

    assert CATALOG_SCHEMA_VERSION == "0.10"
    assert ENTITY_TABLES <= set(tables)
    assert CATALOG_USER_VERSION == 10
    assert {column.name for column in tables["entities"].columns} >= {
        "entity_id",
        "entity_kind",
        "canonical_name",
        "review_status",
        "attrs_json",
    }
    assert {column.name for column in tables["entity_evidence_links"].columns} >= {
        "entity_id",
        "evidence_ref",
        "link_role",
        "link_status",
    }


def test_entity_layer_tables_live_only_in_corpus_state_dataset() -> None:
    cache_tables = {table.name for table in load_catalog_tables("corpus_cache")}
    state_tables = {table.name for table in load_catalog_tables("corpus_state")}

    assert ENTITY_TABLES <= state_tables
    assert cache_tables.isdisjoint(ENTITY_TABLES)
    assert state_tables.isdisjoint(cache_tables)


def test_load_catalog_tables_rejects_unknown_dataset() -> None:
    with pytest.raises(ValueError):
        load_catalog_tables("not_a_real_dataset")


def test_created_catalog_contains_entity_layer_tables() -> None:
    result = create_catalog()

    assert result["status"] == "created"
    assert ENTITY_TABLES <= set(result["expected_tables"])

    with sqlite3.connect(catalog_path()) as conn:
        actual_tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        user_version = conn.execute("PRAGMA user_version").fetchone()[0]

    assert ENTITY_TABLES <= actual_tables
    assert user_version == CATALOG_USER_VERSION
