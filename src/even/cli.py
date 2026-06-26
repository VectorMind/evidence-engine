"""Minimal even command surface.

The first scaffold intentionally uses only the Python standard library so the
binding command shape can be tested before heavy optional dependencies are
installed.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import logging
import platform
import sys
from pathlib import Path
from typing import Any, TextIO

from even import __version__
from even.catalog import catalog_status_report, create_catalog, wipe_catalog
from even.fts import IndexOptions, SearchOptions, index_scope_to_fts, search_text_indexes
from even.hybrid import HybridSearchOptions, search_hybrid_indexes
from even.image_index import (
    ImageIndexOptions,
    ImageSearchOptions,
    index_scope_to_image,
    search_image_stores,
)
from even.inventory import ScanOptions, scan_folder_to_catalog
from even.media import (
    DedupeOptions,
    DescribeOptions,
    InspectOptions,
    dedupe_folder_to_catalog,
    describe_folder_to_catalog,
    inspect_folder_to_catalog,
)
from even.parse import ParseOptions, parse_folder_to_catalog
from even.paths import catalog_path, reports_root, results_root, workspace_root
from even.references import attach_hit_refs
from even.results import CommandRun
from even.routing import RoutingIndexOptions, index_routing, list_representatives
from even.semantic import (
    SemanticIndexOptions,
    SemanticSearchOptions,
    index_scope_to_semantic,
    search_semantic_indexes,
)


SCHEMA_VERSION = "0.4"


def _emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


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
        "workspace_root": str(workspace_root()),
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
    return 0 if payload["status"] in {"created", "current"} else 1


def catalog_status(_: argparse.Namespace) -> int:
    payload = _base_payload("catalog status")
    payload.update(catalog_status_report())
    _emit(payload)
    return 0 if payload["status"] in {"current", "missing", "stale"} else 1


def catalog_wipe(_: argparse.Namespace) -> int:
    payload = _base_payload("catalog wipe")
    payload.update(wipe_catalog())
    _emit(payload)
    return 0


def health(_: argparse.Namespace) -> int:
    payload = _base_payload("health")
    payload.update(
        {
            "status": "ok",
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "paths": {
                "workspace_root_exists": workspace_root().exists(),
                "catalog_exists": catalog_path().exists(),
                "results_root_exists": results_root().exists(),
                "reports_root_exists": reports_root().exists(),
            },
            "checks": [
                {"name": "workspace_storage_contract", "status": "ok"},
                {"name": "sqlite_stdlib", "status": "ok"},
                {
                    "name": "docling",
                    "status": "ok"
                    if importlib.util.find_spec("docling") is not None
                    else "missing",
                },
                {
                    "name": "fts",
                    "status": "ok"
                    if importlib.util.find_spec("tantivy") is not None
                    else "missing",
                },
                {
                    "name": "semantic_store",
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


def sources_scan(args: argparse.Namespace) -> int:
    run = CommandRun.start("sources scan")
    payload = _base_payload("sources scan")
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


def docs_parse(args: argparse.Namespace) -> int:
    _configure_parse_logging(verbose=args.verbose)
    progress_enabled = args.progress
    if progress_enabled is None:
        progress_enabled = sys.stderr.isatty()
    run = CommandRun.start("docs parse")
    payload = _base_payload("docs parse")
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


def media_inspect(args: argparse.Namespace) -> int:
    run = CommandRun.start("media inspect")
    payload = _base_payload("media inspect")
    try:
        result = inspect_folder_to_catalog(
            Path(args.path),
            InspectOptions(limit=args.limit, thumbnails=not args.no_thumbnails),
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


def media_describe(args: argparse.Namespace) -> int:
    run = CommandRun.start("media describe")
    payload = _base_payload("media describe")
    try:
        result = describe_folder_to_catalog(
            Path(args.path),
            DescribeOptions(
                limit=args.limit,
                model=args.model,
                ollama_url=args.ollama_url,
                classify_kind=args.kind,
                max_edge=args.max_edge,
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


def media_dedupe(args: argparse.Namespace) -> int:
    run = CommandRun.start("media dedupe")
    payload = _base_payload("media dedupe")
    try:
        result = dedupe_folder_to_catalog(
            Path(args.path),
            DedupeOptions(
                limit=args.limit,
                max_distance=args.max_distance,
                method=args.method,
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


def index_scope(args: argparse.Namespace) -> int:
    run = CommandRun.start("index scope")
    payload = _base_payload("index scope")
    try:
        if args.image:
            result = index_scope_to_image(
                Path(args.path),
                ImageIndexOptions(force=args.force, limit=args.limit),
            )
        elif args.semantic:
            result = index_scope_to_semantic(
                Path(args.path),
                SemanticIndexOptions(force=args.force),
            )
        else:
            result = index_scope_to_fts(
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


def index_routing_command(args: argparse.Namespace) -> int:
    run = CommandRun.start("index routing")
    payload = _base_payload("index routing")
    try:
        result = index_routing(
            Path(args.path),
            RoutingIndexOptions(
                force=args.force,
                limit=args.limit,
                summary_model=args.summary_model,
                summary_ollama_url=args.summary_ollama_url,
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
    return 0 if payload["status"] == "ok" else 1


def search_text(args: argparse.Namespace) -> int:
    run = CommandRun.start("search text")
    payload = _base_payload("search text")
    try:
        result = search_text_indexes(
            args.query,
            SearchOptions(limit=args.limit, budget=args.budget),
        )
        payload.update(result)
        attach_hit_refs(payload)
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


def list_representatives_command(args: argparse.Namespace) -> int:
    run = CommandRun.start("list")
    payload = _base_payload("list")
    try:
        result = list_representatives(Path(args.path) if args.path else None)
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


def search_semantic(args: argparse.Namespace) -> int:
    run = CommandRun.start("search semantic")
    payload = _base_payload("search semantic")
    try:
        result = search_semantic_indexes(
            args.query,
            SemanticSearchOptions(limit=args.limit),
        )
        payload.update(result)
        attach_hit_refs(payload)
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
        attach_hit_refs(payload)
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


def search_image(args: argparse.Namespace) -> int:
    run = CommandRun.start("search image")
    payload = _base_payload("search image")
    try:
        if not args.image_path and not args.text:
            payload.update(
                {
                    "status": "failed",
                    "error_kind": "missing_query",
                    "message": "Provide an image path or --text.",
                }
            )
        else:
            result = search_image_stores(
                args.image_path,
                ImageSearchOptions(limit=args.limit, text=args.text),
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
        prog="even",
        description="Local evidence engine for documents and generic media.",
    )
    parser.set_defaults(handler=None)
    subparsers = parser.add_subparsers(dest="command")

    catalog = subparsers.add_parser("catalog", help="Catalog control commands.")
    catalog_sub = catalog.add_subparsers(dest="catalog_command")

    catalog_create_parser = catalog_sub.add_parser(
        "create", help="Create the workspace catalog if it is missing."
    )
    catalog_create_parser.set_defaults(handler=catalog_create)

    catalog_status_parser = catalog_sub.add_parser(
        "status", help="Report workspace catalog status."
    )
    catalog_status_parser.set_defaults(handler=catalog_status)

    catalog_wipe_parser = catalog_sub.add_parser(
        "wipe", help="Delete the workspace catalog database."
    )
    catalog_wipe_parser.set_defaults(handler=catalog_wipe)

    health_parser = subparsers.add_parser("health", help="Run read-only health checks.")
    health_parser.set_defaults(handler=health)

    sources = subparsers.add_parser("sources", help="Inventory source inputs.")
    sources_sub = sources.add_subparsers(dest="sources_command")
    sources_scan_parser = sources_sub.add_parser("scan", help="Inventory a folder tree.")
    sources_scan_parser.add_argument("path", help="Folder path to scan.")
    sources_scan_parser.add_argument(
        "--max-files",
        type=int,
        default=None,
        help="Override the configured file-count safeguard.",
    )
    sources_scan_parser.add_argument(
        "--max-bytes",
        type=int,
        default=None,
        help="Override the configured byte-budget safeguard.",
    )
    sources_scan_parser.add_argument(
        "--max-depth",
        type=int,
        default=None,
        help="Override the configured folder-depth safeguard.",
    )
    sources_scan_parser.add_argument(
        "--report",
        action="store_true",
        help="Write an optional generic HTML report under the workspace reports directory.",
    )
    sources_scan_parser.set_defaults(handler=sources_scan)

    docs = subparsers.add_parser("docs", help="Document evidence commands.")
    docs_sub = docs.add_subparsers(dest="docs_command")
    docs_parse_parser = docs_sub.add_parser("parse", help="Parse a folder tree.")
    docs_parse_parser.add_argument("path", help="Folder path to parse.")
    docs_parse_parser.add_argument(
        "--profile",
        default=None,
        choices=["docling_ocr", "docling_default", "docling_fast_text"],
        help="Parser profile. Defaults to config/parser.yaml parser_profile.",
    )
    docs_parse_parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Parse at most this many current source files.",
    )
    docs_parse_parser.add_argument(
        "--document-timeout",
        type=float,
        default=None,
        help="Override the per-document Docling timeout in seconds.",
    )
    docs_parse_parser.add_argument(
        "--max-pages",
        type=int,
        default=None,
        help="Skip documents above this page count.",
    )
    docs_parse_parser.add_argument(
        "--max-file-size",
        type=int,
        default=None,
        help="Skip documents above this byte size.",
    )
    docs_parse_parser.add_argument(
        "--docling-threads",
        type=int,
        default=None,
        help="Override Docling CPU inference threads.",
    )
    docs_parse_parser.add_argument(
        "--batch-size",
        type=int,
        default=None,
        help="Override Docling PDF OCR/layout/table batch size.",
    )
    docs_parse_parser.add_argument(
        "--queue-size",
        type=int,
        default=None,
        help="Override Docling PDF stage queue size.",
    )
    docs_parse_parser.add_argument(
        "--progress",
        dest="progress",
        action="store_true",
        default=None,
        help="Show document-level parse progress.",
    )
    docs_parse_parser.add_argument(
        "--no-progress",
        dest="progress",
        action="store_false",
        help="Suppress document-level parse progress.",
    )
    docs_parse_parser.add_argument(
        "--verbose",
        action="store_true",
        help="Keep verbose third-party parser logs.",
    )
    docs_parse_parser.add_argument(
        "--report",
        action="store_true",
        help="Write an optional generic HTML report under the workspace reports directory.",
    )
    docs_parse_parser.set_defaults(handler=docs_parse)

    media = subparsers.add_parser("media", help="Media evidence commands.")
    media_sub = media.add_subparsers(dest="media_command")
    media_inspect_parser = media_sub.add_parser(
        "inspect", help="Extract deterministic media metadata for a folder."
    )
    media_inspect_parser.add_argument("path", help="Folder path to inspect.")
    media_inspect_parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Inspect at most this many current image source items.",
    )
    media_inspect_parser.add_argument(
        "--no-thumbnails",
        action="store_true",
        help="Skip thumbnail generation and store only metadata rows.",
    )
    media_inspect_parser.set_defaults(handler=media_inspect)

    media_describe_parser = media_sub.add_parser(
        "describe", help="Generate shallow VLM captions for images (opt-in)."
    )
    media_describe_parser.add_argument("path", help="Folder path to describe.")
    media_describe_parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Describe at most this many current image source items.",
    )
    media_describe_parser.add_argument(
        "--model",
        default="granite3.2-vision",
        help="Local Ollama vision model. Defaults to granite3.2-vision.",
    )
    media_describe_parser.add_argument(
        "--ollama-url",
        default="http://localhost:11434",
        help="Local Ollama base URL. Defaults to http://localhost:11434.",
    )
    media_describe_parser.add_argument(
        "--kind",
        action="store_true",
        help="Also classify each image into the closed media-kind vocabulary.",
    )
    media_describe_parser.add_argument(
        "--max-edge",
        type=int,
        default=1024,
        help="Downscale the longest image edge before the VLM call. 0 disables.",
    )
    media_describe_parser.set_defaults(handler=media_describe)

    media_dedupe_parser = media_sub.add_parser(
        "dedupe", help="Find near-duplicate image candidates via perceptual hashing."
    )
    media_dedupe_parser.add_argument("path", help="Folder path to dedupe.")
    media_dedupe_parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Hash at most this many current image source items.",
    )
    media_dedupe_parser.add_argument(
        "--max-distance",
        type=int,
        default=5,
        help="Max Hamming distance for a candidate pair. Defaults to 5.",
    )
    media_dedupe_parser.add_argument(
        "--method",
        default="phash",
        choices=["phash", "dhash", "ahash"],
        help="Perceptual hash method. Defaults to phash.",
    )
    media_dedupe_parser.set_defaults(handler=media_dedupe)

    index = subparsers.add_parser("index", help="Build or refresh indexes.")
    index_sub = index.add_subparsers(dest="index_command")
    index_scope_parser = index_sub.add_parser("scope", help="Index a source scope.")
    index_scope_parser.add_argument("path", help="Folder path or scope path to index.")
    index_scope_parser.add_argument(
        "--force",
        action="store_true",
        help="Force a rebuild even when the indexed source watermark is current.",
    )
    index_scope_parser.add_argument(
        "--semantic",
        action="store_true",
        help="Build the semantic store instead of the default text index.",
    )
    index_scope_parser.add_argument(
        "--image",
        action="store_true",
        help="Build the image-embedding store for media images (needs image-search extra).",
    )
    index_scope_parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="With --image, embed at most this many image assets.",
    )
    index_scope_parser.set_defaults(handler=index_scope)

    index_routing_parser = index_sub.add_parser(
        "routing",
        help="Build or refresh global representative routing indexes.",
    )
    index_routing_parser.add_argument("path", help="Folder path to summarize.")
    index_routing_parser.add_argument(
        "--force",
        action="store_true",
        help="Force summary and representative index rebuild.",
    )
    index_routing_parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum document chunks sampled into the summary prompt.",
    )
    index_routing_parser.add_argument(
        "--summary-model",
        default=None,
        help="Local Ollama model for lossy routing summaries.",
    )
    index_routing_parser.add_argument(
        "--summary-ollama-url",
        default=None,
        help="Local Ollama base URL for routing summaries.",
    )
    index_routing_parser.set_defaults(handler=index_routing_command)

    list_parser = subparsers.add_parser(
        "list", help="List the representative summary-node hierarchy (no query)."
    )
    list_parser.add_argument(
        "path",
        nargs="?",
        default=None,
        help="Optional path filter; lists only roots whose source URI contains it.",
    )
    list_parser.set_defaults(handler=list_representatives_command)

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
    search_text_parser.add_argument(
        "--budget",
        choices=["low", "mid", "high"],
        default="mid",
        help="Query-time fanout budget: low (1 scope), mid (top scopes), high (wider). Defaults to mid.",
    )
    search_text_parser.set_defaults(handler=search_text)

    search_semantic_parser = search_sub.add_parser(
        "semantic", help="Search semantic stores with a text query."
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

    search_image_parser = search_sub.add_parser(
        "image", help="Find visually similar images by example image or text."
    )
    search_image_parser.add_argument(
        "image_path",
        nargs="?",
        default=None,
        help="Query image path. Omit when using --text.",
    )
    search_image_parser.add_argument(
        "--text",
        default=None,
        help="Text query for text->image search instead of an example image.",
    )
    search_image_parser.add_argument(
        "--limit",
        type=int,
        default=30,
        help="Maximum number of image hits to return. Defaults to 30.",
    )
    search_image_parser.set_defaults(handler=search_image)

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
