"""Retrieval-quality metrics for vector memory eval (Sprint 6 / 2.6.5).

Reports Recall@K, graded relevance, and a keyword-vs-vector downstream
groundedness delta (evidence from gold cases present in retrieved hits).
"""

from __future__ import annotations

from typing import Any

from memory.embeddings import case_to_text, tokenize_query


def recall_at_k(
    retrieved_ids: list[str],
    relevant_ids: list[str],
    *,
    k: int = 3,
) -> float:
    """Fraction of relevant ids found in the top-k retrieved list."""
    if not relevant_ids:
        return 1.0
    top = set(retrieved_ids[:k])
    hits = sum(1 for rid in relevant_ids if rid in top)
    return hits / len(relevant_ids)


def mean_relevance(
    retrieved_ids: list[str],
    relevance: dict[str, float],
    *,
    k: int = 3,
) -> float:
    """Average graded relevance of top-k hits (missing -> 0)."""
    if k <= 0:
        return 0.0
    top = retrieved_ids[:k]
    if not top:
        return 0.0
    return sum(float(relevance.get(cid, 0.0)) for cid in top) / len(top)


def query_keywords(query: str) -> list[str]:
    """Keyword-baseline tokens: surface form only, no synonym expansion."""
    return tokenize_query(query)


def case_evidence_tokens(case: dict[str, Any]) -> list[str]:
    """Facts a downstream answer could cite from a gold similar-case."""
    parts: list[str] = []
    for key in ("asset_id", "policy_id", "work_order_id", "alarm_type"):
        value = case.get(key)
        if value:
            parts.append(str(value))
    parts.extend(str(k) for k in (case.get("keywords") or []) if k)
    seen: list[str] = []
    for part in parts:
        token = part.strip().lower()
        if token and token not in seen:
            seen.append(token)
    return seen


def downstream_groundedness(
    retrieved_cases: list[dict[str, Any]],
    relevant_cases: list[dict[str, Any]],
    *,
    banned_ids: list[str] | None = None,
) -> float:
    """Share of gold-case evidence present in retrieved hits.

    Empty relevant set (abstain / unrelated query): 1.0 if no banned ids
    were retrieved, else 0.0. Retrieval-layer proxy, not an LLM judge score.
    """
    if not relevant_cases:
        if not banned_ids:
            return 1.0
        retrieved_ids = {str(c.get("case_id")) for c in retrieved_cases}
        return 0.0 if retrieved_ids & set(banned_ids) else 1.0

    evidence: list[str] = []
    for gold in relevant_cases:
        evidence.extend(case_evidence_tokens(gold))
    evidence = list(dict.fromkeys(evidence))
    if not evidence:
        return 1.0 if retrieved_cases else 0.0

    haystack = " ".join(case_to_text(c) for c in retrieved_cases).lower()
    hits = sum(1 for token in evidence if token in haystack)
    return hits / len(evidence)


def score_retrieval_case(
    case: dict[str, Any],
    retrieved_ids: list[str],
    *,
    k: int = 3,
) -> dict[str, Any]:
    """Score one retrieval golden case."""
    relevant = list(case.get("relevant_case_ids") or [])
    graded = {
        str(item["case_id"]): float(item.get("relevance", 1.0))
        for item in case.get("graded_relevance") or []
        if item.get("case_id")
    }
    for rid in relevant:
        graded.setdefault(rid, 1.0)

    r_at_k = recall_at_k(retrieved_ids, relevant, k=k)
    relevance = mean_relevance(retrieved_ids, graded, k=k)
    must_not = set(case.get("must_not_retrieve") or [])
    banned_hits = [cid for cid in retrieved_ids[:k] if cid in must_not]
    passed = r_at_k >= float(case.get("min_recall_at_k", 1.0)) and not banned_hits

    return {
        "case_id": case.get("case_id"),
        "pass": passed,
        "recall_at_k": round(r_at_k, 4),
        "mean_relevance": round(relevance, 4),
        "retrieved_ids": retrieved_ids[:k],
        "relevant_case_ids": relevant,
        "banned_hits": banned_hits,
        "k": k,
    }


def compare_keyword_vs_vector(
    *,
    case: dict[str, Any],
    vector_hits: list[dict[str, Any]],
    keyword_hits: list[dict[str, Any]],
    relevant_cases: list[dict[str, Any]],
    k: int = 3,
) -> dict[str, Any]:
    """Attach keyword-baseline recall and groundedness delta to a vector score."""
    vector_ids = [str(c["case_id"]) for c in vector_hits]
    keyword_ids = [str(c["case_id"]) for c in keyword_hits]
    banned = list(case.get("must_not_retrieve") or [])
    scored = score_retrieval_case(case, vector_ids, k=k)
    keyword_scored = score_retrieval_case(case, keyword_ids, k=k)
    vector_g = downstream_groundedness(
        vector_hits[:k], relevant_cases, banned_ids=banned
    )
    keyword_g = downstream_groundedness(
        keyword_hits[:k], relevant_cases, banned_ids=banned
    )
    scored["keyword_recall_at_k"] = keyword_scored["recall_at_k"]
    scored["keyword_retrieved_ids"] = keyword_ids[:k]
    scored["groundedness_vector"] = round(vector_g, 4)
    scored["groundedness_keyword"] = round(keyword_g, 4)
    scored["groundedness_delta"] = round(vector_g - keyword_g, 4)
    return scored


def build_retrieval_report(
    case_scores: list[dict[str, Any]],
    *,
    k: int = 3,
) -> dict[str, Any]:
    """Aggregate retrieval eval scores, including keyword vs vector delta."""

    def _avg(key: str) -> float | None:
        values = [c[key] for c in case_scores if c.get(key) is not None]
        if not values:
            return None
        return round(sum(values) / len(values), 4)

    if not case_scores:
        return {
            "case_count": 0,
            "pass_count": 0,
            "pass_rate": 0.0,
            "avg_recall_at_k": None,
            "avg_mean_relevance": None,
            "avg_keyword_recall_at_k": None,
            "avg_groundedness_vector": None,
            "avg_groundedness_keyword": None,
            "groundedness_delta": None,
            "k": k,
            "cases": [],
        }

    recalls = [c["recall_at_k"] for c in case_scores]
    relevances = [c["mean_relevance"] for c in case_scores]
    pass_count = sum(1 for c in case_scores if c.get("pass"))
    vector_g = _avg("groundedness_vector")
    keyword_g = _avg("groundedness_keyword")
    delta = None
    if vector_g is not None and keyword_g is not None:
        delta = round(vector_g - keyword_g, 4)
    return {
        "case_count": len(case_scores),
        "pass_count": pass_count,
        "fail_count": len(case_scores) - pass_count,
        "pass_rate": round(pass_count / len(case_scores), 4),
        "avg_recall_at_k": round(sum(recalls) / len(recalls), 4),
        "avg_mean_relevance": round(sum(relevances) / len(relevances), 4),
        "avg_keyword_recall_at_k": _avg("keyword_recall_at_k"),
        "avg_groundedness_vector": vector_g,
        "avg_groundedness_keyword": keyword_g,
        "groundedness_delta": delta,
        "k": k,
        "cases": case_scores,
    }
