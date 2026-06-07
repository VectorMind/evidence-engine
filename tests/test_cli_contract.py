from __future__ import annotations

import json
from pathlib import Path

import pytest

from documents_manager.cli import build_parser, main
from documents_manager.paths import catalog_path, workspace_root


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
    assert payload["workspace_root"] == str(tmp_path / ".documents-manager")
    assert "cache_root" not in payload


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
