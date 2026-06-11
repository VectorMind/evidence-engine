"""Tests for the catalog Reference Contract helpers."""

from __future__ import annotations

from even.references import attach_hit_refs, evidence_ref


def test_evidence_ref_builds_dataset_table_row_coordinate() -> None:
    assert evidence_ref("document_objects", "obj_123") == (
        "corpus_cache.document_objects.obj_123"
    )


def test_attach_hit_refs_points_each_hit_at_its_object() -> None:
    payload = {"hits": [{"object_id": "obj_a"}, {"object_id": "obj_b"}]}

    attach_hit_refs(payload)

    assert payload["hits"][0]["ref"] == "corpus_cache.document_objects.obj_a"
    assert payload["hits"][1]["ref"] == "corpus_cache.document_objects.obj_b"


def test_attach_hit_refs_uses_null_when_object_id_missing() -> None:
    payload = {"hits": [{"object_id": None}, {"chunk_id": "chunk_only"}]}

    attach_hit_refs(payload)

    assert payload["hits"][0]["ref"] is None
    assert payload["hits"][1]["ref"] is None


def test_attach_hit_refs_tolerates_payload_without_hits() -> None:
    payload = {"status": "ok"}

    assert attach_hit_refs(payload) is payload
