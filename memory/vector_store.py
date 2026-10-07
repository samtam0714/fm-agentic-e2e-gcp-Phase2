"""FAISS-backed vector index for resolved cases (Sprint 6 / 2.6.2)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import faiss

from memory.embeddings import DEFAULT_DIM, case_to_text, embed_text, embed_texts

DEFAULT_INDEX_DIR = (
    Path(__file__).resolve().parents[1] / "data" / "memory" / "vector_index"
)


class VectorStore:
    """Flat IP (cosine) FAISS index with case_id metadata sidecars."""

    def __init__(
        self,
        *,
        index_dir: Path | None = None,
        dim: int = DEFAULT_DIM,
    ) -> None:
        self.index_dir = index_dir or DEFAULT_INDEX_DIR
        self.dim = dim
        self._index: faiss.IndexFlatIP | None = None
        self._ids: list[str] = []
        self._cases: dict[str, dict[str, Any]] = {}

    @property
    def size(self) -> int:
        return len(self._ids)

    def build(self, cases: list[dict[str, Any]]) -> None:
        """Rebuild index from scratch (batch embed)."""
        self._ids = []
        self._cases = {}
        if not cases:
            self._index = faiss.IndexFlatIP(self.dim)
            return

        texts = [case_to_text(c) for c in cases]
        matrix = embed_texts(texts, dim=self.dim)
        self._index = faiss.IndexFlatIP(self.dim)
        self._index.add(matrix)
        for case in cases:
            cid = str(case["case_id"])
            self._ids.append(cid)
            self._cases[cid] = case

    def add(self, case: dict[str, Any]) -> None:
        """Incremental insert (or replace if case_id already indexed)."""
        cid = str(case["case_id"])
        if cid in self._cases:
            # Rebuild to keep FAISS row order aligned with ids (small corpora).
            remaining = [c for c in self._cases.values() if c["case_id"] != cid]
            remaining.append(case)
            self.build(remaining)
            return

        if self._index is None:
            self.build([case])
            return

        vec = embed_text(case_to_text(case), dim=self.dim).reshape(1, -1)
        self._index.add(vec)
        self._ids.append(cid)
        self._cases[cid] = case

    def search(
        self,
        query: str,
        *,
        limit: int = 3,
        min_score: float = 0.05,
    ) -> list[tuple[float, dict[str, Any]]]:
        """Return (score, case) pairs ranked by cosine similarity."""
        if self._index is None or self.size == 0 or not (query or "").strip():
            return []

        q = embed_text(query, dim=self.dim).reshape(1, -1)
        k = min(limit, self.size)
        scores, indices = self._index.search(q, k)
        hits: list[tuple[float, dict[str, Any]]] = []
        for score, idx in zip(scores[0].tolist(), indices[0].tolist(), strict=True):
            if idx < 0 or idx >= len(self._ids):
                continue
            if float(score) < min_score:
                continue
            case = self._cases[self._ids[idx]]
            hits.append((float(score), case))
        return hits

    def save(self, index_dir: Path | None = None) -> Path:
        dest = index_dir or self.index_dir
        dest.mkdir(parents=True, exist_ok=True)
        if self._index is None:
            self._index = faiss.IndexFlatIP(self.dim)
        faiss.write_index(self._index, str(dest / "cases.faiss"))
        meta = {
            "dim": self.dim,
            "ids": self._ids,
            "cases": [self._cases[i] for i in self._ids],
        }
        (dest / "meta.json").write_text(
            json.dumps(meta, indent=2) + "\n", encoding="utf-8"
        )
        return dest

    def load(self, index_dir: Path | None = None) -> None:
        src = index_dir or self.index_dir
        index_path = src / "cases.faiss"
        meta_path = src / "meta.json"
        if not index_path.exists() or not meta_path.exists():
            raise FileNotFoundError(f"vector index not found under {src}")
        self._index = faiss.read_index(str(index_path))
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        self.dim = int(meta.get("dim", self.dim))
        self._ids = list(meta.get("ids") or [])
        self._cases = {str(c["case_id"]): c for c in meta.get("cases") or []}

    @classmethod
    def from_cases(
        cls,
        cases: list[dict[str, Any]],
        *,
        index_dir: Path | None = None,
        persist: bool = False,
    ) -> VectorStore:
        store = cls(index_dir=index_dir)
        store.build(cases)
        if persist:
            store.save()
        return store

    @classmethod
    def try_load(cls, index_dir: Path | None = None) -> VectorStore | None:
        store = cls(index_dir=index_dir)
        try:
            store.load()
            return store
        except FileNotFoundError:
            return None
