"""Root/document representative summary generation, prompts, and the LLM call."""

from __future__ import annotations

import json
import os
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse

from even.chunks import chunks_for_root, high_watermark
from even.routing.budget import _generate_and_calibrate
from even.routing.importance import (
    _importance_learn_threshold,
    _importance_prior,
    _learn_low_prior,
    _parse_importance,
    _resolve_importance,
)
from even.routing.shared import (
    PROMPT_VERSION,
    RoutingIndexOptions,
    SummaryGenerationError,
    SummaryGenerator,
    _chunk_profile,
    _clean_routing_meta,
    _coverage,
    _empty_watermark,
    _iso,
    _json_object,
    _routing_defaults,
    _summary_id,
    _utc_now,
)
from even.routing.summary_store import (
    _root_source_item_id,
    _summary_state,
    _upsert_summary_row,
)


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
            routing_meta={},
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
        summary_text = _generate_and_calibrate(
            summary_generator, prompt, model=model, url=url, timeout=timeout
        )
    except SummaryGenerationError as exc:
        _upsert_summary_row(
            summary_id=summary_id,
            root_id=root_id,
            scope_id=scope_id,
            source_item_id=_root_source_item_id(root_id),
            title=root_label or scope_id,
            summary_text="",
            routing_meta=_document_routing_meta(root_label, samples),
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
            importance=_importance_prior(root_label, scope_id),
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

    summary_text, parsed_importance = _parse_importance(str(summary_text or ""))
    summary_text = " ".join(summary_text.split())
    importance = _resolve_importance(parsed_importance, root_label, scope_id)
    if parsed_importance is not None and parsed_importance < _importance_learn_threshold():
        _learn_low_prior(root_label)
    if not summary_text:
        _upsert_summary_row(
            summary_id=summary_id,
            root_id=root_id,
            scope_id=scope_id,
            source_item_id=_root_source_item_id(root_id),
            title=root_label or scope_id,
            summary_text="",
            routing_meta=_document_routing_meta(root_label, samples),
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
            importance=importance,
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
        routing_meta=_document_routing_meta(root_label, samples),
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
        importance=importance,
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
    from even import ollama

    base_url = _validated_local_base_url(url)
    try:
        return ollama.generate_text(
            prompt,
            model=model,
            url=base_url,
            timeout=timeout,
            options={"temperature": 0},
        )
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


def _validated_local_base_url(base_url: str) -> str:
    """Validate a summary Ollama endpoint and return its normalized base URL.

    Summary generation is localhost-only; `ollama.generate_text` appends the
    `/api/generate` path, so this returns the base without it.
    """

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
    return normalized.rstrip("/")


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
        "terms that would help route future search queries. "
        "Then, on a final separate line, rate how important this root is to "
        "represent for search routing as 'IMPORTANCE: <value>' with value "
        "between 0 and 1. State the reason inside the summary itself only for "
        "extreme cases (clearly trivial or clearly central).\n\n"
        f"Root label: {root_label}\n\n"
        f"Sampled chunks:\n{json.dumps(rows, ensure_ascii=True, indent=2)}"
    )
    return prompt[:max_chars]


def _document_routing_meta(
    root_label: str,
    samples: list[dict[str, Any]],
) -> dict[str, Any]:
    """Structured deterministic routing facets for a document root."""

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
    return _clean_routing_meta(
        {
            "root": root_label,
            "paths": sorted(paths)[:25],
            "titles": sorted(titles)[:25],
            "headings": sorted(headings)[:25],
            "content_types": sorted(content_types)[:10],
        }
    )


def _source_refs(samples: list[dict[str, Any]]) -> list[str]:
    refs = sorted({str(chunk.get("ref") or "") for chunk in samples if chunk.get("ref")})
    return refs


