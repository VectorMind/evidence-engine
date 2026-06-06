"""Structured command result files under the fixed cache root."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import uuid
from typing import Any

from agents_cli.paths import fixed_cache_root, results_root


@dataclass
class CommandRun:
    command: str
    run_id: str
    started_at: str
    result_dir: Path
    result_uri: str

    @classmethod
    def start(cls, command: str) -> "CommandRun":
        now = _utc_now()
        short_id = uuid.uuid4().hex[:10]
        run_id = f"{now.strftime('%Y%m%d%H%M%S')}-{short_id}"
        result_dir = (
            results_root()
            / now.strftime("%Y-%m-%d")
            / f"{now.strftime('%H%M%S')}-{short_id}"
        )
        result_dir.mkdir(parents=True, exist_ok=True)
        run = cls(
            command=command,
            run_id=run_id,
            started_at=_iso(now),
            result_dir=result_dir,
            result_uri=_relative_uri(result_dir),
        )
        run.event("started", {"command": command})
        return run

    def event(self, event_type: str, payload: dict[str, Any] | None = None) -> None:
        event = {
            "run_id": self.run_id,
            "command": self.command,
            "event_type": event_type,
            "created_at": _iso(_utc_now()),
        }
        if payload:
            event.update(payload)
        events_path = self.result_dir / "events.jsonl"
        with events_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, sort_keys=True) + "\n")

    def finish(self, payload: dict[str, Any]) -> None:
        final_payload = dict(payload)
        final_payload["run_id"] = self.run_id
        final_payload["started_at"] = self.started_at
        final_payload["completed_at"] = _iso(_utc_now())
        final_payload["result_uri"] = self.result_uri
        result_path = self.result_dir / "result.json"
        result_path.write_text(
            json.dumps(final_payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        self.event("completed", {"status": final_payload.get("status", "unknown")})


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _relative_uri(path: Path) -> str:
    return path.relative_to(fixed_cache_root()).as_posix()
