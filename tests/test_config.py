"""Config/catalog loaders read the packaged YAML contracts directly.

Guards the Phase 2 removal of the stdlib-only fallback parsers: PyYAML is now a
hard base dependency, so the loaders must parse the real YAML on every install.
"""

from __future__ import annotations

from even.catalog import load_catalog_tables
from even.config import (
    embedding_profile,
    load_embedding_config,
    load_parser_config,
    load_routing_config,
)


def test_parser_config_has_defaults() -> None:
    defaults = load_parser_config()["defaults"]
    assert defaults["parser_profile"]
    assert "fts_profile" in defaults


def test_embedding_profiles_resolve_by_name() -> None:
    names = [profile["name"] for profile in load_embedding_config()["profiles"]]
    assert "fastembed_bge_small_en_v1_5" in names

    profile = embedding_profile("fastembed_bge_small_en_v1_5")
    assert profile is not None
    assert profile["dimension"] == 384
    assert embedding_profile("does-not-exist") is None


def test_routing_defaults_present() -> None:
    defaults = load_routing_config()["defaults"]
    assert int(defaults["representative_top_k"]) >= 1
    assert int(defaults["max_routed_scopes"]) >= 1


def test_catalog_tables_load_with_columns() -> None:
    tables = load_catalog_tables()
    assert tables
    assert all(table.name for table in tables)
    assert any(table.columns for table in tables)
