"""Launch the web viewer over the caller's evidence cache.

The viewer is the Node/Astro project in ``src/web`` (plan
``plans/2026-07/04-webui-viewer``). This module keeps Node an implementation
detail behind the ``even`` entrypoint: it resolves the workspace the same way
every other command does (``EVEN_CACHE`` / ``.env`` via ``even.paths``),
passes it to the Node process, and runs either the built server
(``dist/server/entry.mjs``) or the Astro dev server.

Unlike one-shot commands, ``serve`` is a long-running foreground process, so
it does not create a ``results/`` run record: result artifacts are one-shot
records of CLI invocations, and a server has no single completion to record.
It prints one JSON status line before handing the console to the child.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any

from even.paths import workspace_root

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 4321


@dataclass
class ServeOptions:
    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT
    dev: bool = False


def web_root() -> Path:
    """Return the viewer project directory (``src/web``, sibling of ``even``)."""

    return Path(__file__).resolve().parent.parent / "web"


def run_serve(options: ServeOptions) -> int:
    root = web_root()
    if not (root / "package.json").exists():
        _emit(
            {
                "command": "serve",
                "status": "failed",
                "error_kind": "web_project_missing",
                "message": (
                    f"Web viewer project not found at {root}. "
                    "The viewer runs from a repository checkout."
                ),
            }
        )
        return 1

    workspace = workspace_root()
    env = dict(os.environ)
    env["EVEN_CACHE"] = str(workspace)
    env["HOST"] = options.host
    env["PORT"] = str(options.port)

    built_entry = root / "dist" / "server" / "entry.mjs"
    use_dev = options.dev or not built_entry.exists()
    if use_dev:
        pnpm = shutil.which("pnpm")
        if pnpm is None:
            _emit(
                {
                    "command": "serve",
                    "status": "failed",
                    "error_kind": "pnpm_missing",
                    "message": (
                        "pnpm is required for the dev server "
                        "(or build first: pnpm --dir src/web build)."
                    ),
                }
            )
            return 1
        command = [
            pnpm,
            "dev",
            "--host",
            options.host,
            "--port",
            str(options.port),
        ]
        mode = "dev"
    else:
        node = shutil.which("node")
        if node is None:
            _emit(
                {
                    "command": "serve",
                    "status": "failed",
                    "error_kind": "node_missing",
                    "message": "node is required to run the built viewer server.",
                }
            )
            return 1
        command = [node, str(built_entry)]
        mode = "built"

    _emit(
        {
            "command": "serve",
            "status": "running",
            "mode": mode,
            "url": f"http://{options.host}:{options.port}/",
            "workspace_root": str(workspace),
            "web_root": str(root),
        }
    )
    process = subprocess.Popen(command, cwd=root, env=env)
    try:
        return process.wait()
    except KeyboardInterrupt:
        process.terminate()
        process.wait()
        return 0


def _emit(payload: dict[str, Any]) -> None:
    json.dump(payload, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    sys.stdout.flush()
