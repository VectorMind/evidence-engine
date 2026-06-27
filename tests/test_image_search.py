"""Image index + visual search round-trip with a fake embedder (no model download)."""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from even.cli import main


class _FakeEmbedder:
    """Deterministic 3-d vector from an image's average color."""

    def embed_image(self, image_bytes: bytes) -> list[float]:
        from PIL import Image

        with Image.open(io.BytesIO(image_bytes)) as image:
            r, g, b = image.convert("RGB").resize((1, 1)).getpixel((0, 0))
        return [r / 255, g / 255, b / 255]

    def embed_text(self, text: str) -> list[float]:
        return [0.0, 0.0, 0.0]


def test_index_and_search_image_round_trip(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    pil = pytest.importorskip("PIL.Image")
    pytest.importorskip("lancedb")

    monkeypatch.setattr(
        "even.image_index._load_embedder", lambda profile: _FakeEmbedder()
    )

    monkeypatch.chdir(tmp_path)
    data = tmp_path / "data"
    data.mkdir()
    pil.new("RGB", (16, 16), (200, 10, 10)).save(data / "red.png")
    pil.new("RGB", (16, 16), (200, 10, 10)).save(data / "red2.png")
    pil.new("RGB", (16, 16), (10, 10, 200)).save(data / "blue.png")

    assert main(["index", "scope", str(data), "--image"]) == 0
    index_payload = json.loads(capsys.readouterr().out)
    assert index_payload["counts"]["assets_indexed"] == 3

    assert main(["search", "image", str(data / "red.png")]) == 0
    search_payload = json.loads(capsys.readouterr().out)
    hits = search_payload["hits"]

    assert len(hits) == 3
    assert hits[0]["distance"] < 0.01  # a red image matches exactly
    assert hits[-1]["relative_path"] == "blue.png"  # the odd one out ranks last
    assert all(h["ref"].startswith("corpus_cache.media_assets.") for h in hits)


def test_search_image_skips_incompatible_vector_stores(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    pil = pytest.importorskip("PIL.Image")
    pytest.importorskip("lancedb")

    monkeypatch.setattr(
        "even.image_index._load_embedder", lambda profile: _FakeEmbedder()
    )

    monkeypatch.chdir(tmp_path)
    data = tmp_path / "data"
    data.mkdir()
    pil.new("RGB", (16, 16), (200, 10, 10)).save(data / "red.png")
    pil.new("RGB", (16, 16), (10, 10, 200)).save(data / "blue.png")

    assert main(["index", "scope", str(data), "--image"]) == 0
    capsys.readouterr()
    _seed_incompatible_image_store("scope_bad")

    assert main(["search", "image", str(data / "red.png")]) == 0
    search_payload = json.loads(capsys.readouterr().out)

    assert search_payload["status"] == "ok"
    assert search_payload["counts"]["indexes_searched"] == 1
    assert search_payload["counts"]["indexes_skipped"] == 1
    assert search_payload["counts"]["index_failures"] == 0
    assert search_payload["counts"]["hits_returned"] == 2
    assert search_payload["skipped"][0]["error_kind"] == (
        "image_vector_dimension_incompatible"
    )


def _seed_incompatible_image_store(scope_id: str) -> None:
    import lancedb

    from even import image_index
    from even.paths import workspace_root

    store_uri = f"semantic/image/siglip2_base/{scope_id}.lancedb"
    store_dir = workspace_root() / store_uri
    store_dir.mkdir(parents=True, exist_ok=True)
    db = lancedb.connect(str(store_dir))
    db.create_table(
        image_index.TABLE_NAME,
        data=[
            {
                "asset_id": "asset_bad",
                "scope_id": scope_id,
                "image_profile": "siglip2_base",
                "vector": [0.0, 1.0],
                "relative_path": "bad.png",
                "root_label": "bad",
                "media_type": "image/png",
            }
        ],
        mode="overwrite",
    )
    image_index._upsert_image_registry(
        image_index._stable_id("img", scope_id, "siglip2_base"),
        scope_id,
        "siglip2_base",
        store_uri,
        2,
        1,
        "test-watermark",
        "current",
        "2026-06-27T00:00:00Z",
    )
