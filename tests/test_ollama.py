from __future__ import annotations

import json
from typing import Any

import pytest

from even import ollama


class _FakeResponse:
    def __init__(self, body: bytes) -> None:
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *exc: object) -> bool:
        return False


def test_generate_text_posts_payload_and_returns_stripped_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def fake_urlopen(request: Any, timeout: float | None = None) -> _FakeResponse:
        captured["url"] = request.full_url
        captured["data"] = json.loads(request.data.decode("utf-8"))
        captured["timeout"] = timeout
        return _FakeResponse(json.dumps({"response": "  hello  "}).encode("utf-8"))

    monkeypatch.setattr(ollama.urllib.request, "urlopen", fake_urlopen)

    text = ollama.generate_text(
        "hi",
        model="m",
        url="http://localhost:11434",
        timeout=12.0,
        options={"temperature": 0},
    )

    assert text == "hello"
    assert captured["url"] == "http://localhost:11434/api/generate"
    assert captured["data"] == {
        "model": "m",
        "prompt": "hi",
        "stream": False,
        "options": {"temperature": 0},
    }
    assert captured["timeout"] == 12.0


def test_generate_text_omits_options_when_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def fake_urlopen(request: Any, timeout: float | None = None) -> _FakeResponse:
        captured["data"] = json.loads(request.data.decode("utf-8"))
        return _FakeResponse(json.dumps({"response": "ok"}).encode("utf-8"))

    monkeypatch.setattr(ollama.urllib.request, "urlopen", fake_urlopen)

    ollama.generate_text("hi", model="m", url="http://localhost:11434")

    assert "options" not in captured["data"]
