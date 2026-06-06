"""Minimal agents-docs command surface.

The first scaffold intentionally uses only the Python standard library so the
binding command shape can be tested before heavy optional dependencies are
installed.
"""

from __future__ import annotations

import argparse
import importlib.util
import logging
import platform
import sys
from pathlib import Path
from typing import Any, TextIO

from agents_cli import __version__
from agents_cli.catalog import catalog_status_report, create_catalog, migrate_catalog
from agents_cli.fts import IndexOptions, SearchOptions, index_folder_to_tantivy, search_text_indexes
from agents_cli.hybrid import HybridSearchOptions, search_hybrid_indexes
from agents_cli.inventory import ScanOptions, scan_folder_to_catalog
from agents_cli.parse import ParseOptions, parse_folder_to_catalog
from agents_cli.paths import catalog_path, fixed_cache_root, reports_root, results_root
from agents_cli.results import CommandRun, render_console_summary
from agents_cli.semantic import (
    SemanticIndexOptions,
    SemanticSearchOptions,
    index_folder_to_lancedb,
    search_semantic_indexes,
)


SCHEMA_VERSION = "0.3"


def _emit(payload: dict[str, Any]) -> None:
    print(render_console_summary(payload))


class _ParseProgress:
    def __init__(self, stream: TextIO, *, enabled: bool) -> None:
        self.stream = stream
        self.enabled = enabled
        self.interactive = bool(getattr(stream, "isatty", lambda: False)())
        self.last_len = 0

    def __call__(self, event: dict[str, Any]) -> None:
        if not self.enabled:
            return
        event_type = event.get("event")
        if event_type == "document_start" and self.interactive:
            self._write_current(
                self._line(
                    event,
                    status="parsing",
                )
            )
        elif event_type == "document_done":
            self._write_done(self._line(event, status=self._status_text(event)))

    def _line(self, event: dict[str, Any], *, status: str) -> str:
        index = event.get("index", "?")
        total = event.get("total", "?")
        path = _shorten(str(event.get("relative_path", "")), 88)
        return f"parse [{index}/{total}] {status}: {path}"

    def _status_text(self, event: dict[str, Any]) -> str:
        status = str(event.get("status", "unknown"))
        if status == "failed":
            return f"failed ({event.get('error_kind', 'unknown')})"
        if event.get("docling_status") == "partial_success":
            return "partial"
        return status

    def _write_current(self, line: str) -> None:
        padded = line.ljust(self.last_len)
        self.stream.write("\r" + padded)
        self.stream.flush()
        self.last_len = len(line)

    def _write_done(self, line: str) -> None:
        if self.interactive:
            padded = line.ljust(self.last_len)
            self.stream.write("\r" + padded + "\n")
            self.last_len = 0
        else:
            self.stream.write(line + "\n")
        self.stream.flush()


def _shorten(value: str, max_length: int) -> str:
    if len(value) <= max_length:
        return value
    return "..." + value[-(max_length - 3) :]


def _configure_parse_logging(*, verbose: bool) -> None:
    if verbose:
        return
    for logger_name in (
        "docling",
        "docling_core",
        "docling_ibm_models",
        "RapidOCR",
        "rapidocr",
    ):
        logging.getLogger(logger_name).setLevel(logging.CRITICAL)


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
                "reports_root_exists": reports_root().exists(),
            },
            "checks": [
                {"name": "fixed_cache_contract", "status": "ok"},
                {"name": "sqlite_stdlib", "status": "ok"},
                {
                    "name": "docling",
                    "status": "ok"
                    if importlib.util.find_spec("docling") is not None
                    else "missing",
                },
                {
                    "name": "tantivy",
                    "status": "ok"
                    if importlib.util.find_spec("tantivy") is not None
                    else "missing",
                },
                {
                    "name": "lancedb",
                    "status": "ok"
                    if importlib.util.find_spec("lancedb") is not None
                    else "missing",
                },
                {
                    "name": "fastembed",
                    "status": "ok"
                    if importlib.util.find_spec("fastembed") is not None
                    else "missing",
                },
            ],
        }
    )
    _emit(payload)
    return 0


def scan_folder(args: argparse.Namespace) -> int:
    run = CommandRun.start("scan folder")
    payload = _base_payload("scan folder")
    try:
        result = scan_folder_to_catalog(
            Path(args.path),
            ScanOptions(
                max_files=args.max_files,
                max_bytes=args.max_bytes,
                max_depth=args.max_depth,
            ),
        )
        payload.update(result)
    except Exception as exc:  # pragma: no cover - final defensive boundary.
        payload.update(
            {
                "status": "failed",
                "error_kind": "unhandled_exception",
                "redacted_detail": exc.__class__.__name__,
            }
        )
    payload = run.finish(payload, write_report=args.report)
    _emit(payload)
    return 0 if payload["status"] == "ok" else 1


def parse_folder(args: argparse.Namespace) -> int:
    _configure_parse_logging(verbose=args.verbose)
    progress_enabled = args.progress
    if progress_enabled is None:
        progress_enabled = sys.stderr.isatty()
    run = CommandRun.start("parse folder")
    payload = _base_payload("parse folder")
    try:
        result = parse_folder_to_catalog(
            Path(args.path),
            ParseOptions(
                profile=args.profile,
                limit=args.limit,
                progress=_ParseProgress(sys.stderr, enabled=bool(progress_enabled)),
                document_timeout=args.document_timeout,
                max_pages=args.max_pages,
                max_file_size=args.max_file_size,
                docling_threads=args.docling_threads,
                queue_size=args.queue_size,
                batch_size=args.batch_size,
                suppress_converter_output=not args.verbose,
            ),
        )
        payload.update(result)
    except Exception as exc:  # pragma: no cover - final defensive boundary.
        payload.update(
            {
                "status": "failed",
                "error_kind": "unhandled_exception",
                "redacted_detail": exc.__class__.__name__,
            }
        )
    payload = run.finish(payload, write_report=args.report)
    _emit(payload)
    return 0 if payload["status"] in {"ok", "partial"} else 1


def index_folder(args: argparse.Namespace) -> int:
    run = CommandRun.start("index folder")
    payload = _base_payload("index folder")
    try:
        if args.semantic:
            result = index_folder_to_lancedb(
                Path(args.path),
                SemanticIndexOptions(force=args.force),
            )
        else:
            result = index_folder_to_tantivy(
                Path(args.path),
                IndexOptions(force=args.force),
            )
        payload.update(result)
    except Exception as exc:  # pragma: no cover - final defensive boundary.
        payload.update(
            {
                "status": "failed",
                "error_kind": "unhandled_exception",
                "redacted_detail": exc.__class__.__name__,
            }
        )
    payload = run.finish(payload)
    _emit(payload)
    return 0 if payload["status"] == "ok" else 1


def search_text(args: argparse.Namespace) -> int:
    run = CommandRun.start("search text")
    payload = _base_payload("search text")
    try:
        result = search_text_indexes(
            args.query,
            SearchOptions(limit=args.limit),
        )
        payload.update(result)
    except Exception as exc:  # pragma: no cover - final defensive boundary.
        payload.update(
            {
                "status": "failed",
                "error_kind": "unhandled_exception",
                "redacted_detail": exc.__class__.__name__,
            }
        )
    payload = run.finish(payload)
    _emit(payload)
    return 0 if payload["status"] in {"ok", "partial"} else 1


def search_semantic(args: argparse.Namespace) -> int:
    run = CommandRun.start("search semantic")
    payload = _base_payload("search semantic")
    try:
        result = search_semantic_indexes(
            args.query,
            SemanticSearchOptions(limit=args.limit),
        )
        payload.update(result)
    except Exception as exc:  # pragma: no cover - final defensive boundary.
        payload.update(
            {
                "status": "failed",
                "error_kind": "unhandled_exception",
                "redacted_detail": exc.__class__.__name__,
            }
        )
    payload = run.finish(payload)
    _emit(payload)
    return 0 if payload["status"] in {"ok", "partial"} else 1


def search_hybrid(args: argparse.Namespace) -> int:
    run = CommandRun.start("search hybrid")
    payload = _base_payload("search hybrid")
    try:
        result = search_hybrid_indexes(
            args.query,
            HybridSearchOptions(
                limit=args.limit,
                candidate_limit=args.candidate_limit,
                rrf_k=args.rrf_k,
                rerank=args.rerank,
                ollama_model=args.ollama_model,
                ollama_url=args.ollama_url,
            ),
        )
        payload.update(result)
    except Exception as exc:  # pragma: no cover - final defensive boundary.
        payload.update(
            {
                "status": "failed",
                "error_kind": "unhandled_exception",
                "redacted_detail": exc.__class__.__name__,
            }
        )
    payload = run.finish(payload)
    _emit(payload)
    return 0 if payload["status"] in {"ok", "partial"} else 1


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
    scan_folder_parser.add_argument(
        "--max-files",
        type=int,
        default=None,
        help="Override the configured file-count safeguard.",
    )
    scan_folder_parser.add_argument(
        "--max-bytes",
        type=int,
        default=None,
        help="Override the configured byte-budget safeguard.",
    )
    scan_folder_parser.add_argument(
        "--max-depth",
        type=int,
        default=None,
        help="Override the configured folder-depth safeguard.",
    )
    scan_folder_parser.add_argument(
        "--report",
        action="store_true",
        help="Write an optional generic HTML report under the fixed reports directory.",
    )
    scan_folder_parser.set_defaults(handler=scan_folder)

    parse = subparsers.add_parser("parse", help="Parse source inputs.")
    parse_sub = parse.add_subparsers(dest="parse_command")
    parse_folder_parser = parse_sub.add_parser("folder", help="Parse a folder tree.")
    parse_folder_parser.add_argument("path", help="Folder path to parse.")
    parse_folder_parser.add_argument(
        "--profile",
        default=None,
        choices=["docling_ocr", "docling_default", "docling_fast_text"],
        help="Parser profile. Defaults to config/parser.yaml parser_profile.",
    )
    parse_folder_parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Parse at most this many current source files.",
    )
    parse_folder_parser.add_argument(
        "--document-timeout",
        type=float,
        default=None,
        help="Override the per-document Docling timeout in seconds.",
    )
    parse_folder_parser.add_argument(
        "--max-pages",
        type=int,
        default=None,
        help="Skip documents above this page count.",
    )
    parse_folder_parser.add_argument(
        "--max-file-size",
        type=int,
        default=None,
        help="Skip documents above this byte size.",
    )
    parse_folder_parser.add_argument(
        "--docling-threads",
        type=int,
        default=None,
        help="Override Docling CPU inference threads.",
    )
    parse_folder_parser.add_argument(
        "--batch-size",
        type=int,
        default=None,
        help="Override Docling PDF OCR/layout/table batch size.",
    )
    parse_folder_parser.add_argument(
        "--queue-size",
        type=int,
        default=None,
        help="Override Docling PDF stage queue size.",
    )
    parse_folder_parser.add_argument(
        "--progress",
        dest="progress",
        action="store_true",
        default=None,
        help="Show document-level parse progress.",
    )
    parse_folder_parser.add_argument(
        "--no-progress",
        dest="progress",
        action="store_false",
        help="Suppress document-level parse progress.",
    )
    parse_folder_parser.add_argument(
        "--verbose",
        action="store_true",
        help="Keep verbose third-party parser logs.",
    )
    parse_folder_parser.add_argument(
        "--report",
        action="store_true",
        help="Write an optional generic HTML report under the fixed reports directory.",
    )
    parse_folder_parser.set_defaults(handler=parse_folder)

    index = subparsers.add_parser("index", help="Build or refresh indexes.")
    index_sub = index.add_subparsers(dest="index_command")
    index_folder_parser = index_sub.add_parser("folder", help="Index a folder tree.")
    index_folder_parser.add_argument("path", help="Folder path to index.")
    index_folder_parser.add_argument(
        "--force",
        action="store_true",
        help="Force a rebuild even when the indexed source watermark is current.",
    )
    index_folder_parser.add_argument(
        "--semantic",
        action="store_true",
        help="Build the LanceDB semantic store instead of the default FTS index.",
    )
    index_folder_parser.set_defaults(handler=index_folder)

    search = subparsers.add_parser("search", help="Search built indexes.")
    search_sub = search.add_subparsers(dest="search_command")
    search_text_parser = search_sub.add_parser("text", help="Search with a text query.")
    search_text_parser.add_argument("query", help="Search query.")
    search_text_parser.add_argument(
        "--limit",
        type=int,
        default=30,
        help="Maximum number of FTS hits to return. Defaults to 30.",
    )
    search_text_parser.set_defaults(handler=search_text)

    search_semantic_parser = search_sub.add_parser(
        "semantic", help="Search semantic LanceDB stores with a text query."
    )
    search_semantic_parser.add_argument("query", help="Search query.")
    search_semantic_parser.add_argument(
        "--limit",
        type=int,
        default=30,
        help="Maximum number of semantic hits to return. Defaults to 30.",
    )
    search_semantic_parser.set_defaults(handler=search_semantic)

    search_hybrid_parser = search_sub.add_parser(
        "hybrid", help="Search FTS and semantic stores with RRF fusion."
    )
    search_hybrid_parser.add_argument("query", help="Search query.")
    search_hybrid_parser.add_argument(
        "--limit",
        type=int,
        default=30,
        help="Maximum number of hybrid hits to return. Defaults to 30.",
    )
    search_hybrid_parser.add_argument(
        "--candidate-limit",
        type=int,
        default=60,
        help="Maximum candidates to collect from each backend before fusion. Defaults to 60.",
    )
    search_hybrid_parser.add_argument(
        "--rrf-k",
        type=int,
        default=60,
        help="Reciprocal Rank Fusion k constant.",
    )
    search_hybrid_parser.add_argument(
        "--rerank",
        choices=["none", "ollama"],
        default="none",
        help="Optional local reranker. Defaults to no reranker.",
    )
    search_hybrid_parser.add_argument(
        "--ollama-model",
        default=None,
        help="Local Ollama model used only when --rerank ollama is set.",
    )
    search_hybrid_parser.add_argument(
        "--ollama-url",
        default="http://localhost:11434",
        help="Local Ollama base URL used only when --rerank ollama is set.",
    )
    search_hybrid_parser.set_defaults(handler=search_hybrid)

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
