"""Tests for media metadata extraction helpers and CLI dispatch."""

from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import struct
from types import SimpleNamespace

import pytest

from coev.cli import main
from coev.media import _model3d_fields_obj, _model3d_fields_stl, _video_fields
from coev.paths import catalog_path


def test_model3d_obj_fields_counts_and_bbox() -> None:
    obj = "\n".join(
        [
            "v 0 0 0",
            "v 1 0 0",
            "v 0 2 0",
            "vn 0 0 1",
            "vt 0 0",
            "f 1 2 3",
        ]
    )

    fields = _model3d_fields_obj(obj.encode("utf-8"))

    assert fields["format"] == "OBJ"
    assert fields["vertex_count"] == 3
    assert fields["face_count"] == 1
    assert fields["has_normals"] == 1
    assert fields["has_uv"] == 1
    assert fields["bbox_min"] == [0, 0, 0]
    assert fields["bbox_max"] == [1, 2, 0]


def test_model3d_stl_binary_fields() -> None:
    triangle = (
        struct.pack("<3f", 0, 0, 1)  # normal
        + struct.pack("<3f", 0, 0, 0)
        + struct.pack("<3f", 1, 0, 0)
        + struct.pack("<3f", 0, 1, 0)
        + struct.pack("<H", 0)
    )
    raw = b"\x00" * 80 + struct.pack("<I", 1) + triangle

    fields = _model3d_fields_stl(raw)

    assert fields["format"] == "STL"
    assert fields["face_count"] == 1
    assert fields["vertex_count"] == 3
    assert fields["has_normals"] == 1
    assert fields["bbox_min"] == [0, 0, 0]
    assert fields["bbox_max"] == [1, 1, 0]


def test_video_fields_maps_tracks() -> None:
    tracks = [
        SimpleNamespace(
            track_type="General",
            format="MPEG-4",
            duration="5000",
            overall_bit_rate="800000",
            recorded_date=None,
            tagged_date=None,
        ),
        SimpleNamespace(
            track_type="Video",
            format="AVC",
            width="1920",
            height="1080",
            frame_rate="29.970",
        ),
        SimpleNamespace(track_type="Audio", format="AAC"),
    ]

    fields = _video_fields(tracks)

    assert fields["container"] == "MPEG-4"
    assert fields["video_codec"] == "AVC"
    assert fields["audio_codec"] == "AAC"
    assert fields["width"] == 1920
    assert fields["height"] == 1080
    assert fields["duration_seconds"] == 5.0
    assert fields["frame_rate"] == pytest.approx(29.97)
    assert fields["bit_rate"] == 800000


def test_media_describe_writes_observations(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    pil = pytest.importorskip("PIL.Image")

    monkeypatch.setattr("coev.media.ollama_available", lambda url, **kw: True)

    calls = {"n": 0}

    def fake_generate(image_bytes, prompt, **kwargs):
        calls["n"] += 1
        text = "a small red square" if "Describe" in prompt else "illustration"
        return {"text": text, "elapsed_ms": 12.0}

    monkeypatch.setattr("coev.media.generate_from_image", fake_generate)

    monkeypatch.chdir(tmp_path)
    data = tmp_path / "data"
    data.mkdir()
    pil.new("RGB", (32, 32), color=(200, 10, 10)).save(data / "square.png")

    assert main(["media", "describe", str(data), "--kind"]) == 0

    with sqlite3.connect(catalog_path()) as conn:
        rows = {
            kind: (value, producer)
            for kind, value, producer in conn.execute(
                "SELECT observation_kind, value_text, producer FROM media_observations"
            )
        }

    assert rows["caption"][0] == "a small red square"
    assert rows["media_kind"][0] == "illustration"
    assert rows["caption"][1] == "ollama:granite3.2-vision"
    assert calls["n"] == 2


def test_media_inspect_writes_model3d_metadata(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    data = tmp_path / "data"
    data.mkdir()
    (data / "tri.obj").write_text(
        "v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n", encoding="utf-8"
    )

    assert main(["media", "inspect", str(data)]) == 0

    with sqlite3.connect(catalog_path()) as conn:
        asset_class = conn.execute(
            "SELECT media_class FROM media_assets"
        ).fetchone()[0]
        model = conn.execute(
            "SELECT format, vertex_count, face_count, bbox_max FROM model3d_metadata"
        ).fetchone()

    assert asset_class == "model3d"
    assert model[0] == "OBJ"
    assert model[1] == 3
    assert model[2] == 1
    assert json.loads(model[3]) == [1, 1, 0]
