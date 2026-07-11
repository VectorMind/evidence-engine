"""Milestone 0 deterministic evaluation baseline runner.

See ``evaluation/README.md`` for the fixture/query/judgment format this reads
and why the runner avoids Docling and networked embedding models. Produces
``evaluation/reports/milestone0-baseline.json``.

Usage::

    python evaluation/runners/run_milestone0_baseline.py
"""

from __future__ import annotations

import importlib.util  # noqa: F401 -- even.semantic uses importlib.util without importing the submodule itself
import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

DATASET_ROOT = REPO_ROOT / "evaluation" / "datasets" / "milestone0"
QUERIES_PATH = REPO_ROOT / "evaluation" / "queries" / "milestone0.json"
JUDGMENTS_PATH = REPO_ROOT / "evaluation" / "judgments" / "milestone0.json"
REPORT_PATH = REPO_ROOT / "evaluation" / "reports" / "milestone0-baseline.json"

VOCAB = (
    "northwind", "drifter", "salvage", "reef", "point", "permit", "sl-2210",
    "harbor", "authority", "sign-off", "captain", "vasquez", "manifest",
    "containment", "breach", "renewal", "warden", "whitfield",
)


def _fake_vector(text: str) -> list[float]:
    lowered = str(text).lower()
    raw = [1.0 if term in lowered else 0.0 for term in VOCAB]
    norm = sum(value * value for value in raw) ** 0.5 or 1.0
    return [value / norm for value in raw]


def _fake_summary(prompt: str, **_: object) -> str:
    lowered = prompt.lower()
    for term in VOCAB:
        if term in lowered:
            return f"{term} record root"
    return "generic document root"


def _seed_root(root_path: Path) -> None:
    from even.inventory import ScanOptions, scan_folder_to_catalog
    from even.parse import _stable_id, _write_parsed_document
    from even.paths import catalog_path

    scan = scan_folder_to_catalog(
        root_path, ScanOptions(max_files=None, max_bytes=None, max_depth=None)
    )
    assert scan["status"] == "ok", scan

    with sqlite3.connect(catalog_path()) as conn:
        rows = conn.execute(
            """
            SELECT source_item_id, relative_path, source_sha256
            FROM source_items
            WHERE root_id = ? AND item_kind = 'file'
            """,
            (scan["root_id"],),
        ).fetchall()

    for source_item_id, relative_path, source_sha256 in rows:
        text = (root_path / relative_path).read_text(encoding="utf-8")
        doc_id = _stable_id("doc", source_item_id)
        _write_parsed_document(
            source_item_id=source_item_id,
            doc_id=doc_id,
            source_sha256=source_sha256,
            parser_profile="docling_default",
            title=Path(relative_path).stem,
            text_preview=text,
            payload=text.encode("utf-8"),
            now="2026-07-10T00:00:00Z",
        )


def _build_indexes(root_paths: list[Path]) -> dict[str, Any]:
    from even.fts import IndexOptions, index_scope_to_fts
    from even.routing import RoutingIndexOptions, index_routing
    from even.semantic import SemanticIndexOptions, index_scope_to_semantic

    report: dict[str, Any] = {"fts": [], "semantic": [], "routing": []}
    for root in root_paths:
        fts_result = index_scope_to_fts(root, IndexOptions(force=True))
        report["fts"].append({"root": root.name, "status": fts_result["status"]})
        assert fts_result["status"] == "ok", fts_result

    semantic_result = index_scope_to_semantic(root_paths[0], SemanticIndexOptions(force=True))
    semantic_available = semantic_result.get("status") not in {"failed"} or (
        semantic_result.get("error_kind") != "semantic_dependencies_missing"
    )
    if semantic_result.get("error_kind") == "semantic_dependencies_missing":
        semantic_available = False
    report["semantic"].append({"root": root_paths[0].name, **semantic_result})
    if semantic_available:
        for root in root_paths[1:]:
            result = index_scope_to_semantic(root, SemanticIndexOptions(force=True))
            report["semantic"].append({"root": root.name, **result})

    for root in root_paths:
        routing_result = index_routing(
            root,
            RoutingIndexOptions(force=True, build_semantic=semantic_available),
            summary_generator=_fake_summary,
        )
        report["routing"].append({"root": root.name, "status": routing_result["status"]})

    report["semantic_available"] = semantic_available
    return report


def _hit_relative_paths(hits: list[dict[str, Any]]) -> list[str]:
    seen: list[str] = []
    for hit in hits:
        relative_path = hit.get("relative_path")
        if relative_path and relative_path not in seen:
            seen.append(relative_path)
    return seen


def _recall_at_k(ranked: list[str], relevant: set[str], k: int) -> float:
    if not relevant:
        return 0.0
    top_k = set(ranked[:k])
    return len(top_k & relevant) / len(relevant)


def _mrr(ranked: list[str], relevant: set[str]) -> float:
    for index, item in enumerate(ranked, start=1):
        if item in relevant:
            return 1.0 / index
    return 0.0


def _ndcg_at_k(ranked: list[str], relevant: set[str], k: int) -> float:
    import math

    dcg = 0.0
    for index, item in enumerate(ranked[:k], start=1):
        if item in relevant:
            dcg += 1.0 / math.log2(index + 1)
    ideal_hits = min(len(relevant), k)
    idcg = sum(1.0 / math.log2(index + 1) for index in range(1, ideal_hits + 1))
    return dcg / idcg if idcg > 0 else 0.0


def _score(ranked: list[str], relevant: set[str]) -> dict[str, float]:
    return {
        "recall_at_5": round(_recall_at_k(ranked, relevant, 5), 4),
        "recall_at_20": round(_recall_at_k(ranked, relevant, 20), 4),
        "ndcg_at_10": round(_ndcg_at_k(ranked, relevant, 10), 4),
        "mrr": round(_mrr(ranked, relevant), 4),
    }


def _run_queries(queries: list[dict[str, Any]], judgments: dict[str, list[str]]) -> dict[str, Any]:
    from even.fts import SearchOptions, search_all_text_indexes, search_text_indexes
    from even.hybrid import HybridSearchOptions, search_hybrid_indexes

    per_query: list[dict[str, Any]] = []
    for query in queries:
        query_id = query["query_id"]
        text = query["text"]
        relevant = set(judgments.get(query_id, []))

        exhaustive = search_all_text_indexes(text, SearchOptions(limit=20, routed=False))
        routed: dict[str, Any] = {}
        for budget in ("low", "mid", "high"):
            result = search_text_indexes(text, SearchOptions(limit=20, routed=True, budget=budget))
            routed[budget] = {
                "hits": _hit_relative_paths(result.get("hits", [])),
                "route_status": (result.get("route_trace") or {}).get("status"),
                **_score(_hit_relative_paths(result.get("hits", [])), relevant),
            }
        hybrid = search_hybrid_indexes(text, HybridSearchOptions(limit=20))

        exhaustive_ranked = _hit_relative_paths(exhaustive.get("hits", []))
        hybrid_ranked = _hit_relative_paths(hybrid.get("hits", []))

        per_query.append(
            {
                "query_id": query_id,
                "text": text,
                "scopes_expected": query.get("scopes_expected", []),
                "relevant": sorted(relevant),
                "exhaustive": {"hits": exhaustive_ranked, **_score(exhaustive_ranked, relevant)},
                "routed": routed,
                "hybrid": {"hits": hybrid_ranked, **_score(hybrid_ranked, relevant)},
            }
        )
    return {"queries": per_query}


def main() -> None:
    queries = json.loads(QUERIES_PATH.read_text(encoding="utf-8"))
    judgments = json.loads(JUDGMENTS_PATH.read_text(encoding="utf-8"))
    root_paths = sorted(p for p in DATASET_ROOT.iterdir() if p.is_dir())
    assert root_paths, f"No fixture roots found under {DATASET_ROOT}"

    with tempfile.TemporaryDirectory(prefix="even-eval-milestone0-") as tmp:
        os.environ["EVEN_CACHE"] = str(Path(tmp) / ".cache")
        os.environ.pop("EVEN_HOME", None)

        import even.semantic as semantic_module

        semantic_module._embed_passages = lambda profile, texts: [_fake_vector(t) for t in texts]
        semantic_module._embed_query = lambda profile, text: _fake_vector(text)

        for root in root_paths:
            _seed_root(root)
        index_report = _build_indexes(root_paths)
        query_report = _run_queries(queries, judgments)

    report = {
        "dataset": "milestone0",
        "roots": [root.name for root in root_paths],
        "index_build": index_report,
        **query_report,
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote {REPORT_PATH.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
