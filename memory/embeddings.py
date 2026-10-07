"""Text embedding pipeline for case memory (Sprint 6 / 2.6.1).

Default: offline hashing embedder (char/word n-grams + FM synonym expansion).
Optional: Vertex text embeddings when USE_VERTEX_EMBEDDINGS=1.
"""

from __future__ import annotations

import hashlib
import math
import os
import re
from collections.abc import Sequence

import numpy as np

DEFAULT_DIM = 384

# Domain expansions so synonym queries can match without shared surface tokens.
_SYNONYMS: dict[str, tuple[str, ...]] = {
    "clogged": ("filter", "pressure", "dirty", "blocked"),
    "blocked": ("filter", "clogged", "pressure"),
    "dirty": ("filter", "clogged", "pressure"),
    "overheating": ("temperature", "supply", "air", "temp", "high"),
    "overheat": ("temperature", "supply", "air", "temp", "high"),
    "hot": ("temperature", "supply", "air", "temp", "high"),
    "temperature": ("temp", "supply", "air"),
    "temp": ("temperature", "supply", "air"),
    "airflow": ("air", "flow", "vav", "low"),
    "draught": ("airflow", "air", "flow", "vav"),
    "actuator": ("vav", "airflow", "damper"),
    "recurring": ("repeated", "repeat", "history"),
    "repeated": ("recurring", "repeat", "history"),
    "spike": ("transient", "single", "monitor"),
    "transient": ("spike", "single", "monitor"),
}

_TOKEN_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*", re.IGNORECASE)


def _vertex_enabled() -> bool:
    return os.getenv("USE_VERTEX_EMBEDDINGS", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }


def tokenize_query(text: str) -> list[str]:
    """Split query into tokens with no synonym expansion (keyword-baseline path)."""
    return _TOKEN_RE.findall((text or "").lower())


def expand_query(text: str) -> str:
    """Append domain synonyms so local embeddings capture paraphrases."""
    tokens = tokenize_query(text)
    extras: list[str] = []
    for tok in tokens:
        extras.extend(_SYNONYMS.get(tok, ()))
    if not extras:
        return text or ""
    return f"{text} " + " ".join(dict.fromkeys(extras))


def _stable_bucket(token: str, dim: int) -> int:
    digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, "little") % dim


def _hashing_embed(text: str, *, dim: int = DEFAULT_DIM) -> np.ndarray:
    """Feature-hash bag of words + char trigrams -> L2-normalized vector."""
    expanded = expand_query(text).lower()
    vec = np.zeros(dim, dtype=np.float32)
    tokens = _TOKEN_RE.findall(expanded)
    for tok in tokens:
        vec[_stable_bucket(f"w:{tok}", dim)] += 1.0
        if len(tok) >= 3:
            for i in range(len(tok) - 2):
                gram = tok[i : i + 3]
                vec[_stable_bucket(f"c:{gram}", dim)] += 0.5
    # Soften raw counts
    for i, v in enumerate(vec):
        if v > 0:
            vec[i] = 1.0 + math.log(v)
    norm = float(np.linalg.norm(vec))
    if norm > 0:
        vec /= norm
    return vec


def _vertex_embed(texts: Sequence[str], *, dim: int | None = None) -> np.ndarray:
    """Vertex AI text embeddings (optional cloud path)."""
    from google import genai

    model = os.getenv("VERTEX_EMBEDDING_MODEL", "text-embedding-004")
    client = genai.Client(
        vertexai=True,
        project=os.getenv("GOOGLE_CLOUD_PROJECT"),
        location=os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1"),
    )
    vectors: list[np.ndarray] = []
    for text in texts:
        result = client.models.embed_content(model=model, contents=text or " ")
        values = list(result.embeddings[0].values)
        if dim is not None and len(values) != dim:
            # Pad / truncate to requested dim for index compatibility.
            arr = np.zeros(dim, dtype=np.float32)
            n = min(dim, len(values))
            arr[:n] = values[:n]
        else:
            arr = np.asarray(values, dtype=np.float32)
        norm = float(np.linalg.norm(arr))
        if norm > 0:
            arr /= norm
        vectors.append(arr)
    return np.vstack(vectors)


def embed_texts(
    texts: Sequence[str],
    *,
    dim: int = DEFAULT_DIM,
    backend: str | None = None,
) -> np.ndarray:
    """Embed one or many texts. Returns shape (n, dim), L2-normalized."""
    if not texts:
        return np.zeros((0, dim), dtype=np.float32)

    chosen = (backend or ("vertex" if _vertex_enabled() else "local")).lower()
    if chosen == "vertex":
        try:
            return _vertex_embed(texts, dim=dim)
        except Exception:
            # Cloud unavailable -> local fallback (Sprint 6 degradation path).
            pass

    return np.vstack([_hashing_embed(t, dim=dim) for t in texts])


def embed_text(text: str, *, dim: int = DEFAULT_DIM, backend: str | None = None) -> np.ndarray:
    return embed_texts([text], dim=dim, backend=backend)[0]


def case_to_text(case: dict) -> str:
    """Flatten a memory case into embedding text."""
    parts = [
        str(case.get("case_id", "")),
        str(case.get("asset_id", "")),
        str(case.get("asset_type", "")),
        str(case.get("alarm_type", "")),
        str(case.get("case_type", "")),
        str(case.get("policy_id", "")),
        str(case.get("work_order_id", "")),
        str(case.get("summary", "")),
        str(case.get("resolution", "")),
        " ".join(str(k) for k in case.get("keywords", []) or []),
    ]
    return " ".join(p for p in parts if p)
