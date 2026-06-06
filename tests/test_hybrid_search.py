from __future__ import annotations

from agents_cli.hybrid import _fuse_hits, _ollama_generate_endpoint


def test_rrf_fuses_shared_chunk_from_fts_and_semantic() -> None:
    hits = _fuse_hits(
        [
            {
                "score": 12.0,
                "chunk_id": "shared",
                "title": "Shared",
                "body_preview": "lexical match",
            },
            {"score": 8.0, "chunk_id": "fts-only", "title": "FTS"},
        ],
        [
            {"score": 0.9, "distance": 0.1, "chunk_id": "semantic-only"},
            {"score": 0.8, "distance": 0.2, "chunk_id": "shared"},
        ],
        rrf_k=60,
    )

    shared = next(hit for hit in hits if hit["chunk_id"] == "shared")

    assert shared["matched_backends"] == ["fts", "semantic"]
    assert shared["fts_rank"] == 1
    assert shared["semantic_rank"] == 2
    assert shared["fts_score"] == 12.0
    assert shared["semantic_score"] == 0.8
    assert shared["semantic_distance"] == 0.2
    assert shared["hybrid_score"] > hits[-1]["hybrid_score"]


def test_ollama_rerank_endpoint_must_be_localhost() -> None:
    assert _ollama_generate_endpoint("http://localhost:11434") == {
        "status": "ok",
        "url": "http://localhost:11434/api/generate",
    }

    remote = _ollama_generate_endpoint("https://example.com")

    assert remote["status"] == "failed"
    assert remote["error_kind"] == "nonlocal_rerank_endpoint"
