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
from even.routing import (
    RoutingIndexOptions,
    _blend_tokens_per_sec,
    _entry_budget,
    _estimate_tokens,
    _importance_prior,
    _parse_importance,
    _select_budgeted_rows,
    _token_budget,
    index_routing,
)


def test_summary_nodes_catalog_contract(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)

    tables = {table.name for table in load_catalog_tables()}
    assert "summary_nodes" in tables
    assert CATALOG_USER_VERSION == 8

    assert create_catalog()["status"] == "created"
    with sqlite3.connect(catalog_path()) as conn:
        user_version = conn.execute("PRAGMA user_version").fetchone()[0]
        summary_table = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' "
            "AND name = 'summary_nodes'"
        ).fetchone()
        columns = {
            row[1]
            for row in conn.execute("PRAGMA table_info(summary_nodes)").fetchall()
        }

    assert user_version == 8
    assert summary_table == ("summary_nodes",)
    assert "importance" in columns


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


def test_index_routing_keeps_document_summary_inputs_document_only(
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
    assert "secret media caption" in prompts[1]


def test_index_routing_writes_media_album_summary_with_fake_generator(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    pytest.importorskip("tantivy")
    monkeypatch.chdir(tmp_path)
    data = _make_root(tmp_path, "media", "ignored text")
    (data / "lamp-photo.png").write_bytes(b"\x89PNG\r\n")
    scan = scan_folder_to_catalog(
        data,
        ScanOptions(max_files=None, max_bytes=None, max_depth=None),
    )
    _seed_media_caption(scan["root_id"], "lamp-photo.png", "lamp wiring diagram")

    result = index_routing(
        data,
        RoutingIndexOptions(force=True),
        summary_generator=_fake_summary,
    )

    assert result["status"] == "ok"
    assert result["counts"]["media_assets_considered"] == 1
    with sqlite3.connect(catalog_path()) as conn:
        row = conn.execute(
            """
            SELECT kind, modality, container_kind, summary_status, summary_text,
                   routing_text, source_refs_json
            FROM summary_nodes
            WHERE kind = 'album_summary'
            """
        ).fetchone()

    assert row[:4] == ("album_summary", "image", "root", "current")
    assert "generic" in row[4]
    assert "lamp wiring diagram" in row[5]
    assert json.loads(row[6])[0].startswith("corpus_cache.media_assets.")


def test_search_text_routes_to_media_summary_when_current(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    pytest.importorskip("tantivy")
    monkeypatch.chdir(tmp_path)
    data = _make_root(tmp_path, "media", "ignored text")
    filenames = ["lamp-a.png", "lamp-b.png", "lamp-c.png"]
    for filename in filenames:
        (data / filename).write_bytes(b"\x89PNG\r\n")
    scan = scan_folder_to_catalog(
        data,
        ScanOptions(max_files=None, max_bytes=None, max_depth=None),
    )
    for filename in filenames:
        _seed_media_caption(
            scan["root_id"],
            filename,
            f"{filename} zigbee lamp cluster commissioning",
        )

    assert index_scope_to_fts(data, IndexOptions(force=True))["status"] == "ok"
    assert (
        index_routing(
            data,
            RoutingIndexOptions(force=True),
            summary_generator=_fake_summary,
        )["status"]
        == "ok"
    )

    result = search_text_indexes("zigbee lamp cluster", SearchOptions(limit=10))

    assert result["status"] == "ok"
    assert result["route_trace"]["status"] == "used"
    assert all(hit["asset_id"] for hit in result["hits"])
    assert {hit["content_type"] for hit in result["hits"]} == {"media_caption"}


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


def test_parse_importance_extracts_and_strips_marker() -> None:
    cleaned, value = _parse_importance("alpha renewal contract root\nIMPORTANCE: 0.9")
    assert value == 0.9
    assert "IMPORTANCE" not in cleaned
    assert cleaned == "alpha renewal contract root"

    cleaned_none, value_none = _parse_importance("no marker here")
    assert value_none is None
    assert cleaned_none == "no marker here"

    _, clamped = _parse_importance("text\nimportance = 1.5")
    assert clamped == 1.0


def test_importance_prior_low_for_tooling_paths(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    assert _importance_prior("alpha") == 0.5
    assert _importance_prior("repo/node_modules/pkg") == 0.1
    assert _importance_prior("project/.venv") == 0.1


def test_index_routing_stores_model_importance(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    pytest.importorskip("tantivy")
    monkeypatch.chdir(tmp_path)
    data = _make_root(tmp_path, "alpha", "alpha contract renewal clause")
    _scan_and_seed_document(data, "report.txt", "alpha contract renewal clause")

    def importance_generator(prompt: str, **_: object) -> str:
        return "alpha renewal contract root\nIMPORTANCE: 0.9"

    result = index_routing(
        data,
        RoutingIndexOptions(force=True),
        summary_generator=importance_generator,
    )

    assert result["status"] == "ok"
    with sqlite3.connect(catalog_path()) as conn:
        row = conn.execute(
            "SELECT importance, summary_text FROM summary_nodes "
            "WHERE kind = 'root_summary'"
        ).fetchone()

    assert row[0] == 0.9
    assert "IMPORTANCE" not in row[1]


def test_index_routing_falls_back_to_importance_prior(
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
    with sqlite3.connect(catalog_path()) as conn:
        importance = conn.execute(
            "SELECT importance FROM summary_nodes WHERE kind = 'root_summary'"
        ).fetchone()[0]

    assert importance == 0.5


def test_entry_budget_is_log_scaled_and_capped() -> None:
    assert _entry_budget(1, 20) == 1
    assert _entry_budget(10, 20) == 3
    assert _entry_budget(100, 20) == 5
    assert _entry_budget(10_000, 20) == 9
    # Very large roots stay capped at max_entries.
    assert _entry_budget(10**12, 20) == 20
    assert _entry_budget(10**12, 5) == 5


def test_select_budgeted_rows_reserves_l0_and_ranks_companions() -> None:
    rows = [
        _unit("root", "root_summary", source_count=6, importance=0.4),
        _unit("album", "album_summary", source_count=1, importance=0.4),
        _unit("c_high", "folder_summary", source_count=1, importance=0.9),
        _unit("c_mid", "folder_summary", source_count=1, importance=0.5),
        _unit("c_low", "folder_summary", source_count=1, importance=0.1),
    ]

    selected, overflow = _select_budgeted_rows(rows)

    kept = {row["summary_id"] for row in selected if row["kind"] != "negative_summary"}
    overflow_ids = {row["summary_id"] for row in overflow}
    rollups = [row for row in selected if row["kind"] == "negative_summary"]
    # source_total=10 -> budget=3; root+album reserved, leaving 1 companion slot
    # for the highest-importance companion. The rest roll up into a negative_summary.
    assert kept == {"root", "album", "c_high"}
    assert overflow_ids == {"c_mid", "c_low"}
    assert len(rollups) == 1
    assert rollups[0]["summary_id"] == "neg_r"
    assert rollups[0]["importance"] == 0.05
    assert "c_mid" in rollups[0]["routing_text"]
    assert "c_low" in rollups[0]["routing_text"]


def test_index_routing_learns_low_importance_prior(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    pytest.importorskip("tantivy")
    monkeypatch.chdir(tmp_path)
    data = _make_root(tmp_path, "junkdir", "throwaway scratch notes")
    _scan_and_seed_document(data, "report.txt", "throwaway scratch notes")

    # An unseen folder name starts at the neutral prior.
    assert _importance_prior("junkdir") == 0.5

    def low_importance_generator(prompt: str, **_: object) -> str:
        return "scratch throwaway notes\nIMPORTANCE: 0.05"

    result = index_routing(
        data,
        RoutingIndexOptions(force=True),
        summary_generator=low_importance_generator,
    )

    assert result["status"] == "ok"
    # The model rated it clearly unimportant, so the dynamic prior list learned it.
    assert _importance_prior("junkdir") == 0.1


def test_tokens_per_sec_calibration_math() -> None:
    assert _estimate_tokens("a" * 40) == 10
    assert _estimate_tokens("") == 1
    # First sample seeds the value; later samples blend toward it.
    assert _blend_tokens_per_sec(None, 100.0) == 100.0
    assert _blend_tokens_per_sec(100.0, 200.0, alpha=0.5) == 150.0
    assert _token_budget(300, 50) == 15000
    assert _token_budget(0, 50) == 0


def test_index_routing_skips_media_when_build_budget_exhausted(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    pytest.importorskip("tantivy")
    monkeypatch.chdir(tmp_path)
    data = _make_root(tmp_path, "mixed", "document alpha text")
    (data / "photo.png").write_bytes(b"\x89PNG\r\n")
    scan = _scan_and_seed_document(data, "report.txt", "document alpha text")
    _seed_media_caption(scan["root_id"], "photo.png", "lamp wiring diagram")

    result = index_routing(
        data,
        RoutingIndexOptions(force=True, max_build_seconds=0.0),
        summary_generator=_fake_summary,
    )

    assert result["status"] == "ok"
    assert result["summaries"]["media"]["error_kind"] == "build_budget_exhausted"
    assert result["representation_budget"]["max_build_seconds"] == 0.0
    with sqlite3.connect(catalog_path()) as conn:
        album = conn.execute(
            "SELECT 1 FROM summary_nodes WHERE kind = 'album_summary'"
        ).fetchone()
        root = conn.execute(
            "SELECT summary_status FROM summary_nodes WHERE kind = 'root_summary'"
        ).fetchone()

    # The mandatory root_summary still ran; the media companion was skipped.
    assert root == ("current",)
    assert album is None


def _unit(summary_id: str, kind: str, *, source_count: int, importance: float) -> dict:
    return {
        "root_id": "r",
        "scope_id": "s",
        "summary_id": summary_id,
        "kind": kind,
        "source_count": source_count,
        "coverage_estimate": 0.5,
        "importance": importance,
    }


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
