from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from even.catalog import CATALOG_USER_VERSION, create_catalog, load_catalog_tables
from even.cli import build_parser
from even.fts import IndexOptions, SearchOptions, index_scope_to_fts, search_text_indexes
from even.inventory import ScanOptions, scan_folder_to_catalog
from even.paths import catalog_path
from even.routing import RoutingIndexOptions, index_routing


def test_summary_nodes_catalog_contract(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)

    tables = {table.name for table in load_catalog_tables()}
    assert "summary_nodes" in tables
    assert CATALOG_USER_VERSION == 7

    assert create_catalog()["status"] == "created"
    with sqlite3.connect(catalog_path()) as conn:
        user_version = conn.execute("PRAGMA user_version").fetchone()[0]
        summary_table = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' "
            "AND name = 'summary_nodes'"
        ).fetchone()

    assert user_version == 7
    assert summary_table == ("summary_nodes",)


def test_parser_exposes_index_routing() -> None:
    parser = build_parser()

    args = parser.parse_args(["index", "routing", "C:/example"])

    assert args.handler.__name__ == "index_routing_command"


def test_index_routing_writes_document_summary_with_fake_generator(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    pytest.importorskip("tantivy")
    monkeypatch.chdir(tmp_path)
    data = _make_root(tmp_path, "alpha", "alpha contract renewal clause")
    _scan_and_seed_document(data, "report.txt", "alpha contract renewal clause")

    result = index_routing(
        data,
        RoutingIndexOptions(force=True),
        summary_generator=_fake_summary,
    )

    assert result["status"] == "ok"
    assert result["counts"]["chunks_considered"] == 1
    with sqlite3.connect(catalog_path()) as conn:
        row = conn.execute(
            """
            SELECT kind, modality, container_kind, summary_status, summary_text,
                   routing_text, source_refs_json
            FROM summary_nodes
            """
        ).fetchone()

    assert row[:4] == ("root_summary", "text", "root", "current")
    assert "alpha" in row[4]
    assert "alpha" in row[5]
    assert json.loads(row[6])[0].startswith("corpus_cache.document_objects.")


def test_index_routing_excludes_media_chunks_from_d0_summary(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    pytest.importorskip("tantivy")
    monkeypatch.chdir(tmp_path)
    data = _make_root(tmp_path, "mixed", "document alpha text")
    (data / "photo.png").write_bytes(b"\x89PNG\r\n")
    scan = _scan_and_seed_document(data, "report.txt", "document alpha text")
    _seed_media_caption(scan["root_id"], "photo.png", "secret media caption")
    prompts: list[str] = []

    def capture_prompt(prompt: str, **_: object) -> str:
        prompts.append(prompt)
        return "document alpha summary"

    result = index_routing(
        data,
        RoutingIndexOptions(force=True),
        summary_generator=capture_prompt,
    )

    assert result["status"] == "ok"
    assert prompts
    assert "document alpha text" in prompts[0]
    assert "secret media caption" not in prompts[0]


def test_search_text_uses_global_routing_when_current(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    pytest.importorskip("tantivy")
    monkeypatch.chdir(tmp_path)
    alpha = _make_root(tmp_path, "alpha", "alpha contract")
    beta = _make_root(tmp_path, "beta", "beta invoice")
    (alpha / "alpha.txt").write_text("alpha renewal contract", encoding="utf-8")
    (beta / "beta.txt").write_text("beta invoice receipt", encoding="utf-8")
    _scan_and_seed_document(alpha, "alpha.txt", "alpha renewal contract", repeat=3)
    _scan_and_seed_document(beta, "beta.txt", "beta invoice receipt", repeat=3)

    assert index_scope_to_fts(alpha, IndexOptions(force=True))["status"] == "ok"
    assert index_scope_to_fts(beta, IndexOptions(force=True))["status"] == "ok"
    assert (
        index_routing(
            alpha,
            RoutingIndexOptions(force=True),
            summary_generator=_fake_summary,
        )["status"]
        == "ok"
    )
    assert (
        index_routing(
            beta,
            RoutingIndexOptions(force=True),
            summary_generator=_fake_summary,
        )["status"]
        == "ok"
    )

    result = search_text_indexes("alpha renewal", SearchOptions(limit=10))

    assert result["status"] == "ok"
    assert result["route_trace"]["status"] == "used"
    selected = result["route_trace"]["selected_scopes"]
    assert len(selected) == 1
    assert all("alpha" in hit["relative_path"] for hit in result["hits"])


def _make_root(tmp_path: Path, name: str, text: str) -> Path:
    root = tmp_path / name
    root.mkdir()
    (root / "report.txt").write_text(text, encoding="utf-8")
    return root


def _scan_and_seed_document(
    root: Path,
    relative_path: str,
    text: str,
    *,
    repeat: int = 1,
) -> dict[str, object]:
    scan = scan_folder_to_catalog(
        root,
        ScanOptions(max_files=None, max_bytes=None, max_depth=None),
    )
    with sqlite3.connect(catalog_path()) as conn:
        source_item = conn.execute(
            """
            SELECT source_item_id, source_sha256
            FROM source_items
            WHERE root_id = ?
              AND relative_path = ?
            """,
            (scan["root_id"], relative_path),
        ).fetchone()
        assert source_item is not None
        doc_id = f"doc_{source_item[0]}"
        conn.execute(
            """
            INSERT OR REPLACE INTO documents
            (doc_id, source_item_id, source_sha256, parser_profile, parse_status,
             parsed_at, title, language, object_count, valuable_item_count)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                doc_id,
                source_item[0],
                source_item[1],
                "test_profile",
                "parsed",
                "2026-06-14T00:00:00Z",
                Path(relative_path).stem,
                "en",
                repeat,
                0,
            ),
        )
        for index in range(repeat):
            object_id = f"obj_{source_item[0]}_{index}"
            conn.execute(
                """
                INSERT OR REPLACE INTO document_objects
                (object_id, doc_id, parent_object_id, object_type, order_index,
                 page_start, page_end, heading_path, text_preview, attrs_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    object_id,
                    doc_id,
                    None,
                    "paragraph",
                    index,
                    index + 1,
                    index + 1,
                    "[]",
                    f"{text} section {index}",
                    "{}",
                ),
            )
        conn.commit()
    return scan


def _seed_media_caption(root_id: str, relative_path: str, caption: str) -> None:
    with sqlite3.connect(catalog_path()) as conn:
        source_item = conn.execute(
            """
            SELECT source_item_id
            FROM source_items
            WHERE root_id = ?
              AND relative_path = ?
            """,
            (root_id, relative_path),
        ).fetchone()
        assert source_item is not None
        asset_id = f"asset_{source_item[0]}"
        conn.execute(
            """
            INSERT OR REPLACE INTO media_assets
            (asset_id, source_item_id, media_class, primary_artifact_id,
             inspect_status, attrs_json, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                asset_id,
                source_item[0],
                "image",
                None,
                "current",
                "{}",
                "2026-06-14T00:00:00Z",
            ),
        )
        conn.execute(
            """
            INSERT OR REPLACE INTO media_observations
            (observation_id, asset_id, observation_kind, value_text, confidence,
             producer, profile, attrs_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                f"obs_{asset_id}",
                asset_id,
                "caption",
                caption,
                None,
                "test",
                "test",
                "{}",
                "2026-06-14T00:00:00Z",
            ),
        )
        conn.commit()


def _fake_summary(prompt: str, **_: object) -> str:
    if "alpha" in prompt:
        return "alpha renewal contract root"
    if "beta" in prompt:
        return "beta invoice receipt root"
    return "generic document root"
