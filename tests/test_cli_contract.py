from __future__ import annotations

import json
from pathlib import Path

import pytest

from even.cli import build_parser, main
from even.paths import catalog_path, even_home, model_cache_root, workspace_root


def test_parser_uses_new_sources_scan_surface() -> None:
    parser = build_parser()

    args = parser.parse_args(["sources", "scan", "C:/example"])

    assert args.handler.__name__ == "sources_scan"


def test_old_scan_folder_surface_is_removed() -> None:
    parser = build_parser()

    with pytest.raises(SystemExit):
        parser.parse_args(["scan", "folder", "C:/example"])


def test_old_catalog_migrate_surface_is_removed() -> None:
    parser = build_parser()

    with pytest.raises(SystemExit):
        parser.parse_args(["catalog", "migrate"])


def test_health_outputs_json_for_workspace(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.chdir(tmp_path)

    assert main(["health"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["command"] == "health"
    assert payload["workspace_root"] == str(tmp_path / ".cache")
    assert "cache_root" not in payload


def test_pytest_default_paths_are_test_local(tmp_path: Path) -> None:
    assert workspace_root() == tmp_path / ".cache"
    assert even_home() == tmp_path / ".even-home"


def test_even_cache_env_selects_workspace_cache(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    cache = tmp_path / "central-cache"
    monkeypatch.setenv("EVEN_CACHE", str(cache))
    monkeypatch.chdir(tmp_path)

    assert workspace_root() == cache
    assert catalog_path() == cache / "catalog" / "catalog.sqlite"


def test_dotenv_even_cache_overrides_process_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    env_cache = tmp_path / "env-cache"
    dotenv_cache = tmp_path / "dotenv-cache"
    monkeypatch.setenv("EVEN_CACHE", str(env_cache))
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text(
        f"EVEN_CACHE={dotenv_cache}\n",
        encoding="utf-8",
    )

    assert workspace_root() == dotenv_cache


def test_even_home_defines_model_cache(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    home = tmp_path / "even-home"
    monkeypatch.setenv("EVEN_HOME", str(home))
    monkeypatch.chdir(tmp_path)

    assert even_home() == home
    assert model_cache_root() == home / "models"


def test_sources_scan_writes_workspace_results(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    fixture = Path(__file__).parent / "fixtures" / "scan-basic"

    assert main(["sources", "scan", str(fixture)]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["command"] == "sources scan"
    assert payload["workspace_root"] == str(workspace_root())
    assert catalog_path().exists()
    assert payload["result_uri"].startswith("results/")
    assert (workspace_root() / payload["result_uri"] / "result.json").exists()
    assert (workspace_root() / payload["summary_uri"]).exists()


def test_sources_scan_is_media_aware(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import sqlite3

    monkeypatch.chdir(tmp_path)
    data = tmp_path / "data"
    data.mkdir()
    (data / "photo.png").write_bytes(b"\x89PNG\r\n")
    (data / "clip.mp4").write_bytes(b"\x00\x00\x00")
    (data / "part.obj").write_text("v 0 0 0\n", encoding="utf-8")
    (data / "notes.txt").write_text("hello", encoding="utf-8")

    assert main(["sources", "scan", str(data)]) == 0

    with sqlite3.connect(catalog_path()) as conn:
        media_types = {
            row[0]: row[1]
            for row in conn.execute(
                "SELECT relative_path, media_type FROM source_items "
                "WHERE item_kind = 'file'"
            )
        }

    assert media_types.get("photo.png") == "image/png"
    assert media_types.get("clip.mp4") == "video/mp4"
    assert media_types.get("part.obj") == "model/obj"
    assert media_types.get("notes.txt") == "text/plain"


def test_parse_selection_excludes_media_items(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from even.inventory import ScanOptions, scan_folder_to_catalog
    from even.parse import _source_items_for_root

    monkeypatch.chdir(tmp_path)
    data = tmp_path / "data"
    data.mkdir()
    (data / "report.txt").write_text("a document", encoding="utf-8")
    (data / "photo.png").write_bytes(b"\x89PNG\r\n")
    (data / "clip.mp4").write_bytes(b"\x00")
    (data / "part.obj").write_text("v 0 0 0\n", encoding="utf-8")

    scan = scan_folder_to_catalog(
        data, ScanOptions(max_files=None, max_bytes=None, max_depth=None)
    )
    selected = {
        item["relative_path"] for item in _source_items_for_root(scan["root_id"], None)
    }

    assert selected == {"report.txt"}


def test_media_inspect_writes_image_metadata(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    import sqlite3

    pil = pytest.importorskip("PIL.Image")

    monkeypatch.chdir(tmp_path)
    data = tmp_path / "data"
    data.mkdir()
    pil.new("RGB", (48, 32), color=(10, 20, 30)).save(data / "swatch.png")
    (data / "notes.txt").write_text("not an image", encoding="utf-8")

    assert main(["media", "inspect", str(data)]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["command"] == "media inspect"
    assert payload["counts"]["assets_written"] == 1

    with sqlite3.connect(catalog_path()) as conn:
        asset = conn.execute(
            "SELECT media_class, primary_artifact_id FROM media_assets"
        ).fetchone()
        image = conn.execute(
            "SELECT width, height, color_mode FROM image_metadata"
        ).fetchone()
        artifact_count = conn.execute(
            "SELECT COUNT(*) FROM media_artifacts WHERE artifact_kind = 'thumbnail'"
        ).fetchone()[0]

    assert asset[0] == "image"
    assert asset[1] is not None  # thumbnail wired as primary artifact
    assert image == (48, 32, "RGB")
    assert artifact_count == 1
