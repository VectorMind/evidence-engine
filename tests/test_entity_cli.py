from __future__ import annotations

import json
from pathlib import Path

import pytest

from even.cli import build_parser, main
from even.paths import catalog_path


def test_entity_add_parses() -> None:
    parser = build_parser()

    args = parser.parse_args(["entity", "add", "Acme", "--kind", "organization"])

    assert args.handler.__name__ == "entity_add"
    assert args.name == "Acme"
    assert args.kind == "organization"


def test_entity_review_requires_one_decision_flag() -> None:
    parser = build_parser()

    with pytest.raises(SystemExit):
        parser.parse_args(["entity", "review", "ent_x"])


def test_entity_add_and_show_round_trip(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)

    assert main(["entity", "add", "Northwind Salvage", "--kind", "organization"]) == 0
    added = json.loads(capsys.readouterr().out)
    entity_id = added["entity_id"]
    assert added["entity"]["canonical_name"] == "Northwind Salvage"

    assert main(["entity", "alias", entity_id, "N.W. Salvage", "--kind", "abbreviation"]) == 0
    alias_payload = json.loads(capsys.readouterr().out)
    assert alias_payload["status"] == "ok"

    assert main(["entity", "show", entity_id]) == 0
    shown = json.loads(capsys.readouterr().out)
    assert shown["entity"]["entity_id"] == entity_id
    assert shown["aliases"][0]["alias_text"] == "N.W. Salvage"
    assert catalog_path().exists()


def test_entity_list_filters_by_kind(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)

    main(["entity", "add", "Org One", "--kind", "organization"])
    capsys.readouterr()
    main(["entity", "add", "Person One", "--kind", "person"])
    capsys.readouterr()

    assert main(["entity", "list", "--kind", "organization"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["counts"]["entities_returned"] == 1
    assert payload["entities"][0]["canonical_name"] == "Org One"


def test_entity_review_accept_updates_entity(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)

    main(["entity", "add", "Northwind Salvage", "--kind", "organization"])
    entity_id = json.loads(capsys.readouterr().out)["entity_id"]

    assert main(["entity", "review", entity_id, "--accept"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"
    assert payload["review_status"] == "accepted"


def test_entity_link_rejects_unresolvable_ref(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)

    main(["entity", "add", "Northwind Salvage", "--kind", "organization"])
    entity_id = json.loads(capsys.readouterr().out)["entity_id"]

    exit_code = main(
        ["entity", "link", entity_id, "corpus_cache.document_objects.missing", "--role", "mention"]
    )
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert payload["error_kind"] == "evidence_ref_not_found"
