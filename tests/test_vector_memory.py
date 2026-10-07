"""Vector memory + retrieval quality tests (Sprint 6)."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from eval_harness.metrics.retrieval_scorer import (
    build_retrieval_report,
    compare_keyword_vs_vector,
    downstream_groundedness,
    query_keywords,
    recall_at_k,
)
from memory.case_store import CaseStore
from memory.embeddings import embed_text, embed_texts, expand_query
from memory.tools import search_similar_cases
from memory.vector_store import VectorStore

ROOT = Path(__file__).resolve().parents[1]
RETRIEVAL_CASES = ROOT / "eval_harness" / "golden_dataset" / "retrieval_cases.json"


@pytest.fixture(autouse=True)
def _vector_on(monkeypatch):
    monkeypatch.setenv("USE_VECTOR_MEMORY", "1")
    monkeypatch.delenv("USE_VERTEX_EMBEDDINGS", raising=False)


def test_embed_texts_batch_and_single_shape():
    batch = embed_texts(["filter pressure", "low airflow"])
    assert batch.shape == (2, 384)
    assert abs(float(np.linalg.norm(batch[0])) - 1.0) < 1e-5
    single = embed_text("filter pressure")
    assert single.shape == (384,)


def test_expand_query_adds_domain_synonyms():
    expanded = expand_query("clogged filter").lower()
    assert "pressure" in expanded or "dirty" in expanded


def test_vector_store_build_search_persist(tmp_path):
    store = CaseStore.default()
    cases = store.load()
    vs = VectorStore.from_cases(cases, index_dir=tmp_path, persist=True)
    assert (tmp_path / "cases.faiss").exists()
    assert vs.size == len(cases)

    loaded = VectorStore(index_dir=tmp_path)
    loaded.load()
    hits = loaded.search("recurring filter pressure AHU", limit=2)
    assert hits
    assert hits[0][1]["case_id"] in {"case_001", "case_002"}


def test_vector_store_incremental_add(tmp_path):
    vs = VectorStore(index_dir=tmp_path)
    vs.build([])
    vs.add(
        {
            "case_id": "case_x",
            "asset_id": "AHU-9F-01",
            "summary": "Unique zebra damper failure",
            "keywords": ["zebra", "damper"],
        }
    )
    hits = vs.search("zebra damper", limit=1)
    assert hits and hits[0][1]["case_id"] == "case_x"


def test_keyword_fallback_when_vector_disabled(monkeypatch):
    monkeypatch.setenv("USE_VECTOR_MEMORY", "0")
    store = CaseStore.default()
    cases = store.search_similar(asset_id="AHU-3F-01", limit=2)
    assert cases[0]["case_id"] == "case_002"


def test_semantic_beats_keyword_overlap_gap():
    """Paraphrase without corpus token 'clogged' still retrieves filter case."""
    store = CaseStore.default()
    keyword_only = store.search_by_keywords(["clogged"], limit=3)
    assert keyword_only == []

    semantic = store.search_similar(
        query="clogged AHU filter making building overheat",
        limit=3,
        prefer_vector=True,
    )
    assert any(c["case_id"] == "case_001" for c in semantic)


def test_search_similar_cases_tool_accepts_query():
    result = search_similar_cases(
        query="conference room weak airflow actuator",
        limit=2,
    )
    assert result["match_count"] >= 1
    assert result["cases"][0]["case_id"] == "case_003"


def test_recall_at_k_helper():
    assert recall_at_k(["a", "b", "c"], ["b"], k=3) == 1.0
    assert recall_at_k(["a", "b"], ["c"], k=2) == 0.0


def test_retrieval_golden_cases_pass():
    cases = json.loads(RETRIEVAL_CASES.read_text(encoding="utf-8"))
    store = CaseStore.default()
    by_id = {str(c["case_id"]): c for c in store.load()}
    scores = []
    for case in cases:
        k = int(case.get("k", 3))
        min_score = 0.08
        if case.get("allow_empty") or case.get("must_not_retrieve"):
            min_score = 0.35
        vector_hits = store.search_semantic(case["query"], limit=k, min_score=min_score)
        keywords = query_keywords(case["query"])
        keyword_hits = store.search_by_keywords(keywords, limit=k) if keywords else []
        relevant_cases = [
            by_id[cid]
            for cid in (case.get("relevant_case_ids") or [])
            if cid in by_id
        ]
        scores.append(
            compare_keyword_vs_vector(
                case=case,
                vector_hits=vector_hits,
                keyword_hits=keyword_hits,
                relevant_cases=relevant_cases,
                k=k,
            )
        )

    report = build_retrieval_report(scores, k=3)
    assert report["case_count"] == len(cases)
    failed = [c for c in scores if not c["pass"]]
    assert not failed, f"retrieval failures: {failed}"
    assert report["avg_recall_at_k"] is not None
    assert report["avg_recall_at_k"] >= 0.8
    assert report["avg_groundedness_vector"] is not None
    assert report["avg_groundedness_keyword"] is not None
    assert report["groundedness_delta"] is not None
    assert report["groundedness_delta"] >= 0.0


def test_downstream_groundedness_empty_retrieval_is_zero():
    gold = {
        "case_id": "case_001",
        "asset_id": "AHU-2F-01",
        "policy_id": "HVAC-MNT-001",
        "work_order_id": "WO-2026-0110",
        "keywords": ["filter"],
    }
    assert downstream_groundedness([], [gold]) == 0.0
    assert downstream_groundedness([gold], [gold]) == 1.0
