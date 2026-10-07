#!/usr/bin/env python3
"""Run retrieval-quality eval against golden_dataset/retrieval_cases.json."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from eval_harness.metrics.retrieval_scorer import (
    build_retrieval_report,
    compare_keyword_vs_vector,
    query_keywords,
)
from memory.case_store import CaseStore

DEFAULT_CASES = (
    Path(__file__).resolve().parents[1]
    / "golden_dataset"
    / "retrieval_cases.json"
)
DEFAULT_OUT = (
    Path(__file__).resolve().parents[1]
    / "reports"
    / "retrieval_report.json"
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Sprint 6 retrieval eval")
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--k", type=int, default=3)
    parser.add_argument("--min-score", type=float, default=0.08)
    args = parser.parse_args()

    cases = json.loads(args.cases.read_text(encoding="utf-8"))
    store = CaseStore.default()
    by_id = {str(c["case_id"]): c for c in store.load()}
    scores = []
    for case in cases:
        k = int(case.get("k", args.k))
        min_score = args.min_score
        if case.get("allow_empty") or case.get("must_not_retrieve"):
            min_score = max(min_score, 0.35)
        vector_hits = store.search_semantic(
            case["query"], limit=k, min_score=min_score
        )
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

    report = build_retrieval_report(scores, k=args.k)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        f"[retrieval_eval] {report['pass_count']}/{report['case_count']} pass "
        f"(avg_recall@{args.k}={report['avg_recall_at_k']}, "
        f"groundedness Δ={report.get('groundedness_delta')}) -> {args.out}"
    )
    raise SystemExit(0 if report["pass_rate"] == 1.0 else 1)


if __name__ == "__main__":
    main()
