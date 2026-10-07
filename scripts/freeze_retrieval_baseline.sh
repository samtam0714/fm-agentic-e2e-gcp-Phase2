#!/usr/bin/env bash
# Run retrieval eval and freeze eval_harness/baselines/phase2-retrieval.json.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

MILESTONE="${1:-phase2-retrieval}"
REPORT="${ROOT_DIR}/eval_harness/reports/retrieval_report.json"
MILESTONE_PATH="${ROOT_DIR}/eval_harness/baselines/${MILESTONE}.json"

uv run run-retrieval-eval --out "${REPORT}"

export FREEZE_RETRIEVAL_MILESTONE="${MILESTONE}"
uv run python - <<'PY'
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

milestone = os.environ["FREEZE_RETRIEVAL_MILESTONE"]
report_path = Path("eval_harness/reports/retrieval_report.json")
milestone_path = Path("eval_harness/baselines") / f"{milestone}.json"
milestone_path.parent.mkdir(parents=True, exist_ok=True)

with open(report_path, encoding="utf-8") as f:
    report = json.load(f)

if report.get("fail_count", 0) != 0:
    raise SystemExit(
        f"[freeze_retrieval] BLOCK: report has {report['fail_count']} failing case(s)"
    )

try:
    git_sha = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], text=True
    ).strip()
except Exception:
    git_sha = "unknown"

try:
    import importlib.metadata as md

    adk_version = md.version("google-adk")
except Exception:
    adk_version = "unknown"

baseline = {
    **report,
    "milestone": milestone,
    "git_sha": git_sha,
    "dataset_version": f"retrieval-{report.get('case_count', 0)}",
    "google_adk_version": adk_version,
    "timestamp": datetime.now(timezone.utc).isoformat(),
    "source": str(report_path),
    "notes": "Frozen retrieval-quality eval (Recall@K + keyword vs vector groundedness).",
}

milestone_path.write_text(json.dumps(baseline, indent=2) + "\n", encoding="utf-8")
print(
    f"[freeze_retrieval] Saved {report['pass_count']}/{report['case_count']} "
    f"cases -> {milestone_path} "
    f"(avg_recall@{report.get('k', 3)}={report.get('avg_recall_at_k')})"
)
PY
