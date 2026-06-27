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
    _fuse_representative_hits,
    _importance_prior,
    _kmeans_medoids,
    _parse_importance,
    _search_global_representatives_siglip,
    _select_budgeted_rows,
    _token_budget,
    build_global_representative_siglip,
    index_routing,
    list_representatives,
)


def test_summary_nodes_catalog_contract(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)

    tables = {table.name for table in load_catalog_tables()}
    assert "summary_nodes" in tables
    assert CATALOG_USER_VERSION == 9

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

    assert user_version == 9
    assert summary_table == ("summary_nodes",)
    assert "importance" in columns
    assert "routing_meta" in columns
    assert "routing_text" not in columns


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
                   routing_meta, source_refs_json
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
                   routing_meta, source_refs_json
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
    assert "c_mid" in rollups[0]["routing_payload"]
    assert "c_low" in rollups[0]["routing_payload"]


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


def test_parser_exposes_list_and_search_budget() -> None:
    parser = build_parser()

    list_args = parser.parse_args(["list"])
    assert list_args.handler.__name__ == "list_representatives_command"

    budget_args = parser.parse_args(["search", "text", "alpha", "--budget", "high"])
    assert budget_args.budget == "high"


def test_list_representatives_lists_current_nodes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    pytest.importorskip("tantivy")
    monkeypatch.chdir(tmp_path)
    data = _make_root(tmp_path, "alpha", "alpha contract renewal clause")
    _scan_and_seed_document(data, "report.txt", "alpha contract renewal clause")
    index_routing(data, RoutingIndexOptions(force=True), summary_generator=_fake_summary)

    result = list_representatives()

    assert result["status"] == "ok"
    assert result["counts"]["roots"] == 1
    kinds = {node["kind"] for root in result["roots"] for node in root["nodes"]}
    assert "root_summary" in kinds


def test_search_text_low_budget_limits_fanout(
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
    index_routing(alpha, RoutingIndexOptions(force=True), summary_generator=_fake_summary)
    index_routing(beta, RoutingIndexOptions(force=True), summary_generator=_fake_summary)

    result = search_text_indexes("alpha renewal", SearchOptions(limit=10, budget="low"))

    assert result["route_trace"]["budget"] == "low"
    assert len(result["route_trace"].get("selected_scopes", [])) <= 1


def test_fuse_representative_hits_ranks_shared_unit_first() -> None:
    fused = _fuse_representative_hits(
        [
            ("global_representative_fts", [
                {"summary_id": "a", "scope_id": "sa", "rank": 1},
                {"summary_id": "b", "scope_id": "sb", "rank": 2},
            ]),
            ("global_representative_semantic", [
                {"summary_id": "b", "scope_id": "sb", "rank": 1},
                {"summary_id": "c", "scope_id": "sc", "rank": 2},
            ]),
        ]
    )

    # `b` is hit by both routes, so RRF ranks it first.
    assert fused[0]["summary_id"] == "b"
    assert fused[0]["contributing_modes"] == [
        "global_representative_fts",
        "global_representative_semantic",
    ]
    assert fused[0]["rank"] == 1


_FAKE_VOCAB = ("alpha", "beta", "renewal", "contract", "invoice", "receipt")


def _fake_vector(text: str) -> list[float]:
    lowered = str(text).lower()
    raw = [1.0 if word in lowered else 0.0 for word in _FAKE_VOCAB]
    norm = sum(value * value for value in raw) ** 0.5 or 1.0
    return [value / norm for value in raw]


def test_semantic_representative_route_fuses_with_fts(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    pytest.importorskip("tantivy")
    pytest.importorskip("lancedb")
    monkeypatch.chdir(tmp_path)
    from even import semantic

    monkeypatch.setattr(
        semantic, "_embed_passages", lambda profile, texts: [_fake_vector(t) for t in texts]
    )
    monkeypatch.setattr(semantic, "_embed_query", lambda profile, text: _fake_vector(text))

    alpha = _make_root(tmp_path, "alpha", "alpha contract")
    beta = _make_root(tmp_path, "beta", "beta invoice")
    (alpha / "alpha.txt").write_text("alpha renewal contract", encoding="utf-8")
    (beta / "beta.txt").write_text("beta invoice receipt", encoding="utf-8")
    _scan_and_seed_document(alpha, "alpha.txt", "alpha renewal contract", repeat=3)
    _scan_and_seed_document(beta, "beta.txt", "beta invoice receipt", repeat=3)
    assert index_scope_to_fts(alpha, IndexOptions(force=True))["status"] == "ok"
    assert index_scope_to_fts(beta, IndexOptions(force=True))["status"] == "ok"
    index_routing(
        alpha, RoutingIndexOptions(force=True, build_semantic=True), summary_generator=_fake_summary
    )
    built = index_routing(
        beta, RoutingIndexOptions(force=True, build_semantic=True), summary_generator=_fake_summary
    )

    # DP5 parity: FTS and semantic projections cover the identical unit set.
    assert built["global_representative_semantic"]["status"] == "ok"
    assert (
        built["global_representative_semantic"]["counts"]["summary_nodes_planned"]
        == built["global_representative_fts"]["counts"]["summary_nodes_planned"]
    )

    result = search_text_indexes("alpha renewal", SearchOptions(limit=10))
    trace = result["route_trace"]
    modes = {route["mode"]: route["status"] for route in trace["routes"]}
    assert modes["global_representative_fts"] == "used"
    assert modes["global_representative_semantic"] == "used"
    assert trace["fused_selection"]
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


# --------------------------------------------------------------------------- #
# D3 — media SigLIP representative routing (B1/B2/B3)
# --------------------------------------------------------------------------- #


def test_kmeans_medoids_selects_one_per_cluster() -> None:
    pytest.importorskip("scipy")
    vectors = [
        [1.0, 0.0, 0.0],
        [0.99, 0.1, 0.0],
        [0.99, -0.1, 0.0],
        [0.0, 1.0, 0.0],
        [0.0, 0.99, 0.1],
    ]
    ids = ["a1", "a2", "a3", "b1", "b2"]

    medoids = _kmeans_medoids(vectors, ids, k_max=16)

    # n=5 -> k=ceil(sqrt(2.5))=2: one medoid drawn from each visual cluster.
    assert len(medoids) == 2
    assert any(medoid.startswith("a") for medoid in medoids)
    assert any(medoid.startswith("b") for medoid in medoids)


def _img_vec(relative_path: str) -> list[float]:
    # Two visual clusters by filename prefix, with a small intra-cluster offset.
    if relative_path.startswith("a"):
        base = [1.0, 0.0, 0.0]
    else:
        base = [0.0, 1.0, 0.0]
    jitter = (hash(relative_path) % 5) / 100.0
    raw = [base[0], base[1] + jitter, base[2]]
    norm = sum(value * value for value in raw) ** 0.5 or 1.0
    return [value / norm for value in raw]


def _image_asset_map(root_id: str) -> dict[str, str]:
    with sqlite3.connect(catalog_path()) as conn:
        rows = conn.execute(
            """
            SELECT si.relative_path, a.asset_id
            FROM media_assets a
            JOIN source_items si ON si.source_item_id = a.source_item_id
            WHERE si.root_id = ? AND a.media_class = 'image'
            """,
            (root_id,),
        ).fetchall()
    return {relative_path: asset_id for relative_path, asset_id in rows}


def _seed_image_store(
    scope_id: str, asset_map: dict[str, str], profile: str = "siglip2_base"
) -> None:
    import lancedb

    from even.image_index import TABLE_NAME
    from even.paths import workspace_root

    store_dir = workspace_root() / f"semantic/image/{profile}/{scope_id}.lancedb"
    store_dir.mkdir(parents=True, exist_ok=True)
    data = [
        {
            "asset_id": asset_id,
            "scope_id": scope_id,
            "image_profile": profile,
            "vector": _img_vec(relative_path),
            "relative_path": relative_path,
            "root_label": "media",
            "media_type": "image/png",
        }
        for relative_path, asset_id in asset_map.items()
    ]
    db = lancedb.connect(str(store_dir))
    db.create_table(TABLE_NAME, data=data, mode="overwrite")

    # Register the store so the central image union (search text --image) finds it.
    from even import image_index

    image_index._upsert_image_registry(
        image_index._stable_id("img", scope_id, profile),
        scope_id,
        profile,
        f"semantic/image/{profile}/{scope_id}.lancedb",
        3,
        len(data),
        "test-watermark",
        "current",
        "2026-06-27T00:00:00Z",
    )


def _build_media_root_with_medoids(
    tmp_path: Path,
) -> tuple[str, str, str]:
    data = _make_root(tmp_path, "album", "ignored text")
    filenames = ["a1.png", "a2.png", "a3.png", "b1.png", "b2.png"]
    for filename in filenames:
        (data / filename).write_bytes(b"\x89PNG\r\n")
    scan = scan_folder_to_catalog(
        data, ScanOptions(max_files=None, max_bytes=None, max_depth=None)
    )
    for filename in filenames:
        _seed_media_caption(scan["root_id"], filename, f"{filename} lamp scene")
    # Seed the per-scope image proof store BEFORE routing so medoids are computed.
    _seed_image_store(scan["scope_id"], _image_asset_map(scan["root_id"]))

    result = index_routing(
        data, RoutingIndexOptions(force=True), summary_generator=_fake_summary
    )
    assert result["status"] == "ok"
    return str(data), scan["root_id"], scan["scope_id"]


def test_index_routing_persists_album_medoids_in_attrs(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    pytest.importorskip("tantivy")
    pytest.importorskip("lancedb")
    pytest.importorskip("scipy")
    monkeypatch.chdir(tmp_path)
    _, _root_id, _scope_id = _build_media_root_with_medoids(tmp_path)

    with sqlite3.connect(catalog_path()) as conn:
        attrs_json = conn.execute(
            "SELECT attrs_json FROM summary_nodes WHERE kind = 'album_summary'"
        ).fetchone()[0]
    attrs = json.loads(attrs_json)

    assert attrs["medoid_profile"] == "siglip2_base"
    assert 1 <= len(attrs["medoids"]) <= 5
    # Medoids are real asset ids drawn from this album.
    asset_ids = set(_image_asset_map(_root_id).values())
    assert set(attrs["medoids"]).issubset(asset_ids)


def test_build_global_siglip_store_reuses_medoid_vectors(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    pytest.importorskip("tantivy")
    pytest.importorskip("lancedb")
    pytest.importorskip("scipy")
    monkeypatch.chdir(tmp_path)
    _build_media_root_with_medoids(tmp_path)

    built = build_global_representative_siglip(force=True)

    assert built["status"] == "ok"
    assert built["image_profile"] == "siglip2_base"
    assert built["counts"]["albums"] == 1
    assert built["counts"]["media_representatives_indexed"] >= 1
    # Idempotent: an unforced rebuild over the same medoids is unchanged.
    again = build_global_representative_siglip(force=False)
    assert again["index_status"] == "current"
    assert again["counts"]["media_representatives_unchanged"] >= 1


def test_siglip_route_returns_fusable_album_hits(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    pytest.importorskip("tantivy")
    pytest.importorskip("lancedb")
    pytest.importorskip("scipy")
    monkeypatch.chdir(tmp_path)
    _, _root_id, scope_id = _build_media_root_with_medoids(tmp_path)
    assert build_global_representative_siglip(force=True)["status"] == "ok"

    route = _search_global_representatives_siglip(
        _img_vec("a1.png"), image_profile_name="siglip2_base", limit=5
    )

    assert route["status"] == "ok"
    assert route["hits"], "expected at least one album hit"
    top = route["hits"][0]
    assert top["kind"] == "album_summary"
    assert top["scope_id"] == scope_id

    # B3: the visual route fuses with a text route at scope granularity.
    fts_route = [{"summary_id": top["summary_id"], "scope_id": scope_id, "rank": 1}]
    fused = _fuse_representative_hits(
        [
            ("global_representative_fts", fts_route),
            ("global_representative_siglip", route["hits"]),
        ]
    )
    assert fused[0]["scope_id"] == scope_id
    assert "global_representative_siglip" in fused[0]["contributing_modes"]
    assert "global_representative_fts" in fused[0]["contributing_modes"]


class _FakeSiglipEmbedder:
    def embed_image(self, _image_bytes: bytes) -> list[float]:
        return [1.0, 0.0, 0.0]

    def embed_text(self, _text: str) -> list[float]:
        return [1.0, 0.0, 0.0]


def test_search_text_image_engages_visual_route_and_returns_image_hits(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    pytest.importorskip("tantivy")
    pytest.importorskip("lancedb")
    pytest.importorskip("scipy")
    monkeypatch.chdir(tmp_path)
    from even import image_index

    monkeypatch.setattr(image_index, "image_runtime_status", lambda: {"status": "ok"})
    monkeypatch.setattr(image_index, "_load_embedder", lambda profile: _FakeSiglipEmbedder())

    data_str, _root_id, scope_id = _build_media_root_with_medoids(tmp_path)
    data = Path(data_str)
    assert index_scope_to_fts(data, IndexOptions(force=True))["status"] == "ok"
    assert build_global_representative_siglip(force=True)["status"] == "ok"
    query_image = tmp_path / "query.png"
    query_image.write_bytes(b"\x89PNG\r\n")

    result = search_text_indexes(
        "lamp", SearchOptions(limit=10, image_paths=(str(query_image),))
    )

    # The SigLIP visual route joins routing (C3: explicit cross-modal probe only).
    modes = {route["mode"]: route["status"] for route in result["route_trace"]["routes"]}
    assert modes["global_representative_siglip"] == "used"
    # Image hits from the routed scope are returned alongside text hits.
    assert result["counts"]["image_hits_returned"] >= 1
    assert any(
        str(hit.get("ref") or "").startswith("corpus_cache.media_assets.")
        for hit in result["hits"]
    )
