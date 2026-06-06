"""Hybrid search over local FTS and semantic indexes."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from agents_cli.fts import SearchOptions, search_text_indexes
from agents_cli.semantic import SemanticSearchOptions, search_semantic_indexes


@dataclass(frozen=True)
class HybridSearchOptions:
    limit: int = 30
    candidate_limit: int | None = 60
    rrf_k: int = 60
    rerank: str = "none"
    ollama_model: str | None = None
    ollama_url: str = "http://localhost:11434"


def search_hybrid_indexes(
    query: str, options: HybridSearchOptions
) -> dict[str, Any]:
    """Search FTS and semantic indexes, then fuse candidates by RRF."""

    limit = max(1, int(options.limit or 30))
    candidate_limit = max(limit, int(options.candidate_limit or 60))
    rrf_k = max(1, int(options.rrf_k or 60))

    fts_result = search_text_indexes(query, SearchOptions(limit=candidate_limit))
    semantic_result = search_semantic_indexes(
        query, SemanticSearchOptions(limit=candidate_limit)
    )

    fused_hits = _fuse_hits(
        fts_result.get("hits", []),
        semantic_result.get("hits", []),
        rrf_k=rrf_k,
    )
    rerank_report = _rerank_report("not_requested", mode="none")
    final_hits = fused_hits[:limit]

    rerank_mode = options.rerank or "none"
    if rerank_mode == "ollama":
        rerank_report = _rerank_with_ollama(
            query=query,
            hits=fused_hits[:candidate_limit],
            model=options.ollama_model,
            base_url=options.ollama_url,
        )
        if rerank_report["status"] == "ok":
            final_hits = rerank_report["hits"][:limit]
        else:
            final_hits = fused_hits[:limit]
    elif rerank_mode != "none":
        rerank_report = _rerank_report(
            "failed",
            error_kind="unsupported_rerank_mode",
            mode=rerank_mode,
        )

    backend_status = _backend_status(fts_result, semantic_result)
    status = backend_status["status"]
    if rerank_report["status"] == "failed" and status == "ok":
        status = "partial"

    failures = [
        *_backend_failures("fts", fts_result),
        *_backend_failures("semantic", semantic_result),
    ]
    if rerank_report["status"] == "failed":
        failures.append(
            {
                "backend": "rerank",
                "error_kind": rerank_report.get("error_kind", "rerank_failed"),
                "mode": rerank_report.get("mode", rerank_mode),
            }
        )

    return {
        "status": status,
        "search_backend": "hybrid",
        "query": query,
        "ranking": {
            "fusion": "rrf",
            "rrf_k": rrf_k,
            "rerank": rerank_report,
        },
        "counts": {
            "indexes_searched": backend_status["indexes_searched"],
            "index_failures": len(failures),
            "fts_indexes_searched": _count(fts_result, "indexes_searched"),
            "semantic_indexes_searched": _count(semantic_result, "indexes_searched"),
            "fts_hits": len(fts_result.get("hits", [])),
            "semantic_hits": len(semantic_result.get("hits", [])),
            "candidate_limit": candidate_limit,
            "candidates_fused": len(fused_hits),
            "hits_returned": len(final_hits),
        },
        "hits": final_hits,
        "failures": failures[:10],
    }


def _fuse_hits(
    fts_hits: list[dict[str, Any]],
    semantic_hits: list[dict[str, Any]],
    *,
    rrf_k: int,
) -> list[dict[str, Any]]:
    candidates: dict[str, dict[str, Any]] = {}
    _add_ranked_hits(candidates, "fts", fts_hits, rrf_k=rrf_k)
    _add_ranked_hits(candidates, "semantic", semantic_hits, rrf_k=rrf_k)
    hits = [_public_hit(candidate) for candidate in candidates.values()]
    return sorted(
        hits,
        key=lambda hit: (
            -float(hit["hybrid_score"]),
            int(hit.get("fts_rank") or 1_000_000),
            int(hit.get("semantic_rank") or 1_000_000),
            str(hit.get("chunk_id") or hit.get("hybrid_candidate_id") or ""),
        ),
    )


def _add_ranked_hits(
    candidates: dict[str, dict[str, Any]],
    backend: str,
    hits: list[dict[str, Any]],
    *,
    rrf_k: int,
) -> None:
    for rank, hit in enumerate(hits, start=1):
        key = _candidate_key(backend, hit)
        candidate = candidates.setdefault(
            key,
            {
                "key": key,
                "base_backend": backend,
                "base_hit": dict(hit),
                "matched_backends": set(),
                "rrf_score": 0.0,
            },
        )
        if backend == "fts":
            candidate["base_backend"] = "fts"
            candidate["base_hit"] = dict(hit)
        candidate["matched_backends"].add(backend)
        rank_key = f"{backend}_rank"
        if rank_key in candidate and int(candidate[rank_key]) <= rank:
            continue
        if rank_key in candidate:
            previous_rank = int(candidate[rank_key])
            candidate["rrf_score"] -= 1.0 / (rrf_k + previous_rank)
        candidate[rank_key] = rank
        candidate["rrf_score"] += 1.0 / (rrf_k + rank)
        candidate[f"{backend}_score"] = float(hit.get("score", 0.0) or 0.0)
        if backend == "semantic":
            candidate["semantic_distance"] = hit.get("distance")


def _public_hit(candidate: dict[str, Any]) -> dict[str, Any]:
    hit = dict(candidate["base_hit"])
    hybrid_score = float(candidate["rrf_score"])
    hit["score"] = hybrid_score
    hit["hybrid_score"] = hybrid_score
    hit["hybrid_candidate_id"] = candidate["key"]
    hit["matched_backends"] = sorted(candidate["matched_backends"])
    for key in (
        "fts_rank",
        "fts_score",
        "semantic_rank",
        "semantic_score",
        "semantic_distance",
    ):
        if key in candidate:
            hit[key] = candidate[key]
    return hit


def _candidate_key(backend: str, hit: dict[str, Any]) -> str:
    chunk_id = hit.get("chunk_id")
    if chunk_id:
        return str(chunk_id)
    parts = [
        backend,
        str(hit.get("scope_id") or ""),
        str(hit.get("doc_id") or ""),
        str(hit.get("object_id") or ""),
        str(hit.get("relative_path") or ""),
        str(hit.get("title") or ""),
    ]
    return ":".join(parts)


def _backend_status(
    fts_result: dict[str, Any], semantic_result: dict[str, Any]
) -> dict[str, Any]:
    results = [fts_result, semantic_result]
    statuses = [str(result.get("status", "failed")) for result in results]
    indexes_searched = sum(_count(result, "indexes_searched") for result in results)
    ok_or_partial = {"ok", "partial"}
    if not any(status in ok_or_partial for status in statuses):
        return {"status": "failed", "indexes_searched": indexes_searched}
    if any(status not in ok_or_partial or status == "partial" for status in statuses):
        return {"status": "partial", "indexes_searched": indexes_searched}
    return {"status": "ok", "indexes_searched": indexes_searched}


def _backend_failures(backend: str, result: dict[str, Any]) -> list[dict[str, Any]]:
    failures = [
        dict(failure, backend=backend) for failure in result.get("failures", [])[:10]
    ]
    if result.get("status") not in {"ok", "partial"}:
        failures.append(
            {
                "backend": backend,
                "error_kind": result.get("error_kind", "backend_unavailable"),
                "message": result.get("message", ""),
            }
        )
    return failures


def _count(result: dict[str, Any], key: str) -> int:
    return int(result.get("counts", {}).get(key, 0) or 0)


def _rerank_with_ollama(
    *,
    query: str,
    hits: list[dict[str, Any]],
    model: str | None,
    base_url: str,
) -> dict[str, Any]:
    resolved_model = model or os.environ.get("AGENTS_DOCS_OLLAMA_RERANK_MODEL")
    if not resolved_model:
        return _rerank_report(
            "failed",
            error_kind="ollama_model_missing",
            mode="ollama",
            message=(
                "Pass --ollama-model or set AGENTS_DOCS_OLLAMA_RERANK_MODEL for "
                "optional local Ollama reranking."
            ),
        )

    endpoint = _ollama_generate_endpoint(base_url)
    if endpoint["status"] != "ok":
        return _rerank_report(
            "failed",
            error_kind=endpoint["error_kind"],
            mode="ollama",
            model=resolved_model,
            message=endpoint.get("message", ""),
        )

    candidate_rows = [_rerank_candidate(hit) for hit in hits]
    payload = {
        "model": resolved_model,
        "stream": False,
        "format": "json",
        "options": {"temperature": 0},
        "prompt": _ollama_prompt(query, candidate_rows),
    }
    try:
        request = Request(
            str(endpoint["url"]),
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=45) as response:  # noqa: S310 local-only
            body = json.loads(response.read().decode("utf-8"))
        ranking = _parse_ranking(body.get("response", ""))
        reranked_hits = _apply_ranking(hits, ranking, resolved_model)
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        return _rerank_report(
            "failed",
            error_kind="ollama_unavailable",
            mode="ollama",
            model=resolved_model,
            message=exc.__class__.__name__,
        )
    except (json.JSONDecodeError, ValueError) as exc:
        return _rerank_report(
            "failed",
            error_kind="ollama_ranking_parse_failed",
            mode="ollama",
            model=resolved_model,
            message=exc.__class__.__name__,
        )

    return _rerank_report(
        "ok",
        mode="ollama",
        model=resolved_model,
        candidate_count=len(hits),
        ranked_candidate_count=len(ranking),
        hits=reranked_hits,
    )


def _ollama_generate_endpoint(base_url: str) -> dict[str, Any]:
    normalized = base_url if "://" in base_url else f"http://{base_url}"
    parsed = urlparse(normalized)
    host = parsed.hostname or ""
    if host.lower() not in {"localhost", "127.0.0.1", "::1"}:
        return {
            "status": "failed",
            "error_kind": "nonlocal_rerank_endpoint",
            "message": "Ollama reranking only accepts localhost endpoints.",
        }
    if parsed.scheme not in {"http", "https"}:
        return {
            "status": "failed",
            "error_kind": "unsupported_rerank_endpoint_scheme",
            "message": "Ollama reranking expects an HTTP localhost endpoint.",
        }
    url = normalized.rstrip("/")
    if not url.endswith("/api/generate"):
        url = f"{url}/api/generate"
    return {"status": "ok", "url": url}


def _rerank_candidate(hit: dict[str, Any]) -> dict[str, str]:
    return {
        "id": _hit_id(hit),
        "path": str(hit.get("relative_path") or ""),
        "title": str(hit.get("title") or ""),
        "text": " ".join(str(hit.get("body_preview") or "").split())[:700],
    }


def _ollama_prompt(query: str, candidates: list[dict[str, str]]) -> str:
    return (
        "You are reranking local document search results. "
        "Return strict JSON only, with this shape: "
        '{"ranking":["candidate_id_1","candidate_id_2"]}. '
        "Use only candidate IDs from the input. Rank by relevance to the query.\n\n"
        f"Query: {query}\n\n"
        f"Candidates:\n{json.dumps(candidates, ensure_ascii=True, indent=2)}"
    )


def _parse_ranking(response_text: str) -> list[str]:
    parsed = json.loads(response_text)
    raw: Any
    if isinstance(parsed, list):
        raw = parsed
    elif isinstance(parsed, dict):
        raw = (
            parsed.get("ranking")
            or parsed.get("ordered_ids")
            or parsed.get("ids")
            or []
        )
    else:
        raw = []
    ranking: list[str] = []
    for item in raw:
        if isinstance(item, str):
            ranking.append(item)
        elif isinstance(item, dict) and item.get("id"):
            ranking.append(str(item["id"]))
    if not ranking:
        raise ValueError("empty_ranking")
    return ranking


def _apply_ranking(
    hits: list[dict[str, Any]], ranking: list[str], model: str
) -> list[dict[str, Any]]:
    hit_by_id = {_hit_id(hit): hit for hit in hits}
    ordered: list[dict[str, Any]] = []
    seen: set[str] = set()
    for candidate_id in ranking:
        if candidate_id in seen or candidate_id not in hit_by_id:
            continue
        seen.add(candidate_id)
        ordered.append(hit_by_id[candidate_id])
    ordered.extend(hit for hit in hits if _hit_id(hit) not in seen)

    reranked: list[dict[str, Any]] = []
    for index, hit in enumerate(ordered, start=1):
        updated = dict(hit)
        if _hit_id(hit) in seen:
            updated["rerank_rank"] = index
            updated["rerank_score"] = 1.0 / index
            updated["score"] = updated["rerank_score"]
        updated["rerank_provider"] = "ollama"
        updated["rerank_model"] = model
        reranked.append(updated)
    return reranked


def _hit_id(hit: dict[str, Any]) -> str:
    return str(hit.get("chunk_id") or hit.get("hybrid_candidate_id") or "")


def _rerank_report(status: str, **extra: Any) -> dict[str, Any]:
    report = {"status": status, "mode": extra.pop("mode", "none")}
    report.update(extra)
    return report
