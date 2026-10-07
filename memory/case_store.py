"""Long-term case memory backed by data/memory/cases.json.

Sprint 6: semantic (vector) search when an index is available, with keyword
fallback for empty results / missing index / USE_VECTOR_MEMORY=0.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from memory.vector_store import VectorStore

DEFAULT_CASES_PATH = (
    Path(__file__).resolve().parents[1] / "data" / "memory" / "cases.json"
)


def _vector_enabled() -> bool:
    """Default ON; set USE_VECTOR_MEMORY=0 to force keyword-only."""
    raw = os.getenv("USE_VECTOR_MEMORY", "1").strip().lower()
    return raw not in {"0", "false", "no", "off"}


class CaseStore:
    """Keyword and asset_id search over resolved incident cases."""

    def __init__(
        self,
        cases_path: Path | None = None,
        *,
        vector_store: VectorStore | None = None,
        auto_vector: bool = True,
    ) -> None:
        self.cases_path = cases_path or DEFAULT_CASES_PATH
        self._cases: list[dict[str, Any]] | None = None
        self._vector_store = vector_store
        self._auto_vector = auto_vector

    @classmethod
    def default(cls) -> CaseStore:
        return cls()

    def load(self) -> list[dict[str, Any]]:
        if self._cases is None:
            with open(self.cases_path, encoding="utf-8") as f:
                self._cases = json.load(f)
        return self._cases

    def reload(self) -> list[dict[str, Any]]:
        self._cases = None
        self._vector_store = None
        return self.load()

    def get_by_asset_id(self, asset_id: str) -> list[dict[str, Any]]:
        asset_id = asset_id.strip().upper()
        return [c for c in self.load() if c.get("asset_id", "").upper() == asset_id]

    def search_by_keywords(
        self,
        keywords: list[str],
        *,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        if not keywords:
            return []

        normalized = [kw.strip().lower() for kw in keywords if kw.strip()]
        scored: list[tuple[int, dict[str, Any]]] = []

        for case in self.load():
            haystack = " ".join(
                [
                    case.get("summary", ""),
                    case.get("resolution", ""),
                    case.get("case_type", ""),
                    case.get("alarm_type", ""),
                    " ".join(case.get("keywords", [])),
                ]
            ).lower()
            score = sum(1 for kw in normalized if kw in haystack)
            if score > 0:
                scored.append((score, case))

        scored.sort(key=lambda item: item[0], reverse=True)
        return [case for _, case in scored[:limit]]

    def _ensure_vector_store(self) -> VectorStore | None:
        if not _vector_enabled():
            return None
        if self._vector_store is not None:
            return self._vector_store
        if not self._auto_vector:
            return None
        loaded = VectorStore.try_load()
        if loaded is not None and loaded.size > 0:
            self._vector_store = loaded
            return loaded
        # Build ephemeral index from JSON cases (no disk write required for tools).
        self._vector_store = VectorStore.from_cases(self.load())
        return self._vector_store

    def search_semantic(
        self,
        query: str,
        *,
        limit: int = 3,
        min_score: float = 0.05,
    ) -> list[dict[str, Any]]:
        """Vector retrieval; empty list when disabled / unavailable."""
        store = self._ensure_vector_store()
        if store is None:
            return []
        return [case for _, case in store.search(query, limit=limit, min_score=min_score)]

    def search_similar(
        self,
        *,
        asset_id: str | None = None,
        keywords: list[str] | None = None,
        query: str | None = None,
        limit: int = 3,
        prefer_vector: bool | None = None,
    ) -> list[dict[str, Any]]:
        """Rank cases by semantic similarity when possible, else keyword/asset.

        ``prefer_vector`` defaults to USE_VECTOR_MEMORY. When vector returns
        nothing, falls back to the V1 keyword/asset ranking path.
        """
        use_vector = _vector_enabled() if prefer_vector is None else prefer_vector
        query_text = (query or "").strip()
        if not query_text and keywords:
            query_text = " ".join(keywords)

        if use_vector and query_text:
            semantic = self.search_semantic(query_text, limit=limit)
            if asset_id:
                # Exact asset matches first, then semantic neighbors.
                asset_hits = self.get_by_asset_id(asset_id)
                if asset_hits:
                    merged: list[dict[str, Any]] = []
                    seen: set[str] = set()
                    for case in asset_hits:
                        if case["case_id"] not in seen:
                            merged.append(case)
                            seen.add(case["case_id"])
                    for case in semantic:
                        if case["case_id"] not in seen:
                            merged.append(case)
                            seen.add(case["case_id"])
                    return merged[:limit]
            if semantic:
                return semantic[:limit]

        # Keyword / asset fallback (V1 behavior)
        scored: dict[str, tuple[int, dict[str, Any]]] = {}

        if asset_id:
            for case in self.get_by_asset_id(asset_id):
                scored[case["case_id"]] = (100, case)

        if keywords:
            for idx, case in enumerate(
                self.search_by_keywords(keywords, limit=len(self.load()))
            ):
                bonus = max(1, 10 - idx)
                current = scored.get(case["case_id"], (0, case))
                scored[case["case_id"]] = (current[0] + bonus, case)

        if not scored and not asset_id and not keywords:
            return []

        ranked = sorted(scored.values(), key=lambda item: item[0], reverse=True)
        return [case for _, case in ranked[:limit]]
