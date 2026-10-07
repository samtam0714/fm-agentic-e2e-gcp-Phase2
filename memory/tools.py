"""Search long-term case history for similar past incidents."""

from __future__ import annotations

from memory.case_store import CaseStore


def search_similar_cases(
    asset_id: str | None = None,
    keywords: list[str] | None = None,
    query: str | None = None,
    limit: int = 3,
) -> dict:
    """Find similar resolved cases from institutional memory.

    Prefer a free-text ``query`` (semantic retrieval when vector memory is on).
    ``keywords`` / ``asset_id`` remain supported; keyword path is the fallback
    when vector search is disabled or returns nothing.
    """
    store = CaseStore.default()
    cases = store.search_similar(
        asset_id=asset_id,
        keywords=keywords,
        query=query,
        limit=limit,
    )
    return {
        "query": {
            "asset_id": asset_id,
            "keywords": keywords or [],
            "query": query,
            "limit": limit,
        },
        "match_count": len(cases),
        "cases": cases,
    }
