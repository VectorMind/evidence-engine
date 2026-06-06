"""Minimal agents-docs command surface.

The first scaffold intentionally uses only the Python standard library so the
binding command shape can be tested before heavy optional dependencies are
installed.
"""

from __future__ import annotations

import argparse
import json
import platform
import sys
from pathlib import Path
from typing import Any

from agents_cli import __version__
from agents_cli.catalog import catalog_status_report, create_catalog, migrate_catalog
from agents_cli.paths import catalog_path, fixed_cache_root, results_root


SCHEMA_VERSION = "0.2"


def _emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def _base_payload(command: str) -> dict[str, Any]:
    return {
        "command": command,
        "package_version": __version__,
        "schema_version": SCHEMA_VERSION,
        "cache_root": str(fixed_cache_root()),
        "catalog_path": str(catalog_path()),
    }


def _not_implemented(command: str, **extra: Any) -> int:
    payload = _base_payload(command)
    payload.update(
        {
            "status": "not_implemented",
            "message": "Command surface is reserved; runtime behavior lands in later phases.",
        }
    )
    payload.update(extra)
    _emit(payload)
    return 2


def catalog_create(_: argparse.Namespace) -> int:
    payload = _base_payload("catalog create")
    payload.update(create_catalog())
    _emit(payload)
    return 0 if payload["status"] in {"created", "current", "migrated"} else 1


def catalog_migrate(_: argparse.Namespace) -> int:
    payload = _base_payload("catalog migrate")
    payload.update(migrate_catalog())
    _emit(payload)
    return 0 if payload["status"] in {"current", "migrated"} else 1


def catalog_status(_: argparse.Namespace) -> int:
    payload = _base_payload("catalog status")
    payload.update(catalog_status_report())
    _emit(payload)
    return 0 if payload["status"] in {"current", "missing", "stale"} else 1


def health(_: argparse.Namespace) -> int:
    payload = _base_payload("health")
    payload.update(
        {
            "status": "ok",
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "paths": {
                "cache_root_exists": fixed_cache_root().exists(),
                "catalog_exists": catalog_path().exists(),
                "results_root_exists": results_root().exists(),
            },
            "checks": [
                {"name": "fixed_cache_contract", "status": "ok"},
                {"name": "sqlite_stdlib", "status": "ok"},
            ],
        }
    )
    _emit(payload)
    return 0


def scan_folder(args: argparse.Namespace) -> int:
    return _not_implemented("scan folder", source_path=str(Path(args.path)))


def parse_folder(args: argparse.Namespace) -> int:
    return _not_implemented("parse folder", source_path=str(Path(args.path)))


def index_folder(args: argparse.Namespace) -> int:
    return _not_implemented("index folder", source_path=str(Path(args.path)))


def search_text(args: argparse.Namespace) -> int:
    return _not_implemented("search text", query=args.query)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agents-docs",
        description="Local document corpus-cache CLI.",
    )
    parser.set_defaults(handler=None)
    subparsers = parser.add_subparsers(dest="command")

    catalog = subparsers.add_parser("catalog", help="Catalog control commands.")
    catalog_sub = catalog.add_subparsers(dest="catalog_command")

    catalog_create_parser = catalog_sub.add_parser(
        "create", help="Create the fixed home catalog if it is missing."
    )
    catalog_create_parser.set_defaults(handler=catalog_create)

    catalog_migrate_parser = catalog_sub.add_parser(
        "migrate", help="Upgrade the fixed home catalog if it exists."
    )
    catalog_migrate_parser.set_defaults(handler=catalog_migrate)

    catalog_status_parser = catalog_sub.add_parser(
        "status", help="Report fixed catalog status."
    )
    catalog_status_parser.set_defaults(handler=catalog_status)

    health_parser = subparsers.add_parser("health", help="Run read-only health checks.")
    health_parser.set_defaults(handler=health)

    scan = subparsers.add_parser("scan", help="Inventory source inputs.")
    scan_sub = scan.add_subparsers(dest="scan_command")
    scan_folder_parser = scan_sub.add_parser("folder", help="Inventory a folder tree.")
    scan_folder_parser.add_argument("path", help="Folder path to scan.")
    scan_folder_parser.set_defaults(handler=scan_folder)

    parse = subparsers.add_parser("parse", help="Parse source inputs.")
    parse_sub = parse.add_subparsers(dest="parse_command")
    parse_folder_parser = parse_sub.add_parser("folder", help="Parse a folder tree.")
    parse_folder_parser.add_argument("path", help="Folder path to parse.")
    parse_folder_parser.set_defaults(handler=parse_folder)

    index = subparsers.add_parser("index", help="Build or refresh indexes.")
    index_sub = index.add_subparsers(dest="index_command")
    index_folder_parser = index_sub.add_parser("folder", help="Index a folder tree.")
    index_folder_parser.add_argument("path", help="Folder path to index.")
    index_folder_parser.set_defaults(handler=index_folder)

    search = subparsers.add_parser("search", help="Search built indexes.")
    search_sub = search.add_subparsers(dest="search_command")
    search_text_parser = search_sub.add_parser("text", help="Search with a text query.")
    search_text_parser.add_argument("query", help="Search query.")
    search_text_parser.set_defaults(handler=search_text)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.handler is None:
        parser.print_help()
        return 0
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
