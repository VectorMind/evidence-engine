"""Minimal local Ollama REST client for vision-model observations.

Only talks to a local Ollama endpoint over HTTP. Never pulls models and never
calls a remote provider. Images are sent as base64 of the source bytes read in
place; sources are never copied or modified.
"""

from __future__ import annotations

import base64
import json
import time
from typing import Any
import urllib.error
import urllib.request

DEFAULT_URL = "http://localhost:11434"
DEFAULT_MODEL = "granite3.2-vision"


class EmptyVlmResponse(RuntimeError):
    """The VLM returned HTTP 200 with no text.

    Seen when an image is just over the model's image-token budget: Ollama answers
    200 but does not generate (no ``eval_count``, empty ``response``). Treated as a
    failure so the caller records it instead of writing a blank caption.
    """


def ollama_available(url: str = DEFAULT_URL, *, timeout: float = 5.0) -> bool:
    """Return True if a local Ollama server answers at the given URL."""

    try:
        with urllib.request.urlopen(f"{url}/api/tags", timeout=timeout) as response:
            return response.status == 200
    except (urllib.error.URLError, OSError):
        return False


def generate_text(
    prompt: str,
    *,
    model: str = DEFAULT_MODEL,
    url: str = DEFAULT_URL,
    timeout: float = 300.0,
    options: dict[str, Any] | None = None,
) -> str:
    """Run a single text-only generation and return the stripped response text.

    Policy-free transport: raises plain transport/server/parse errors so callers
    can classify them. Endpoint policy (e.g. localhost-only) belongs to callers.
    """

    payload: dict[str, Any] = {"model": model, "prompt": prompt, "stream": False}
    if options:
        payload["options"] = options
    request = urllib.request.Request(
        f"{url}/api/generate",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = json.load(response)
    return str(body.get("response", "")).strip()


def generate_from_image(
    image_bytes: bytes,
    prompt: str,
    *,
    model: str = DEFAULT_MODEL,
    url: str = DEFAULT_URL,
    timeout: float = 300.0,
) -> dict[str, Any]:
    """Run a single vision generation and return text plus timing.

    Returns a dict with ``text`` and ``elapsed_ms``. Raises on transport or
    server errors so callers can record a per-item failure.
    """

    payload = json.dumps(
        {
            "model": model,
            "prompt": prompt,
            "images": [base64.b64encode(image_bytes).decode("ascii")],
            "stream": False,
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        f"{url}/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    started = time.monotonic()
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = json.load(response)
    elapsed_ms = round((time.monotonic() - started) * 1000, 1)
    text = str(body.get("response", "")).strip()
    if not text:
        # 200 with no generation (e.g. image just over the token budget). Fail
        # loudly rather than persist an empty caption.
        raise EmptyVlmResponse("vlm returned an empty response")
    return {"text": text, "elapsed_ms": elapsed_ms}
