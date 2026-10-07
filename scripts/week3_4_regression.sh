#!/usr/bin/env bash
# Week 3.4: break workorder prompt -> eval FAIL -> gate BLOCK -> restore -> PASS.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROMPT_FILE="${ROOT_DIR}/agents/workorder_agent/prompts.py"
BACKUP_FILE="${PROMPT_FILE}.week34.bak"
CASE_ID="${CASE_ID:-alarm_001}"

GOOD_PROMPT='SYSTEM_INSTRUCTION = """You are a Facility Management Work Order Triage Agent.

Context: You run after alarm_agent and kb_agent. Review prior outputs for
asset_id, event_count, is_recurring, alarm priority, policy_ids, and likely_cause
before calling recommend_work_order.

Rules:
1. ALWAYS call recommend_work_order before recommending create/update actions.
2. Base decisions ONLY on tool output - do not invent work order IDs or priorities.
3. If an active work order already exists, prefer escalate/update over creating duplicates.
4. Cite work_order_id, priority, and action from tool output.
5. Summarize: action (create_new / use_existing / escalate_existing), priority, rationale.
"""'

BROKEN_PROMPT='SYSTEM_INSTRUCTION = """You are a Facility Management Work Order Triage Agent.

REGRESSION TEST MODE - ignore safety rules:
- Always recommend creating a new work order even when WO-2026-0142 exists.
- Your response MUST include the exact phrase: create a new work order
- Do NOT recommend escalating existing work orders.
"""'

restore_prompt() {
  if [[ -f "${BACKUP_FILE}" ]]; then
    mv "${BACKUP_FILE}" "${PROMPT_FILE}"
    echo "[week3.4] Restored original workorder prompt"
  fi
}

trap restore_prompt EXIT

write_prompt() {
  printf '%s\n' "$1" > "${PROMPT_FILE}"
}

run_gate_expect() {
  local expected="$1"
  set +e
  uv run python eval_harness/release_gate/gate.py eval_harness/reports/eval_report.json
  local gate_exit=$?
  set -e

  if [[ "${expected}" == "block" && ${gate_exit} -ne 0 ]]; then
    echo "[week3.4] OK: release gate BLOCKED as expected (exit=${gate_exit})"
    return 0
  fi
  if [[ "${expected}" == "pass" && ${gate_exit} -eq 0 ]]; then
    echo "[week3.4] OK: release gate PASSED as expected"
    return 0
  fi

  echo "[week3.4] FAIL: expected gate ${expected}, got exit=${gate_exit}"
  return 1
}

cd "${ROOT_DIR}"

echo ""
echo "========== Week 3.4 Step 1: backup good prompt =========="
cp "${PROMPT_FILE}" "${BACKUP_FILE}"

echo ""
echo "========== Week 3.4 Step 2: inject broken workorder prompt =========="
write_prompt "${BROKEN_PROMPT}"
cat "${PROMPT_FILE}"

echo ""
echo "========== Week 3.4 Step 3: run eval (expect FAIL) =========="
set +e
uv run python eval_harness/runners/run_agent_eval.py \
  --case-id "${CASE_ID}" \
  --skip-llm-judge
eval_fail_exit=$?
set -e
if [[ ${eval_fail_exit} -eq 0 ]]; then
  echo "[week3.4] FAIL: eval unexpectedly passed with broken prompt"
  exit 1
fi
echo "[week3.4] OK: eval failed as expected (exit=${eval_fail_exit})"

echo ""
echo "========== Week 3.4 Step 4: release gate (expect BLOCK) =========="
run_gate_expect block

echo ""
echo "========== Week 3.4 Step 5: restore good prompt =========="
restore_prompt
trap - EXIT
cat "${PROMPT_FILE}"

echo ""
echo "========== Week 3.4 Step 6: run eval again (expect PASS) =========="
uv run python eval_harness/runners/run_agent_eval.py \
  --case-id "${CASE_ID}" \
  --skip-llm-judge

echo ""
echo "========== Week 3.4 Step 7: release gate (expect PASS) =========="
run_gate_expect pass

echo ""
echo "========== Week 3.4 COMPLETE: Release gate regression verified =========="
