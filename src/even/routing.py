"""Global representative routing for text search.

Builds root-level representative summaries, projects them into a fixed global
FTS map, and uses that map to choose root-scoped FTS indexes before deep search.
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
from even.references import evidence_ref


GLOBAL_FTS_TEMPLATE = "fts_summary_node"
GLOBAL_FTS_MANIFEST = "manifest.json"
PROMPT_VERSION = "summary_prompt_v1"
MEDIA_PROMPT_VERSION = "media_summary_prompt_v1"
MEDIA_SUMMARY_PROFILE = "media_album_summary_v1"


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
    """Build summary nodes and the global representative FTS map."""

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

    generator = summary_generator or _generate_summary_text
    document_summary = _upsert_root_summary(
        root_id=scan_result["root_id"],
        root_label=str(scan_result.get("root_label") or ""),
        scope_id=scan_result["scope_id"],
        options=options,
        summary_generator=generator,
    )
    media_summary = _upsert_media_summary(
        root_id=scan_result["root_id"],
        root_label=str(scan_result.get("root_label") or ""),
        scope_id=scan_result["scope_id"],
        options=options,
        summary_generator=generator,
    )
    document_summary["summary_type"] = "document"
    media_summary["summary_type"] = "media"
    summaries = [document_summary, media_summary]
    current_summaries = [
        summary
        for summary in summaries
        if summary.get("status") == "ok" and summary.get("summary_status") == "current"
    ]
    if not current_summaries:
        primary = _primary_summary(summaries)
        return {
            "status": _blocked_summary_status(summaries),
            "error_kind": primary.get("error_kind"),
            "index_backend": "routing",
            "root_id": scan_result["root_id"],
            "root_label": scan_result.get("root_label"),
            "scope_id": scan_result["scope_id"],
            "summary_id": primary["summary_id"],
            "summary_ids": [summary["summary_id"] for summary in summaries],
            "summary_status": primary["summary_status"],
            "auto_scan_status": scan_result["status"],
            "summaries": _summary_payloads(summaries),
            "counts": _combined_summary_counts(summaries),
            "message": primary.get("message", ""),
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
            "summary_id": current_summaries[0]["summary_id"],
            "summary_ids": [summary["summary_id"] for summary in summaries],
            "summary_status": "current",
            "auto_scan_status": scan_result["status"],
            "summaries": _summary_payloads(summaries),
            "global_representative_fts": projection,
            "counts": _combined_summary_counts(summaries),
        }

    counts = _combined_summary_counts(summaries)
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
        "summary_id": current_summaries[0]["summary_id"],
        "summary_ids": [summary["summary_id"] for summary in summaries],
        "summary_status": "current",
        "summary_index_status": projection["index_status"],
        "global_representative_fts": projection,
        "auto_scan_status": scan_result["status"],
        "summaries": _summary_payloads(summaries),
        "counts": counts,
    }


def _primary_summary(summaries: list[dict[str, Any]]) -> dict[str, Any]:
    for summary in summaries:
        if summary.get("error_kind"):
            return summary
    return summaries[0]


def _blocked_summary_status(summaries: list[dict[str, Any]]) -> str:
    if any(summary.get("status") == "failed" for summary in summaries):
        return "failed"
    return "deferred"


def _summary_payloads(summaries: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    payloads: dict[str, dict[str, Any]] = {}
    for summary in summaries:
        summary_type = str(summary.get("summary_type") or summary.get("summary_id"))
        payloads[summary_type] = dict(summary)
    return payloads


def _combined_summary_counts(summaries: list[dict[str, Any]]) -> dict[str, Any]:
    counts: dict[str, Any] = {}
    for summary in summaries:
        for key, value in dict(summary.get("counts") or {}).items():
            if isinstance(value, (int, float)):
                counts[key] = counts.get(key, 0) + value
            else:
                counts[key] = value
    return counts


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
    rows = _current_summary_rows()
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


def _upsert_media_summary(
    *,
    root_id: str,
    root_label: str,
    scope_id: str,
    options: RoutingIndexOptions,
    summary_generator: SummaryGenerator,
) -> dict[str, Any]:
    config = _routing_defaults()
    sample_policy = "media_album_v1"
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
    max_assets = int(options.limit or config["summary_sample_chunks_default"])
    assets = _media_assets_for_root(root_id)
    summary_id = _media_summary_id(scope_id)
    now = _iso(_utc_now())
    state = _summary_state(summary_id)

    if not assets:
        written = 0
        if state:
            _upsert_summary_row(
                summary_id=summary_id,
                root_id=root_id,
                scope_id=scope_id,
                source_item_id=_root_source_item_id(root_id),
                title=f"{root_label or scope_id} media",
                summary_text="",
                routing_text="",
                source_refs=[],
                source_count=0,
                sample_count=0,
                coverage_estimate=0.0,
                sample_policy=sample_policy,
                producer="none",
                profile=MEDIA_SUMMARY_PROFILE,
                watermark=_empty_watermark(root_id, scope_id, sample_policy),
                status="deleted",
                attrs={"error_kind": "no_media_summary_inputs"},
                now=now,
                created_at=state.get("created_at"),
                kind="album_summary",
                modality="mixed",
                container_kind="root",
            )
            written = 1
        return {
            "status": "deferred",
            "error_kind": "no_media_summary_inputs",
            "message": "No current media assets were available for routing.",
            "summary_id": summary_id,
            "summary_status": "deferred",
            "index_status": "deferred",
            "counts": {
                "media_assets_considered": 0,
                "media_assets_sampled": 0,
                "summary_nodes_written": written,
            },
        }

    watermark = _media_high_watermark(
        assets,
        sample_policy,
        model,
        str(max_assets),
        MEDIA_PROMPT_VERSION,
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
                "media_assets_considered": len(assets),
                "media_assets_sampled": 0,
                "summary_nodes_written": 0,
            },
        }

    samples = _sample_media_assets(assets, max_assets=max_assets)
    prompt = _media_summary_prompt(
        root_label=root_label,
        samples=samples,
        max_chars=int(config["summary_prompt_max_chars"]),
        per_asset_chars=int(config["summary_sample_chars_per_chunk"]),
    )
    modality = _media_modality(assets)
    media_kind = _dominant_media_kind(assets)
    title = f"{root_label or scope_id} media"

    try:
        summary_text = summary_generator(prompt, model=model, url=url, timeout=timeout)
    except SummaryGenerationError as exc:
        _upsert_summary_row(
            summary_id=summary_id,
            root_id=root_id,
            scope_id=scope_id,
            source_item_id=_root_source_item_id(root_id),
            title=title,
            summary_text="",
            routing_text=_media_routing_text(root_label, samples, ""),
            source_refs=_media_source_refs(samples),
            source_count=len(assets),
            sample_count=len(samples),
            coverage_estimate=_coverage(len(samples), len(assets)),
            sample_policy=sample_policy,
            producer=f"ollama:{model}",
            profile=MEDIA_SUMMARY_PROFILE,
            watermark=watermark,
            status=exc.status,
            attrs=_media_summary_attrs(
                assets,
                samples,
                {"error_kind": exc.error_kind, "message": exc.message},
            ),
            now=now,
            created_at=state.get("created_at") if state else None,
            kind="album_summary",
            modality=modality,
            media_kind=media_kind,
            container_kind="root",
        )
        return {
            "status": exc.status,
            "error_kind": exc.error_kind,
            "message": exc.message,
            "summary_id": summary_id,
            "summary_status": exc.status,
            "index_status": exc.status,
            "counts": {
                "media_assets_considered": len(assets),
                "media_assets_sampled": len(samples),
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
            title=title,
            summary_text="",
            routing_text=_media_routing_text(root_label, samples, ""),
            source_refs=_media_source_refs(samples),
            source_count=len(assets),
            sample_count=len(samples),
            coverage_estimate=_coverage(len(samples), len(assets)),
            sample_policy=sample_policy,
            producer=f"ollama:{model}",
            profile=MEDIA_SUMMARY_PROFILE,
            watermark=watermark,
            status="failed",
            attrs=_media_summary_attrs(assets, samples, {"error_kind": "empty_summary"}),
            now=now,
            created_at=state.get("created_at") if state else None,
            kind="album_summary",
            modality=modality,
            media_kind=media_kind,
            container_kind="root",
        )
        return {
            "status": "failed",
            "error_kind": "empty_summary",
            "message": "The local summary model returned no text.",
            "summary_id": summary_id,
            "summary_status": "failed",
            "index_status": "failed",
            "counts": {
                "media_assets_considered": len(assets),
                "media_assets_sampled": len(samples),
                "summary_nodes_written": 1,
            },
        }

    _upsert_summary_row(
        summary_id=summary_id,
        root_id=root_id,
        scope_id=scope_id,
        source_item_id=_root_source_item_id(root_id),
        title=title,
        summary_text=summary_text,
        routing_text=_media_routing_text(root_label, samples, summary_text),
        source_refs=_media_source_refs(samples),
        source_count=len(assets),
        sample_count=len(samples),
        coverage_estimate=_coverage(len(samples), len(assets)),
        sample_policy=sample_policy,
        producer=f"ollama:{model}",
        profile=MEDIA_SUMMARY_PROFILE,
        watermark=watermark,
        status="current",
        attrs=_media_summary_attrs(
            assets,
            samples,
            {
                "prompt_version": MEDIA_PROMPT_VERSION,
                "model": model,
                "ollama_url": url,
            },
        ),
        now=now,
        created_at=state.get("created_at") if state else None,
        kind="album_summary",
        modality=modality,
        media_kind=media_kind,
        container_kind="root",
    )
    return {
        "status": "ok",
        "summary_id": summary_id,
        "summary_status": "current",
        "index_status": "rebuilt" if options.force else "refreshed",
        "counts": {
            "media_assets_considered": len(assets),
            "media_assets_sampled": len(samples),
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
        rows = _current_summary_rows()
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
    parent_summary_id: str | None = None,
    doc_id: str | None = None,
    kind: str = "root_summary",
    modality: str = "text",
    media_kind: str | None = None,
    container_kind: str = "root",
    summary_level: int = 0,
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
                parent_summary_id,
                source_item_id,
                doc_id,
                kind,
                modality,
                media_kind,
                container_kind,
                summary_level,
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


def _current_summary_rows() -> list[dict[str, Any]]:
    with sqlite3.connect(catalog_path()) as conn:
        rows = conn.execute(
            """
            SELECT s.summary_id, s.root_id, s.scope_id, s.kind, s.modality,
                   s.title, s.summary_text, s.routing_text, s.source_refs_json,
                   s.source_high_watermark, s.updated_at, sr.root_label,
                   s.media_kind, s.container_kind
            FROM "summary_nodes" s
            JOIN "source_roots" sr ON sr.root_id = s.root_id
            WHERE s.summary_status = 'current'
              AND COALESCE(s.routing_text, '') <> ''
            ORDER BY s.root_id, s.scope_id, s.summary_id
            """
        ).fetchall()
    result = []
    for row in rows:
        metadata = {
            "root_label": row[11],
            "source_high_watermark": row[9],
            "updated_at": row[10],
            "media_kind": row[12],
            "container_kind": row[13],
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


def _media_assets_for_root(root_id: str) -> list[dict[str, Any]]:
    sql = """
        SELECT a.asset_id, a.source_item_id, a.media_class, a.inspect_status,
               a.attrs_json, a.updated_at, si.relative_path, si.media_type,
               si.source_sha256, si.size_bytes,
               img.format AS image_format, img.width AS image_width,
               img.height AS image_height, img.megapixels AS image_megapixels,
               img.color_mode AS image_color_mode,
               img.captured_at AS image_captured_at,
               vid.container AS video_container,
               vid.video_codec AS video_codec, vid.audio_codec AS audio_codec,
               vid.width AS video_width, vid.height AS video_height,
               vid.duration_seconds AS video_duration_seconds,
               vid.frame_rate AS video_frame_rate,
               vid.captured_at AS video_captured_at,
               mdl.format AS model_format, mdl.vertex_count AS model_vertex_count,
               mdl.face_count AS model_face_count, mdl.units AS model_units,
               (
                   SELECT value_text
                   FROM "media_observations"
                   WHERE asset_id = a.asset_id
                     AND observation_kind = 'caption'
                   ORDER BY created_at DESC, observation_id DESC
                   LIMIT 1
               ) AS caption,
               (
                   SELECT value_text
                   FROM "media_observations"
                   WHERE asset_id = a.asset_id
                     AND observation_kind = 'media_kind'
                   ORDER BY created_at DESC, observation_id DESC
                   LIMIT 1
               ) AS media_kind
        FROM "media_assets" a
        JOIN "source_items" si ON si.source_item_id = a.source_item_id
        LEFT JOIN "image_metadata" img ON img.asset_id = a.asset_id
        LEFT JOIN "video_metadata" vid ON vid.asset_id = a.asset_id
        LEFT JOIN "model3d_metadata" mdl ON mdl.asset_id = a.asset_id
        WHERE si.root_id = ?
          AND si.inventory_status IN ('current', 'unchanged', 'changed')
        ORDER BY si.relative_path, a.asset_id
    """
    with sqlite3.connect(catalog_path()) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(sql, (root_id,)).fetchall()
    return [dict(row) for row in rows]


def _sample_media_assets(
    assets: list[dict[str, Any]], *, max_assets: int
) -> list[dict[str, Any]]:
    limit = max(1, int(max_assets or 1))
    ordered = sorted(
        assets,
        key=lambda item: (
            str(item.get("media_class") or ""),
            str(item.get("relative_path") or ""),
            str(item.get("asset_id") or ""),
        ),
    )
    by_class: dict[str, list[dict[str, Any]]] = {}
    for asset in ordered:
        by_class.setdefault(str(asset.get("media_class") or "other"), []).append(asset)

    samples: list[dict[str, Any]] = []
    for media_class in sorted(by_class):
        if len(samples) >= limit:
            break
        samples.append(by_class[media_class][0])
    if len(samples) < limit:
        seen = {str(sample.get("asset_id")) for sample in samples}
        for asset in ordered:
            if len(samples) >= limit:
                break
            if str(asset.get("asset_id")) not in seen:
                samples.append(asset)
    return samples


def _media_summary_prompt(
    *,
    root_label: str,
    samples: list[dict[str, Any]],
    max_chars: int,
    per_asset_chars: int,
) -> str:
    rows = []
    for index, asset in enumerate(samples, start=1):
        caption = " ".join(str(asset.get("caption") or "").split())[:per_asset_chars]
        rows.append(
            {
                "n": index,
                "path": asset.get("relative_path") or "",
                "media_class": asset.get("media_class") or "",
                "media_type": asset.get("media_type") or "",
                "media_kind": asset.get("media_kind") or "",
                "caption": caption,
                "metadata": _media_metadata_facets(asset),
            }
        )
    prompt = (
        "Write a concise routing summary for a local media root. "
        "Use only sampled filenames, existing captions, media-kind labels, "
        "and safe metadata. Do not infer unseen visual content. Do not claim "
        "complete coverage. Return 2-4 plain sentences focused on visual "
        "topics, media types, and terms that would help route future search "
        "queries.\n\n"
        f"Root label: {root_label}\n\n"
        f"Sampled media assets:\n{json.dumps(rows, ensure_ascii=True, indent=2)}"
    )
    return prompt[:max_chars]


def _media_metadata_facets(asset: dict[str, Any]) -> dict[str, Any]:
    facets: dict[str, Any] = {}
    if asset.get("size_bytes") is not None:
        facets["size_bytes"] = asset["size_bytes"]
    if asset.get("image_width") and asset.get("image_height"):
        facets["dimensions"] = f"{asset['image_width']}x{asset['image_height']}"
    if asset.get("image_format"):
        facets["image_format"] = asset["image_format"]
    if asset.get("image_color_mode"):
        facets["image_color_mode"] = asset["image_color_mode"]
    if asset.get("image_captured_at"):
        facets["captured_at"] = asset["image_captured_at"]
    if asset.get("video_width") and asset.get("video_height"):
        facets["video_dimensions"] = f"{asset['video_width']}x{asset['video_height']}"
    if asset.get("video_container"):
        facets["video_container"] = asset["video_container"]
    if asset.get("video_codec"):
        facets["video_codec"] = asset["video_codec"]
    if asset.get("audio_codec"):
        facets["audio_codec"] = asset["audio_codec"]
    if asset.get("video_duration_seconds") is not None:
        facets["duration_seconds"] = asset["video_duration_seconds"]
    if asset.get("video_frame_rate") is not None:
        facets["frame_rate"] = asset["video_frame_rate"]
    if asset.get("video_captured_at"):
        facets["captured_at"] = asset["video_captured_at"]
    if asset.get("model_format"):
        facets["model_format"] = asset["model_format"]
    if asset.get("model_vertex_count") is not None:
        facets["vertex_count"] = asset["model_vertex_count"]
    if asset.get("model_face_count") is not None:
        facets["face_count"] = asset["model_face_count"]
    if asset.get("model_units"):
        facets["units"] = asset["model_units"]
    return facets


def _media_routing_text(
    root_label: str,
    samples: list[dict[str, Any]],
    summary_text: str,
) -> str:
    paths: set[str] = set()
    filenames: set[str] = set()
    captions: set[str] = set()
    media_classes: set[str] = set()
    media_types: set[str] = set()
    media_kinds: set[str] = set()
    dimensions: set[str] = set()
    durations: set[str] = set()
    model_formats: set[str] = set()

    for asset in samples:
        relative_path = str(asset.get("relative_path") or "")
        if relative_path:
            paths.add(relative_path)
            filenames.add(Path(relative_path).stem.replace("_", " ").replace("-", " "))
        if asset.get("caption"):
            captions.add(" ".join(str(asset["caption"]).split())[:160])
        if asset.get("media_class"):
            media_classes.add(str(asset["media_class"]))
        if asset.get("media_type"):
            media_types.add(str(asset["media_type"]))
        if asset.get("media_kind"):
            media_kinds.add(str(asset["media_kind"]))
        if asset.get("image_width") and asset.get("image_height"):
            dimensions.add(f"{asset['image_width']}x{asset['image_height']}")
        if asset.get("video_width") and asset.get("video_height"):
            dimensions.add(f"{asset['video_width']}x{asset['video_height']}")
        if asset.get("video_duration_seconds") is not None:
            durations.add(str(asset["video_duration_seconds"]))
        if asset.get("model_format"):
            model_formats.add(str(asset["model_format"]))

    parts = [
        f"Root: {root_label}",
        f"Summary: {summary_text}",
        "Paths: " + " | ".join(sorted(paths)[:25]),
        "Filenames: " + " | ".join(sorted(filenames)[:25]),
        "Captions: " + " | ".join(sorted(captions)[:20]),
        "Media kinds: " + " | ".join(sorted(media_kinds)[:10]),
        "Media classes: " + " | ".join(sorted(media_classes)[:10]),
        "Media types: " + " | ".join(sorted(media_types)[:10]),
        "Dimensions: " + " | ".join(sorted(dimensions)[:10]),
        "Durations seconds: " + " | ".join(sorted(durations)[:10]),
        "3D formats: " + " | ".join(sorted(model_formats)[:10]),
    ]
    return "\n".join(part for part in parts if part.strip())


def _media_source_refs(samples: list[dict[str, Any]]) -> list[str]:
    return sorted(
        {
            evidence_ref("media_assets", str(asset["asset_id"]))
            for asset in samples
            if asset.get("asset_id")
        }
    )


def _media_high_watermark(assets: list[dict[str, Any]], *extra: str) -> str:
    digest = hashlib.sha256()
    for value in extra:
        digest.update(str(value or "").encode("utf-8"))
        digest.update(b"\0")
    fields = (
        "asset_id",
        "source_item_id",
        "media_class",
        "inspect_status",
        "updated_at",
        "relative_path",
        "media_type",
        "source_sha256",
        "caption",
        "media_kind",
        "image_format",
        "image_width",
        "image_height",
        "image_captured_at",
        "video_container",
        "video_codec",
        "audio_codec",
        "video_width",
        "video_height",
        "video_duration_seconds",
        "video_captured_at",
        "model_format",
        "model_vertex_count",
        "model_face_count",
        "model_units",
    )
    for asset in sorted(
        assets,
        key=lambda item: (
            str(item.get("relative_path") or ""),
            str(item.get("asset_id") or ""),
        ),
    ):
        for field in fields:
            digest.update(str(asset.get(field) or "").encode("utf-8"))
            digest.update(b"\0")
    return digest.hexdigest()


def _media_modality(assets: list[dict[str, Any]]) -> str:
    valid = {"image", "video", "audio", "model3d"}
    classes = {str(asset.get("media_class") or "") for asset in assets}
    known = {media_class for media_class in classes if media_class in valid}
    if len(known) == 1 and len(classes) == 1:
        return next(iter(known))
    return "mixed"


def _dominant_media_kind(assets: list[dict[str, Any]]) -> str | None:
    counts: dict[str, int] = {}
    for asset in assets:
        media_kind = str(asset.get("media_kind") or "").strip()
        if media_kind:
            counts[media_kind] = counts.get(media_kind, 0) + 1
    if not counts:
        return None
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))[0][0]


def _media_summary_attrs(
    assets: list[dict[str, Any]],
    samples: list[dict[str, Any]],
    extra: dict[str, Any],
) -> dict[str, Any]:
    attrs = dict(extra)
    attrs.update(
        {
            "asset_count": len(assets),
            "sampled_asset_count": len(samples),
            "media_classes": _value_counts(assets, "media_class"),
            "media_kinds": _value_counts(assets, "media_kind"),
        }
    )
    return attrs


def _value_counts(rows: list[dict[str, Any]], field: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        value = str(row.get(field) or "").strip()
        if value:
            counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


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


def _media_summary_id(scope_id: str) -> str:
    return stable_id("sum", scope_id, "album_summary", "media")


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
