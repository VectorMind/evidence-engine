"""Importance prior/parse/learn subsystem for summary nodes."""

from __future__ import annotations

from pathlib import Path

from even.routing.budget import _load_calibration, _save_calibration
from even.routing.shared import _IMPORTANCE_RE, _routing_defaults


def _parse_importance(text: str) -> tuple[str, float | None]:
    """Split a trailing ``IMPORTANCE: <0..1>`` marker out of model text.

    Returns the summary text with the marker removed and the parsed importance,
    or ``None`` when the model did not emit a usable marker.
    """

    if not text:
        return text, None
    match = None
    for match in _IMPORTANCE_RE.finditer(text):
        pass
    if match is None:
        return text, None
    try:
        value = float(match.group(1))
    except ValueError:
        return text, None
    value = max(0.0, min(1.0, value))
    cleaned = (text[: match.start()] + text[match.end() :]).strip()
    return cleaned, value


def _importance_prior(*tokens: str) -> float:
    """Seed importance from deterministic path priors before the model refines it.

    Paths matching the configured low-importance prior list (build/tooling/system
    folders) or the learned low-importance list start low; everything else starts
    at the neutral default.
    """

    config = _routing_defaults()
    default = float(config.get("importance_default", 0.5))
    low = float(config.get("importance_low_prior", 0.1))
    priors = [str(prior).lower() for prior in config.get("importance_priors", [])]
    priors += _learned_low_priors()
    haystack = " ".join(token for token in tokens if token).lower().replace("\\", "/")
    for prior in priors:
        if prior and prior in haystack:
            return low
    return default


def _importance_learn_threshold() -> float:
    return float(_routing_defaults().get("importance_learn_threshold", 0.2))


def _learned_low_priors() -> list[str]:
    return [
        str(prior).lower()
        for prior in _load_calibration().get("learned_low_priors", [])
        if str(prior).strip()
    ]


def _learn_low_prior(token: str) -> None:
    """Teach the dynamic prior list a path the model rated clearly unimportant."""

    basename = Path(str(token or "").replace("\\", "/")).name.strip().lower()
    if not basename:
        return
    data = _load_calibration()
    learned = {str(prior).lower() for prior in data.get("learned_low_priors", [])}
    if basename in learned:
        return
    learned.add(basename)
    data["learned_low_priors"] = sorted(learned)[:200]
    _save_calibration(data)


def _resolve_importance(parsed: float | None, *prior_tokens: str) -> float:
    """Use the model importance when present, else the deterministic prior."""

    if parsed is not None:
        return parsed
    return _importance_prior(*prior_tokens)


