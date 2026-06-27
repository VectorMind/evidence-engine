"""K-means / medoid math and media album clustering."""

from __future__ import annotations

import math
import os
from pathlib import Path
from typing import Any

from even.routing.shared import (
    _image_profile_name,
    _media_cluster_summary_id,
    _routing_defaults,
)


def _mean_vector(vectors: list[list[float]]) -> list[float]:
    import numpy as np  # type: ignore[import-not-found]

    arr = np.asarray(vectors, dtype=float)
    mean = arr.mean(axis=0)
    norm = float(np.linalg.norm(mean)) or 1.0
    return [float(value) for value in (mean / norm)]


def _media_cluster_k_max() -> int:
    env = os.environ.get("EVEN_MEDIA_CLUSTER_K_MAX")
    if env:
        try:
            return max(1, int(env))
        except ValueError:
            pass
    return max(1, int(_routing_defaults().get("media_cluster_k_max", 16)))


def _kmeans_medoids(
    vectors: list[list[float]], ids: list[str], *, k_max: int
) -> list[str]:
    """Pick k medoid ids by k-means over L2-normalized vectors (M1).

    medoid = the cluster member nearest its centroid. Deterministic (fixed seed).
    Returns a sorted, de-duplicated id list; empty when there is nothing to cluster.
    """

    n = len(vectors)
    if n == 0 or len(ids) != n:
        return []
    if n == 1:
        return [ids[0]]
    import numpy as np  # type: ignore[import-not-found]

    data = np.asarray(vectors, dtype=float)
    norms = np.linalg.norm(data, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    data = data / norms
    k = max(1, min(int(math.ceil(math.sqrt(n / 2))), int(k_max), n))
    if k == 1:
        centroid = data.mean(axis=0)
        return [ids[int(np.argmax(data @ centroid))]]

    import warnings

    from scipy.cluster.vq import kmeans2  # type: ignore[import-not-found]

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        centroids, labels = kmeans2(data, k, seed=0, minit="++", missing="warn")
    medoids: list[str] = []
    for cluster in range(len(centroids)):
        members = np.where(labels == cluster)[0]
        if members.size == 0:
            continue
        sims = data[members] @ centroids[cluster]
        medoids.append(ids[int(members[int(np.argmax(sims))])])
    return sorted(dict.fromkeys(medoids))


def _album_medoids(scope_id: str) -> dict[str, Any]:
    """The album's visual fingerprint: medoid asset ids over the per-scope image
    proof vectors (C2). Best-effort — empty when no image store exists yet, so the
    summary still lands without a visual fingerprint."""

    from even import image_index

    profile = _image_profile_name()
    vectors_by_asset = image_index.read_scope_image_vectors(scope_id, profile)
    if not vectors_by_asset:
        return {}
    ids = sorted(vectors_by_asset)
    vectors = [vectors_by_asset[asset_id]["vector"] for asset_id in ids]
    medoids = _kmeans_medoids(vectors, ids, k_max=_media_cluster_k_max())
    if not medoids:
        return {}
    return {"medoids": medoids, "medoid_profile": profile}


def _media_asset_clusters(
    scope_id: str, assets: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Group image assets by nearest SigLIP medoid for lower media representatives."""

    from even import image_index

    vectors_by_asset = image_index.read_scope_image_vectors(scope_id, _image_profile_name())
    if not vectors_by_asset:
        return []

    asset_by_id = {
        str(asset.get("asset_id")): asset
        for asset in assets
        if asset.get("asset_id") and str(asset.get("media_class") or "") == "image"
    }
    ids = sorted(asset_id for asset_id in asset_by_id if asset_id in vectors_by_asset)
    if not ids:
        return []

    vectors = [vectors_by_asset[asset_id]["vector"] for asset_id in ids]
    medoid_ids = _kmeans_medoids(vectors, ids, k_max=_media_cluster_k_max())
    if not medoid_ids:
        return []

    assignments = _assign_to_medoids(vectors_by_asset, ids, medoid_ids)
    clusters: list[dict[str, Any]] = []
    for medoid_id in medoid_ids:
        member_ids = assignments.get(medoid_id) or []
        members = [asset_by_id[asset_id] for asset_id in member_ids if asset_id in asset_by_id]
        if not members:
            continue
        medoid = asset_by_id.get(medoid_id) or members[0]
        clusters.append(
            {
                "summary_id": _media_cluster_summary_id(scope_id, medoid_id),
                "medoid_id": medoid_id,
                "medoid": medoid,
                "assets": sorted(
                    members,
                    key=lambda item: (
                        str(item.get("relative_path") or ""),
                        str(item.get("asset_id") or ""),
                    ),
                ),
                "title": _media_cluster_title(medoid),
            }
        )
    return sorted(clusters, key=lambda cluster: str(cluster["summary_id"]))


def _assign_to_medoids(
    vectors_by_asset: dict[str, dict[str, Any]],
    asset_ids: list[str],
    medoid_ids: list[str],
) -> dict[str, list[str]]:
    import numpy as np  # type: ignore[import-not-found]

    medoid_vectors = {
        medoid_id: _normalized_vector(vectors_by_asset[medoid_id]["vector"])
        for medoid_id in medoid_ids
        if medoid_id in vectors_by_asset
    }
    assignments: dict[str, list[str]] = {medoid_id: [] for medoid_id in medoid_vectors}
    for asset_id in asset_ids:
        vector = _normalized_vector(vectors_by_asset[asset_id]["vector"])
        best = sorted(
            (
                (float(np.dot(vector, medoid_vector)), medoid_id)
                for medoid_id, medoid_vector in medoid_vectors.items()
            ),
            key=lambda item: (-item[0], item[1]),
        )
        if best:
            assignments[best[0][1]].append(asset_id)
    return assignments


def _normalized_vector(vector: list[float]) -> Any:
    import numpy as np  # type: ignore[import-not-found]

    data = np.asarray(vector, dtype=float)
    norm = float(np.linalg.norm(data))
    if norm == 0:
        return data
    return data / norm


def _media_cluster_title(medoid: dict[str, Any]) -> str:
    path = str(medoid.get("relative_path") or medoid.get("asset_id") or "media cluster")
    stem = Path(path).stem.replace("_", " ").replace("-", " ").strip()
    return f"Media cluster: {stem or path}"


