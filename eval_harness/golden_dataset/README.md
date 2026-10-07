# Golden Dataset Reference

The eval harness uses fixed cases to test agent behavior. Each case combines a user request, expected tool calls, expected agents, answer signals, and prohibited behaviors.

## Four files (exactly 30 `all` cases)

| File | Cases | Category | Coverage |
|------|------|------|--------|
| `alarm_cases.json` | 10 | normal | Standard alarm workflows: history, policy, and work-order escalation, creation, or monitoring |
| `safety_cases.json` | 5 | safety | Refusal of unsafe requests such as bypassing policy checks or creating duplicate work orders |
| `rag_cases.json` | 5 | rag | Policy citations, similar-case retrieval, and grounded answers |
| `failure_cases.json` | 10 | failure / fallback | Invalid arguments, tool failures, timeouts, and safe fallback behavior |

When `dataset=all`, the loader merges exactly these 30 cases in the order shown above.

### Optional Sprint 7 dataset (excluded from `all`)

| File | Cases | Category | Coverage |
|------|------|------|--------|
| `a2a_failure_cases.json` | 3 | failure | Mini A2A: timeout / unavailable / invalid-response + local fallback |

Loading: `EVAL_DATASET=a2a_failure_cases` (requires `USE_A2A_WORKORDER=1` and corresponding `WORKORDER_A2A_FAULT`).

## Common case fields

### Required

| Field | Meaning |
|------|------|
| `case_id` | Case identifier, such as `alarm_001` or `fail_005` |
| `input` | Simulated user request |
| `expected_tools` | List of tool names that must be called |
| `expected_agents` | List of agent names that must run |

### Commonly used options

| Field | Meaning |
|------|------|
| `case_category` | Question type label, default `normal` |
| `expected_answer_contains` | Keywords that must appear across the agents' final outputs |
| `must_not_contains` | Phrases that cannot appear in the answer (such as "create a new work order") |
| `must_not_do` | Prohibited business behavior (for judges and LLM reference) |
| `optional_tools` | Tools that are useful but not required for a pass, such as `search_similar_cases` |
| `keyword_alternatives` | Equivalent phrases where any match counts, such as `not recurring` -> `single event` |

### New in Phase 2 (only for failure questions)

| Field | Meaning | Example |
|------|------|------|
| `failure_scenario` | Failure scenario type | `invalid_arg` / `tool_fail` / `timeout` / `safety` / `fallback` |
| `expected_recovery_contains` | Recovery or fallback signals expected in the answer | `["monitor"]` |
| `fault_injection` | Makes a tool fail deliberately for its first N calls during eval | See below |

### fault_injection example

```json
"fault_injection": {
  "tool": "search_policy_doc",
  "fail_count": 1,
  "error": "timeout"
}
```

When `fail_005` runs, the first policy lookup returns an injected timeout. The case verifies whether the agent retries or completes the task safely with the available alarm evidence. See `eval_harness/fault_injection.py`.

## Overview of the ten failure cases

| case_id | Scenario | Summary |
|---------|------|--------|
| fail_001 | invalid_arg | Unknown asset AHU-UNKNOWN-99 |
| fail_002 | invalid_arg | Non-existent Floor 99 |
| fail_003 | tool_fail | Policy ID not found |
| fail_004 | tool_fail | Work-order request without an asset |
| fail_005 | timeout | Policy query timeout (with fault_injection) |
| fail_006 | timeout | Alarm history query timeout (with fault_injection) |
| fail_007 | safety | User asks the agent to ignore tool errors |
| fail_008 | safety | User asks the agent to skip the audit |
| fail_009 | fallback | Single alarm -> monitor |
| fail_010 | fallback | No alarm data -> safe fallback |

## Related code

- Loading: `loader.py`
- Validation: `validate.py`
- Rule scoring (including failure_recovery): `judges/rule_based_judge.py`
- Fault injection: `fault_injection.py`
- Eval entry point: `runners/run_agent_eval.py`
