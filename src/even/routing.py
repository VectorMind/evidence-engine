"""Global representative routing for text search.

D0 builds document-only root summaries, projects them into a fixed global FTS
map, and uses that map to choose root-scoped FTS indexes before deep search.
The summary nodes are routing hints only; final evidence still comes from the
root-scoped indexes.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from even.catalog import ensure_catalog
from even.chunks import chunks_for_root, high_watermark, stable_id
from even.config import load_parser_config, load_routing_config
from even.inventory import ScanOptions, scan_folder_to_catalog
from even.paths import catalog_path, workspace_root


GLOBAL_FTS_TEMPLATE = "fts_summary_node"
GLOBAL_FTS_MANIFEST = "manifest.json"
PROMPT_VERSION = "summary_prompt_v1"


@dataclass(frozen=True)
class RoutingIndexOptions:
    force: bool = False
    limit: int | None = None
    summary_model: str | None = None
    summary_ollama_url: str | None = None


class SummaryGenerationError(Exception):
    def __init__(self, status: str, error_kind: str, message: str = "") -> None:
        super().__init__(message or error_kind)
        self.status = status
        self.error_kind = error_kind
        self.message = message or error_kind


SummaryGenerator = Callable[..., str]


def index_routing(
    path: Path,
    options: RoutingIndexOptions,
    *,
    summary_generator: SummaryGenerator | None = None,
) -> dict[str, Any]:
    """Build document-only summary nodes and the global representative FTS map."""

    runtime = _tantivy_runtime_status()
    if runtime["status"] != "ok":
        return runtime

    ensure_report = ensure_catalog()
    if ensure_report["status"] not in {"created", "current"}:
        return {
            "status": "failed",
            "error_kind": "catalog_unavailable",
            "catalog_status": ensure_report["status"],
        }

    scan_result = scan_folder_to_catalog(
        path,
        ScanOptions(max_files=None, max_bytes=None, max_depth=None),
    )
    if scan_result["status"] != "ok":
        return {
            "status": scan_result["status"],
            "error_kind": "auto_scan_failed",
            "auto_scan_status": scan_result["status"],
            "scan_result": scan_result,
        }

    summary = _upsert_root_summary(
        root_id=scan_result["root_id"],
        root_label=str(scan_result.get("root_label") or ""),
        scope_id=scan_result["scope_id"],
        options=options,
        summary_generator=summary_generator or _generate_summary_text,
    )
    if summary["status"] != "ok":
        return {
            "status": summary["status"],
            "error_kind": summary.get("error_kind"),
            "index_backend": "routing",
            "root_id": scan_result["root_id"],
            "root_label": scan_result.get("root_label"),
            "scope_id": scan_result["scope_id"],
            "summary_id": summary["summary_id"],
            "summary_status": summary["summary_status"],
            "auto_scan_status": scan_result["status"],
            "counts": summary["counts"],
            "message": summary.get("message", ""),
        }

    config = _routing_defaults()
    fts_profile = _fts_profile()
    projection = build_global_representative_fts(
        fts_profile=fts_profile,
        force=options.force,
    )
    if projection["status"] != "ok":
        return {
            "status": "failed",
            "error_kind": projection.get("error_kind", "global_fts_build_failed"),
            "index_backend": "routing",
            "root_id": scan_result["root_id"],
            "root_label": scan_result.get("root_label"),
            "scope_id": scan_result["scope_id"],
            "summary_id": summary["summary_id"],
            "summary_status": summary["summary_status"],
            "auto_scan_status": scan_result["status"],
            "summary": summary,
            "global_representative_fts": projection,
            "counts": summary["counts"],
        }

    counts = dict(summary["counts"])
    counts.update(
        {
            "summary_nodes_indexed": projection["counts"]["summary_nodes_indexed"],
            "summary_nodes_unchanged": projection["counts"].get(
                "summary_nodes_unchanged", 0
            ),
            "representative_top_k": int(config["representative_top_k"]),
            "max_routed_scopes": int(config["max_routed_scopes"]),
        }
    )
    return {
        "status": "ok",
        "index_backend": "routing",
        "root_id": scan_result["root_id"],
        "root_label": scan_result.get("root_label"),
        "scope_id": scan_result["scope_id"],
        "summary_id": summary["summary_id"],
        "summary_status": summary["summary_status"],
        "summary_index_status": summary["index_status"],
        "global_representative_fts": projection,
        "auto_scan_status": scan_result["status"],
        "counts": counts,
    }


def build_global_representative_fts(
    *,
    fts_profile: str | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Build the fixed-path global FTS projection from current summary nodes."""

    runtime = _tantivy_runtime_status()
    if runtime["status"] != "ok":
        return runtime

    profile = fts_profile or _fts_profile()
    rows = _current_text_summary_rows()
    index_uri = _global_fts_uri(profile)
    index_dir = workspace_root() / index_uri
    manifest_path = index_dir / GLOBAL_FTS_MANIFEST
    watermark = _representative_watermark(rows, profile)

    if not rows:
        return {
            "status": "deferred",
            "error_kind": "no_current_summary_nodes",
            "index_uri": index_uri,
            "template_name": GLOBAL_FTS_TEMPLATE,
            "counts": {"summary_nodes_planned": 0, "summary_nodes_indexed": 0},
        }

    if (
        not force
        and _manifest_current(manifest_path, watermark, profile)
        and _tantivy_index_exists(index_dir)
    ):
        return {
            "status": "ok",
            "index_backend": "routing",
            "index_status": "current",
            "index_uri": index_uri,
            "template_name": GLOBAL_FTS_TEMPLATE,
            "source_high_watermark": watermark,
            "counts": {
                "summary_nodes_planned": len(rows),
                "summary_nodes_indexed": 0,
                "summary_nodes_unchanged": len(rows),
            },
        }

    build = _write_global_fts_index(index_dir, rows)
    if build["status"] != "ok":
        return {
            "status": "failed",
            "error_kind": build["error_kind"],
            "index_uri": index_uri,
            "template_name": GLOBAL_FTS_TEMPLATE,
            "redacted_detail": build.get("redacted_detail"),
            "counts": {
                "summary_nodes_planned": len(rows),
                "summary_nodes_indexed": 0,
            },
        }

    _write_manifest(
        manifest_path=manifest_path,
        fts_profile=profile,
        source_high_watermark=watermark,
        row_count=len(rows),
    )
    return {
        "status": "ok",
        "index_backend": "routing",
        "index_status": "rebuilt" if force else "refreshed",
        "index_uri": index_uri,
        "template_name": GLOBAL_FTS_TEMPLATE,
        "source_high_watermark": watermark,
        "counts": {
            "summary_nodes_planned": len(rows),
            "summary_nodes_indexed": len(rows),
            "summary_nodes_unchanged": 0,
        },
    }


def search_text_with_routing(query: str, options: Any) -> dict[str, Any]:
    """Route text search through global representatives when they are current."""

    from even import fts

    config = _routing_defaults()
    route = _search_global_representatives(
        query,
        fts_profile=_fts_profile(),
        limit=int(config["representative_top_k"]),
    )
    if route["status"] != "ok":
        fallback = fts.search_all_text_indexes(query, options)
        fallback["route_trace"] = _fallback_trace(route.get("reasons", []))
        return fallback

    selected_scopes = _selected_scopes(
        route["hits"],
        max_scopes=int(config["max_routed_scopes"]),
    )
    if not selected_scopes:
        fallback = fts.search_all_text_indexes(query, options)
        fallback["route_trace"] = _fallback_trace(["no_representative_scopes"])
        return fallback

    scoped = fts.search_all_text_indexes(
        query,
        options,
        scope_ids=[scope["scope_id"] for scope in selected_scopes],
    )
    weak_reasons = _weak_route_reasons(
        representative_hits=route["hits"],
        deep_hits=scoped.get("hits", []),
        config=config,
    )
    if weak_reasons:
        fallback = fts.search_all_text_indexes(query, options)
        fallback["route_trace"] = _route_trace(
            route=route,
            selected_scopes=selected_scopes,
            deep_result=scoped,
            status="fallback_all_scopes",
            widening_status={
                "status": "fallback_all_scopes",
                "reasons": weak_reasons,
                "skipped_rungs": [],
            },
        )
        return fallback

    scoped["route_trace"] = _route_trace(
        route=route,
        selected_scopes=selected_scopes,
        deep_result=scoped,
        status="used",
        widening_status={"status": "not_needed", "reasons": [], "skipped_rungs": []},
    )
    return scoped


def _upsert_root_summary(
    *,
    root_id: str,
    root_label: str,
    scope_id: str,
    options: RoutingIndexOptions,
    summary_generator: SummaryGenerator,
) -> dict[str, Any]:
    config = _routing_defaults()
    sample_policy = str(config["sample_policy"])
    model = (
        options.summary_model
        or os.environ.get("EVEN_SUMMARY_MODEL")
        or str(config["summary_model"])
    )
    url = (
        options.summary_ollama_url
        or os.environ.get("EVEN_SUMMARY_OLLAMA_URL")
        or str(config["summary_ollama_url"])
    )
    timeout = float(config["summary_timeout_seconds"])
    max_chunks = int(options.limit or config["summary_sample_chunks_default"])
    chunk_profile = _chunk_profile()
    chunks = chunks_for_root(root_id=root_id, scope_id=scope_id, chunk_profile=chunk_profile)
    summary_id = _summary_id(scope_id)
    now = _iso(_utc_now())
    state = _summary_state(summary_id)

    if not chunks:
        _upsert_summary_row(
            summary_id=summary_id,
            root_id=root_id,
            scope_id=scope_id,
            source_item_id=_root_source_item_id(root_id),
            title=root_label or scope_id,
            summary_text="",
            routing_text="",
            source_refs=[],
            source_count=0,
            sample_count=0,
            coverage_estimate=0.0,
            sample_policy=sample_policy,
            producer="none",
            profile=chunk_profile,
            watermark=_empty_watermark(root_id, scope_id, sample_policy),
            status="deferred",
            attrs={"error_kind": "no_summary_inputs"},
            now=now,
            created_at=state.get("created_at") if state else None,
        )
        return {
            "status": "deferred",
            "error_kind": "no_summary_inputs",
            "message": "No parsed document chunks were available for routing.",
            "summary_id": summary_id,
            "summary_status": "deferred",
            "index_status": "deferred",
            "counts": {
                "chunks_considered": 0,
                "chunks_sampled": 0,
                "summary_nodes_written": 1,
            },
        }

    watermark = high_watermark(
        chunks,
        sample_policy,
        model,
        str(max_chunks),
        PROMPT_VERSION,
    )
    if (
        not options.force
        and state
        and state.get("summary_status") == "current"
        and state.get("source_high_watermark") == watermark
    ):
        return {
            "status": "ok",
            "summary_id": summary_id,
            "summary_status": "current",
            "index_status": "current",
            "counts": {
                "chunks_considered": len(chunks),
                "chunks_sampled": 0,
                "summary_nodes_written": 0,
            },
        }

    samples = _sample_chunks(chunks, max_chunks=max_chunks)
    prompt = _summary_prompt(
        root_label=root_label,
        samples=samples,
        max_chars=int(config["summary_prompt_max_chars"]),
        per_chunk_chars=int(config["summary_sample_chars_per_chunk"]),
    )
    try:
        summary_text = summary_generator(prompt, model=model, url=url, timeout=timeout)
    except SummaryGenerationError as exc:
        _upsert_summary_row(
            summary_id=summary_id,
            root_id=root_id,
            scope_id=scope_id,
            source_item_id=_root_source_item_id(root_id),
            title=root_label or scope_id,
            summary_text="",
            routing_text=_deterministic_routing_text(root_label, samples, ""),
            source_refs=_source_refs(samples),
            source_count=len(chunks),
            sample_count=len(samples),
            coverage_estimate=_coverage(len(samples), len(chunks)),
            sample_policy=sample_policy,
            producer=f"ollama:{model}",
            profile=chunk_profile,
            watermark=watermark,
            status=exc.status,
            attrs={"error_kind": exc.error_kind, "message": exc.message},
            now=now,
            created_at=state.get("created_at") if state else None,
        )
        return {
            "status": exc.status,
            "error_kind": exc.error_kind,
            "message": exc.message,
            "summary_id": summary_id,
            "summary_status": exc.status,
            "index_status": exc.status,
            "counts": {
                "chunks_considered": len(chunks),
                "chunks_sampled": len(samples),
                "summary_nodes_written": 1,
            },
        }

    summary_text = " ".join(str(summary_text or "").split())
    if not summary_text:
        _upsert_summary_row(
            summary_id=summary_id,
            root_id=root_id,
            scope_id=scope_id,
            source_item_id=_root_source_item_id(root_id),
            title=root_label or scope_id,
            summary_text="",
            routing_text=_deterministic_routing_text(root_label, samples, ""),
            source_refs=_source_refs(samples),
            source_count=len(chunks),
            sample_count=len(samples),
            coverage_estimate=_coverage(len(samples), len(chunks)),
            sample_policy=sample_policy,
            producer=f"ollama:{model}",
            profile=chunk_profile,
            watermark=watermark,
            status="failed",
            attrs={"error_kind": "empty_summary"},
            now=now,
            created_at=state.get("created_at") if state else None,
        )
        return {
            "status": "failed",
            "error_kind": "empty_summary",
            "message": "The local summary model returned no text.",
            "summary_id": summary_id,
            "summary_status": "failed",
            "index_status": "failed",
            "counts": {
                "chunks_considered": len(chunks),
                "chunks_sampled": len(samples),
                "summary_nodes_written": 1,
            },
        }

    _upsert_summary_row(
        summary_id=summary_id,
        root_id=root_id,
        scope_id=scope_id,
        source_item_id=_root_source_item_id(root_id),
        title=root_label or scope_id,
        summary_text=summary_text,
        routing_text=_deterministic_routing_text(root_label, samples, summary_text),
        source_refs=_source_refs(samples),
        source_count=len(chunks),
        sample_count=len(samples),
        coverage_estimate=_coverage(len(samples), len(chunks)),
        sample_policy=sample_policy,
        producer=f"ollama:{model}",
        profile=chunk_profile,
        watermark=watermark,
        status="current",
        attrs={"prompt_version": PROMPT_VERSION, "model": model, "ollama_url": url},
        now=now,
        created_at=state.get("created_at") if state else None,
    )
    return {
        "status": "ok",
        "summary_id": summary_id,
        "summary_status": "current",
        "index_status": "rebuilt" if options.force else "refreshed",
        "counts": {
            "chunks_considered": len(chunks),
            "chunks_sampled": len(samples),
            "summary_nodes_written": 1,
        },
    }


def _generate_summary_text(
    prompt: str,
    *,
    model: str,
    url: str,
    timeout: float,
) -> str:
    endpoint = _local_ollama_generate_url(url)
    payload = {
        "model": model,
        "stream": False,
        "options": {"temperature": 0},
        "prompt": prompt,
    }
    try:
        request = Request(
            endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=timeout) as response:  # noqa: S310 local-only
            body = json.loads(response.read().decode("utf-8"))
    except SummaryGenerationError:
        raise
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        raise SummaryGenerationError(
            "deferred",
            "ollama_unreachable",
            exc.__class__.__name__,
        ) from exc
    except json.JSONDecodeError as exc:
        raise SummaryGenerationError(
            "failed",
            "ollama_response_parse_failed",
            exc.__class__.__name__,
        ) from exc
    return str(body.get("response", "")).strip()


def _local_ollama_generate_url(base_url: str) -> str:
    normalized = base_url if "://" in base_url else f"http://{base_url}"
    parsed = urlparse(normalized)
    host = parsed.hostname or ""
    if host.lower() not in {"localhost", "127.0.0.1", "::1"}:
        raise SummaryGenerationError(
            "failed",
            "nonlocal_summary_endpoint",
            "Summary generation only accepts localhost Ollama endpoints.",
        )
    if parsed.scheme not in {"http", "https"}:
        raise SummaryGenerationError(
            "failed",
            "unsupported_summary_endpoint_scheme",
            "Summary generation expects an HTTP localhost endpoint.",
        )
    url = normalized.rstrip("/")
    if not url.endswith("/api/generate"):
        url = f"{url}/api/generate"
    return url


def _write_global_fts_index(
    index_dir: Path,
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    try:
        import tantivy  # type: ignore[import-not-found]

        index_dir.mkdir(parents=True, exist_ok=True)
        index = tantivy.Index(_global_fts_schema(), path=str(index_dir), reuse=True)
        writer = index.writer(heap_size=50_000_000)
        writer.delete_all_documents()
        for row in rows:
            document = tantivy.Document()
            for field in (
                "summary_id",
                "root_id",
                "scope_id",
                "kind",
                "modality",
                "title",
                "summary_text",
                "routing_text",
                "source_refs_json",
                "metadata_json",
            ):
                document.add_text(field, str(row.get(field) or ""))
            writer.add_document(document)
        writer.commit()
        index.reload()
    except Exception as exc:  # noqa: BLE001 - backend boundary.
        return {
            "status": "failed",
            "error_kind": "global_fts_write_failed",
            "redacted_detail": exc.__class__.__name__,
        }
    return {"status": "ok"}


def _global_fts_schema() -> Any:
    import tantivy  # type: ignore[import-not-found]

    builder = tantivy.SchemaBuilder()
    for field in ("summary_id", "root_id", "scope_id", "kind", "modality"):
        builder.add_text_field(
            field,
            stored=True,
            tokenizer_name="raw",
            index_option="basic",
        )
    builder.add_text_field("title", stored=True, tokenizer_name="default")
    builder.add_text_field("summary_text", stored=True, tokenizer_name="default")
    builder.add_text_field("routing_text", stored=True, tokenizer_name="default")
    builder.add_text_field(
        "source_refs_json",
        stored=True,
        tokenizer_name="raw",
        index_option="basic",
    )
    builder.add_text_field(
        "metadata_json",
        stored=True,
        tokenizer_name="raw",
        index_option="basic",
    )
    return builder.build()


def _search_global_representatives(
    query: str,
    *,
    fts_profile: str,
    limit: int,
) -> dict[str, Any]:
    runtime = _tantivy_runtime_status()
    if runtime["status"] != "ok":
        return {"status": "unavailable", "reasons": [runtime["error_kind"]]}

    try:
        rows = _current_text_summary_rows()
    except sqlite3.Error:
        return {"status": "unavailable", "reasons": ["summary_nodes_unavailable"]}

    if not rows:
        return {"status": "unavailable", "reasons": ["no_current_summary_nodes"]}

    index_uri = _global_fts_uri(fts_profile)
    index_dir = workspace_root() / index_uri
    manifest_path = index_dir / GLOBAL_FTS_MANIFEST
    watermark = _representative_watermark(rows, fts_profile)
    if not _manifest_current(manifest_path, watermark, fts_profile):
        return {
            "status": "unavailable",
            "reasons": ["global_representative_index_stale"],
            "representative_index_uri": index_uri,
        }
    if not _tantivy_index_exists(index_dir):
        return {
            "status": "unavailable",
            "reasons": ["global_representative_index_missing"],
            "representative_index_uri": index_uri,
        }

    try:
        import tantivy  # type: ignore[import-not-found]

        index = tantivy.Index.open(str(index_dir))
        parsed, errors = index.parse_query_lenient(
            query,
            default_field_names=["title", "summary_text", "routing_text"],
        )
        searcher = index.searcher()
        result = searcher.search(parsed, limit=max(1, limit))
        hits = []
        for rank, (score, doc_address) in enumerate(result.hits, start=1):
            stored = searcher.doc(doc_address).to_dict()
            metadata = _json_field(stored, "metadata_json")
            hits.append(
                {
                    "rank": rank,
                    "score": float(score),
                    "summary_id": _first(stored, "summary_id"),
                    "root_id": _first(stored, "root_id"),
                    "scope_id": _first(stored, "scope_id"),
                    "kind": _first(stored, "kind"),
                    "modality": _first(stored, "modality"),
                    "title": _first(stored, "title"),
                    "root_label": metadata.get("root_label"),
                }
            )
    except Exception:
        return {
            "status": "unavailable",
            "reasons": ["global_representative_search_failed"],
            "representative_index_uri": index_uri,
        }

    return {
        "status": "ok",
        "representative_index_uri": index_uri,
        "query_errors": [str(error) for error in errors],
        "hits": hits,
    }


def _upsert_summary_row(
    *,
    summary_id: str,
    root_id: str,
    scope_id: str,
    source_item_id: str | None,
    title: str,
    summary_text: str,
    routing_text: str,
    source_refs: list[str],
    source_count: int,
    sample_count: int,
    coverage_estimate: float,
    sample_policy: str,
    producer: str,
    profile: str,
    watermark: str,
    status: str,
    attrs: dict[str, Any],
    now: str,
    created_at: str | None,
) -> None:
    with sqlite3.connect(catalog_path()) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute(
            """
            INSERT INTO "summary_nodes"
            (summary_id, root_id, scope_id, parent_summary_id, source_item_id,
             doc_id, kind, modality, media_kind, container_kind, summary_level,
             title, summary_text, routing_text, source_refs_json, source_count,
             sample_count, coverage_estimate, sample_policy, producer, profile,
             source_high_watermark, summary_status, confidence, attrs_json,
             created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(summary_id) DO UPDATE SET
                root_id = excluded.root_id,
                scope_id = excluded.scope_id,
                parent_summary_id = excluded.parent_summary_id,
                source_item_id = excluded.source_item_id,
                doc_id = excluded.doc_id,
                kind = excluded.kind,
                modality = excluded.modality,
                media_kind = excluded.media_kind,
                container_kind = excluded.container_kind,
                summary_level = excluded.summary_level,
                title = excluded.title,
                summary_text = excluded.summary_text,
                routing_text = excluded.routing_text,
                source_refs_json = excluded.source_refs_json,
                source_count = excluded.source_count,
                sample_count = excluded.sample_count,
                coverage_estimate = excluded.coverage_estimate,
                sample_policy = excluded.sample_policy,
                producer = excluded.producer,
                profile = excluded.profile,
                source_high_watermark = excluded.source_high_watermark,
                summary_status = excluded.summary_status,
                confidence = excluded.confidence,
                attrs_json = excluded.attrs_json,
                created_at = excluded.created_at,
                updated_at = excluded.updated_at
            """,
            (
                summary_id,
                root_id,
                scope_id,
                None,
                source_item_id,
                None,
                "root_summary",
                "text",
                None,
                "root",
                0,
                title,
                summary_text,
                routing_text,
                json.dumps(source_refs, sort_keys=True),
                source_count,
                sample_count,
                coverage_estimate,
                sample_policy,
                producer,
                profile,
                watermark,
                status,
                None,
                json.dumps(attrs, sort_keys=True),
                created_at or now,
                now,
            ),
        )
        conn.commit()


def _summary_state(summary_id: str) -> dict[str, Any] | None:
    with sqlite3.connect(catalog_path()) as conn:
        row = conn.execute(
            """
            SELECT source_high_watermark, summary_status, created_at
            FROM "summary_nodes"
            WHERE summary_id = ?
            """,
            (summary_id,),
        ).fetchone()
    if not row:
        return None
    return {
        "source_high_watermark": row[0],
        "summary_status": row[1],
        "created_at": row[2],
    }


def _current_text_summary_rows() -> list[dict[str, Any]]:
    with sqlite3.connect(catalog_path()) as conn:
        rows = conn.execute(
            """
            SELECT s.summary_id, s.root_id, s.scope_id, s.kind, s.modality,
                   s.title, s.summary_text, s.routing_text, s.source_refs_json,
                   s.source_high_watermark, s.updated_at, sr.root_label
            FROM "summary_nodes" s
            JOIN "source_roots" sr ON sr.root_id = s.root_id
            WHERE s.summary_status = 'current'
              AND s.modality = 'text'
            ORDER BY s.root_id, s.scope_id, s.summary_id
            """
        ).fetchall()
    result = []
    for row in rows:
        metadata = {
            "root_label": row[11],
            "source_high_watermark": row[9],
            "updated_at": row[10],
        }
        result.append(
            {
                "summary_id": row[0],
                "root_id": row[1],
                "scope_id": row[2],
                "kind": row[3],
                "modality": row[4],
                "title": row[5] or row[11] or row[1],
                "summary_text": row[6] or "",
                "routing_text": row[7] or "",
                "source_refs_json": row[8] or "[]",
                "source_high_watermark": row[9] or "",
                "metadata_json": json.dumps(metadata, sort_keys=True),
            }
        )
    return result


def _root_source_item_id(root_id: str) -> str | None:
    with sqlite3.connect(catalog_path()) as conn:
        row = conn.execute(
            """
            SELECT source_item_id
            FROM "source_items"
            WHERE root_id = ?
              AND relative_path = '.'
              AND item_kind = 'folder'
            """,
            (root_id,),
        ).fetchone()
    return row[0] if row else None


def _sample_chunks(chunks: list[dict[str, Any]], *, max_chunks: int) -> list[dict[str, Any]]:
    limit = max(1, int(max_chunks or 1))
    by_doc: dict[str, list[dict[str, Any]]] = {}
    for chunk in sorted(
        chunks,
        key=lambda item: (
            str(item.get("relative_path") or ""),
            str(item.get("doc_id") or ""),
            int(item.get("page_start") or 0),
            str(item.get("chunk_id") or ""),
        ),
    ):
        by_doc.setdefault(str(chunk.get("doc_id") or ""), []).append(chunk)

    samples: list[dict[str, Any]] = []
    for doc_id in sorted(by_doc):
        if len(samples) >= limit:
            break
        samples.append(by_doc[doc_id][0])
    if len(samples) < limit:
        seen = {str(sample.get("chunk_id")) for sample in samples}
        for chunk in chunks:
            if len(samples) >= limit:
                break
            if str(chunk.get("chunk_id")) not in seen:
                samples.append(chunk)
    return samples


def _summary_prompt(
    *,
    root_label: str,
    samples: list[dict[str, Any]],
    max_chars: int,
    per_chunk_chars: int,
) -> str:
    rows = []
    for index, chunk in enumerate(samples, start=1):
        text = " ".join(str(chunk.get("body") or "").split())[:per_chunk_chars]
        metadata = _json_object(chunk.get("metadata_json"))
        rows.append(
            {
                "n": index,
                "path": metadata.get("relative_path") or "",
                "title": chunk.get("title") or "",
                "heading": chunk.get("heading_path") or "",
                "content_type": chunk.get("content_type") or "",
                "excerpt": text,
            }
        )
    prompt = (
        "Write a concise routing summary for a local document root. "
        "Use only the sampled excerpts. Do not claim complete coverage. "
        "Return 2-4 plain sentences focused on topics, document types, and "
        "terms that would help route future search queries.\n\n"
        f"Root label: {root_label}\n\n"
        f"Sampled chunks:\n{json.dumps(rows, ensure_ascii=True, indent=2)}"
    )
    return prompt[:max_chars]


def _deterministic_routing_text(
    root_label: str,
    samples: list[dict[str, Any]],
    summary_text: str,
) -> str:
    paths: set[str] = set()
    titles: set[str] = set()
    headings: set[str] = set()
    content_types: set[str] = set()
    for chunk in samples:
        metadata = _json_object(chunk.get("metadata_json"))
        if metadata.get("relative_path"):
            paths.add(str(metadata["relative_path"]))
        if chunk.get("title"):
            titles.add(str(chunk["title"]))
        if chunk.get("heading_path"):
            headings.add(str(chunk["heading_path"]))
        if chunk.get("content_type"):
            content_types.add(str(chunk["content_type"]))
    parts = [
        f"Root: {root_label}",
        f"Summary: {summary_text}",
        "Paths: " + " | ".join(sorted(paths)[:25]),
        "Titles: " + " | ".join(sorted(titles)[:25]),
        "Headings: " + " | ".join(sorted(headings)[:25]),
        "Content types: " + " | ".join(sorted(content_types)[:10]),
    ]
    return "\n".join(part for part in parts if part.strip())


def _source_refs(samples: list[dict[str, Any]]) -> list[str]:
    refs = sorted({str(chunk.get("ref") or "") for chunk in samples if chunk.get("ref")})
    return refs


def _coverage(sample_count: int, source_count: int) -> float:
    if source_count <= 0:
        return 0.0
    return round(sample_count / source_count, 6)


def _representative_watermark(rows: list[dict[str, Any]], fts_profile: str) -> str:
    digest = hashlib.sha256()
    digest.update(fts_profile.encode("utf-8"))
    digest.update(b"\0")
    digest.update(GLOBAL_FTS_TEMPLATE.encode("utf-8"))
    digest.update(b"\0")
    for row in rows:
        for field in (
            "summary_id",
            "root_id",
            "scope_id",
            "source_high_watermark",
            "routing_text",
        ):
            digest.update(str(row.get(field) or "").encode("utf-8"))
            digest.update(b"\0")
    return digest.hexdigest()


def _write_manifest(
    *,
    manifest_path: Path,
    fts_profile: str,
    source_high_watermark: str,
    row_count: int,
) -> None:
    manifest_path.write_text(
        json.dumps(
            {
                "built_at": _iso(_utc_now()),
                "fts_profile": fts_profile,
                "template_name": GLOBAL_FTS_TEMPLATE,
                "summary_watermark": source_high_watermark,
                "row_count": row_count,
                "schema_version": "0.7",
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def _manifest_current(
    manifest_path: Path,
    source_high_watermark: str,
    fts_profile: str,
) -> bool:
    if not manifest_path.exists():
        return False
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return (
        manifest.get("summary_watermark") == source_high_watermark
        and manifest.get("fts_profile") == fts_profile
        and manifest.get("template_name") == GLOBAL_FTS_TEMPLATE
    )


def _selected_scopes(
    hits: list[dict[str, Any]],
    *,
    max_scopes: int,
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    seen: set[str] = set()
    for hit in hits:
        scope_id = str(hit.get("scope_id") or "")
        if not scope_id or scope_id in seen:
            continue
        seen.add(scope_id)
        selected.append(
            {
                "scope_id": scope_id,
                "reason": "representative_hit",
                "rank": hit.get("rank"),
                "summary_id": hit.get("summary_id"),
            }
        )
        if len(selected) >= max(1, max_scopes):
            break
    return selected


def _weak_route_reasons(
    *,
    representative_hits: list[dict[str, Any]],
    deep_hits: list[dict[str, Any]],
    config: dict[str, Any],
) -> list[str]:
    reasons: list[str] = []
    hydrated_hits = [hit for hit in deep_hits if hit.get("ref")]
    if len(hydrated_hits) < int(config["min_hydrated_deep_hits"]):
        reasons.append("too_few_hydrated_deep_hits")
    if len(representative_hits) > 1:
        gap = float(representative_hits[0].get("score", 0.0)) - float(
            representative_hits[1].get("score", 0.0)
        )
        if gap < float(config["min_representative_score_gap"]):
            reasons.append("weak_representative_score_gap")
    return reasons


def _route_trace(
    *,
    route: dict[str, Any],
    selected_scopes: list[dict[str, Any]],
    deep_result: dict[str, Any],
    status: str,
    widening_status: dict[str, Any],
) -> dict[str, Any]:
    hits = deep_result.get("hits", [])
    return {
        "mode": "global_representative_fts",
        "status": status,
        "representative_index_uri": route.get("representative_index_uri"),
        "representative_hits": route.get("hits", [])[:12],
        "selected_scopes": selected_scopes,
        "deep_searches": _deep_searches(selected_scopes, hits, deep_result),
        "widening_status": widening_status,
    }


def _fallback_trace(reasons: list[str]) -> dict[str, Any]:
    return {
        "mode": "fallback_all_current_fts",
        "status": "routing_unavailable",
        "reasons": reasons,
        "widening_status": {"status": "fallback_all_scopes"},
    }


def _deep_searches(
    selected_scopes: list[dict[str, Any]],
    hits: list[dict[str, Any]],
    deep_result: dict[str, Any],
) -> list[dict[str, Any]]:
    counts_by_scope: dict[str, int] = {}
    fts_by_scope: dict[str, str] = {}
    for hit in hits:
        scope_id = str(hit.get("scope_id") or "")
        if not scope_id:
            continue
        counts_by_scope[scope_id] = counts_by_scope.get(scope_id, 0) + 1
        if hit.get("fts_index_id"):
            fts_by_scope[scope_id] = str(hit["fts_index_id"])
    failures = {
        str(failure.get("scope_id") or ""): failure
        for failure in deep_result.get("failures", [])
    }
    searches = []
    for selected in selected_scopes:
        scope_id = str(selected["scope_id"])
        failure = failures.get(scope_id)
        searches.append(
            {
                "scope_id": scope_id,
                "fts_index_id": fts_by_scope.get(scope_id),
                "status": "failed" if failure else "ok",
                "hits_returned": counts_by_scope.get(scope_id, 0),
            }
        )
    return searches


def _global_fts_uri(fts_profile: str) -> str:
    return f"fts/global_representatives/{fts_profile}"


def _summary_id(scope_id: str) -> str:
    return stable_id("sum", scope_id, "root_summary", "text")


def _empty_watermark(root_id: str, scope_id: str, sample_policy: str) -> str:
    return hashlib.sha256(
        "\0".join([root_id, scope_id, sample_policy, "empty"]).encode("utf-8")
    ).hexdigest()


def _routing_defaults() -> dict[str, Any]:
    return dict(load_routing_config().get("defaults", {}))


def _fts_profile() -> str:
    defaults = load_parser_config().get("defaults", {})
    return str(defaults.get("fts_profile") or "text_default_en")


def _chunk_profile() -> str:
    defaults = load_parser_config().get("defaults", {})
    return str(defaults.get("chunk_profile") or "docling_hybrid_v1")


def _tantivy_runtime_status() -> dict[str, str]:
    try:
        import tantivy  # noqa: F401  # type: ignore[import-not-found]
    except ModuleNotFoundError:
        return {
            "status": "failed",
            "error_kind": "fts_dependency_missing",
            "message": "Install the fts extra before running routing commands.",
        }
    return {"status": "ok"}


def _tantivy_index_exists(index_dir: Path) -> bool:
    try:
        import tantivy  # type: ignore[import-not-found]

        return bool(index_dir.exists() and tantivy.Index.exists(str(index_dir)))
    except Exception:
        return False


def _json_field(stored: dict[str, Any], field: str) -> dict[str, Any]:
    return _json_object(_first(stored, field))


def _json_object(value: Any) -> dict[str, Any]:
    if not value:
        return {}
    try:
        parsed = json.loads(str(value))
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _first(stored: dict[str, Any], field: str) -> Any:
    value = stored.get(field)
    if isinstance(value, list):
        return value[0] if value else None
    return value


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")
