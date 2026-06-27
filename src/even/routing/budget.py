"""Token estimation, generation-time calibration, and build-budget reporting."""

from __future__ import annotations

import json
import time
from typing import Any

from even.paths import calibration_path
from even.routing.shared import (
    _CALIBRATION_MIN_ELAPSED,
    CALIBRATION_DEFAULT_TPS,
    SummaryGenerator,
    _iso,
    _utc_now,
)


def _estimate_tokens(*texts: str) -> int:
    """Rough token estimate (~4 chars/token) used only for time budgeting."""

    chars = sum(len(text) for text in texts if text)
    return max(1, chars // 4)


def _blend_tokens_per_sec(
    previous: float | None, sample: float, alpha: float = 0.3
) -> float:
    """Exponential moving average so the calibration self-corrects over builds."""

    if not previous or previous <= 0:
        return sample
    return (1 - alpha) * previous + alpha * sample


def _token_budget(max_build_seconds: float, tokens_per_sec: float) -> int:
    """Derive an advisory token budget from the decisive time budget."""

    return max(0, int(max_build_seconds * tokens_per_sec))


def _load_calibration() -> dict[str, Any]:
    try:
        return dict(json.loads(calibration_path().read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError, ValueError):
        return {}


def _save_calibration(data: dict[str, Any]) -> None:
    path = calibration_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    except OSError:
        pass


def _current_tokens_per_sec() -> float:
    try:
        tps = float(_load_calibration().get("tokens_per_sec"))
    except (TypeError, ValueError):
        return CALIBRATION_DEFAULT_TPS
    return tps if tps > 0 else CALIBRATION_DEFAULT_TPS


def _record_calibration(prompt: str, response: str, elapsed: float) -> None:
    if elapsed < _CALIBRATION_MIN_ELAPSED:
        return
    sample = _estimate_tokens(prompt, response) / elapsed
    if sample <= 0:
        return
    data = _load_calibration()
    try:
        previous = float(data["tokens_per_sec"])
    except (KeyError, TypeError, ValueError):
        previous = None
    data["tokens_per_sec"] = round(_blend_tokens_per_sec(previous, sample), 3)
    data["samples"] = int(data.get("samples", 0)) + 1
    data["updated_at"] = _iso(_utc_now())
    _save_calibration(data)


def _generate_and_calibrate(
    generator: SummaryGenerator,
    prompt: str,
    *,
    model: str,
    url: str,
    timeout: float,
) -> str:
    start = time.monotonic()
    text = generator(prompt, model=model, url=url, timeout=timeout)
    try:
        _record_calibration(prompt, str(text or ""), time.monotonic() - start)
    except Exception:  # noqa: BLE001 - calibration is best-effort only.
        pass
    return text


def _build_budget_report(max_build_seconds: float, build_started: float) -> dict[str, Any]:
    tokens_per_sec = _current_tokens_per_sec()
    return {
        "max_build_seconds": max_build_seconds,
        "tokens_per_sec": round(tokens_per_sec, 3),
        "derived_token_budget": _token_budget(max_build_seconds, tokens_per_sec),
        "elapsed_seconds": round(time.monotonic() - build_started, 3),
    }


def _budget_skipped_summary(summary_id: str) -> dict[str, Any]:
    return {
        "status": "deferred",
        "error_kind": "build_budget_exhausted",
        "message": "Skipped companion generation: per-root build budget reached.",
        "summary_id": summary_id,
        "summary_status": "deferred",
        "index_status": "deferred",
        "counts": {
            "media_assets_considered": 0,
            "media_assets_sampled": 0,
            "summary_nodes_written": 0,
        },
    }


