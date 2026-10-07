#!/usr/bin/env bash
# Freeze eval_report.json as a versioned milestone baseline (+ CI sync copy).
#
# Usage:
#   ./scripts/freeze_baseline.sh                       # -> phase2-adk-skills (default)
#   ./scripts/freeze_baseline.sh phase2-planner
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

MILESTONE="${1:-phase2-adk-skills}"
REPORT="${ROOT_DIR}/eval_harness/reports/eval_report.json"
LEGACY="${ROOT_DIR}/eval_harness/reports/baseline.json"
MILESTONE_PATH="${ROOT_DIR}/eval_harness/baselines/${MILESTONE}.json"

if [[ ! -f "${REPORT}" ]]; then
  echo "[freeze_baseline] ERROR: ${REPORT} not found. Run ./scripts/run_eval.sh first."
  exit 1
fi

export FREEZE_MILESTONE="${MILESTONE}"
uv run python - <<'PY'
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from eval_harness.metrics.schema import validate_report

milestone = os.environ["FREEZE_MILESTONE"]
report_path = Path("eval_harness/reports/eval_report.json")
legacy_path = Path("eval_harness/reports/baseline.json")
milestone_path = Path("eval_harness/baselines") / f"{milestone}.json"
milestone_path.parent.mkdir(parents=True, exist_ok=True)

with open(report_path, encoding="utf-8") as f:
    report = json.load(f)

if report.get("fail_count", 0) != 0:
    raise SystemExit(
        f"[freeze_baseline] BLOCK: report has {report['fail_count']} failing case(s)"
    )

errors = validate_report(report)
if errors:
    raise SystemExit(f"[freeze_baseline] BLOCK: invalid report schema: {errors}")

try:
    git_sha = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], text=True
    ).strip()
except Exception:
    git_sha = "unknown"

skill_versions: dict[str, str] = {}
try:
    from skills.loader import load_skills

    skill_versions = {s.id: s.version for s in load_skills()}
except Exception:
    pass

try:
    import importlib.metadata as md

    adk_version = md.version("google-adk")
except Exception:
    adk_version = "unknown"

report["frozen_at"] = datetime.now(timezone.utc).isoformat()
report["source"] = str(report_path)
report["milestone"] = milestone
report["git_sha"] = git_sha
report["dataset_version"] = f"golden@{report.get('case_count', 0)}"
report["model"] = report.get("model") or os.getenv("EVAL_MODEL", "gemini-2.0-flash")
report["model_settings"] = report.get("model_settings") or {"temperature": 0.0}
report["google_adk_version"] = adk_version
report["skill_versions"] = skill_versions
report["timestamp"] = report["frozen_at"]

payload = json.dumps(report, indent=2) + "\n"
milestone_path.write_text(payload, encoding="utf-8")
legacy_path.write_text(payload, encoding="utf-8")

print(
    f"[freeze_baseline] Saved {report['pass_count']}/{report['case_count']} "
    f"cases -> {milestone_path} (and sync {legacy_path})"
)
print(
    "[freeze_baseline] Reminder: set gates/regression_rules.yaml "
    f"baseline_path to eval_harness/baselines/{milestone}.json"
)
PY
