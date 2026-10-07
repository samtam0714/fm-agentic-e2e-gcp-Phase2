import json
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "mock"


def _load_json(name: str) -> list:
    with open(DATA_DIR / name, encoding="utf-8") as f:
        return json.load(f)


def _normalize(text: str) -> str:
    """Normalize retrieval text by lowercasing and treating separators as spaces.

    This lets an alarm type such as "high_supply_air_temp" match policy text
    containing "supply air temp".
    """
    return text.lower().replace("_", " ").replace("-", " ")


def search_policy_doc(
    query: str,
    asset_type: str | None = None,
) -> dict:
    """Search maintenance policy documents by keywords and optional asset type."""
    if not query.strip():
        return {
            "query": {"query": query, "asset_type": asset_type},
            "match_count": 0,
            "policies": [],
        }

    policies = _load_json("policies.json")
    q = _normalize(query)
    # Keep tokens of at least three characters to avoid noisy matches such as "of".
    q_tokens = [tok for tok in q.split() if len(tok) >= 3]

    matched = []
    for p in policies:
        if asset_type and asset_type not in p.get("applies_to", []):
            continue
        haystack = _normalize(" ".join([
            p.get("policy_id", ""),
            p.get("title", ""),
            p.get("summary", ""),
            " ".join(p.get("rules", [])),
            " ".join(p.get("keywords", [])),
        ]))
        if q in haystack or any(tok in haystack for tok in q_tokens):
            matched.append(p)

    return {
        "query": {"query": query, "asset_type": asset_type},
        "match_count": len(matched),
        "policies": matched,
    }