# Phase 1 Study Notes

> Record key decisions and pitfalls during V1 implementation. See [plan_phase1.md](../plan_phase1.md) for detailed specifications.

---

## Architectural Decisions

### SequentialAgent replaced Router + Planner in V1

The V1 workflow was fixed (alarm -> policy -> work order -> audit), so ADK `SequentialAgent` was sufficient and more stable. Phase 2 later added RouterAgent for intent classification and PlannerAgent for three-step planning, followed by a bounded specialist execution loop with recovery.

### In-process Tool Registry

In V1, tool functions lived in `agents/*/tools.py` and were registered through `tools/registry.py`. Phase 2 later introduced independent MCP server processes.

### Share investigate pipeline

`services/investigate.py` is shared by API, CLI, and eval harness to ensure that the three paths behave consistently.

---

## Eval and Release Gate

### Rule judge vs LLM judge

- **Rule judge**: Check tool/agent coverage, keywords, `must_not_contains` - deterministic, fast.
- **LLM judge**: checks `task_success` and `groundedness`; it is stricter and can detect contradictions across agent outputs.

At Phase 1 completion, all 5 cases passed both judges: rule 5/5, LLM 5/5, and release gate PASS. The current `dataset=all` regression suite contains exactly 30 cases.

Key fixes:
- `recommend_work_order` will no longer be misjudged as an order that should be built just because the policy clause contains "work order"
- `to_agent_trace()` passes `texts_by_agent`, LLM judge can see the output of each agent
- The rule judge applies `must_not_contains` only to the WorkOrder Agent recommendation, avoiding false failures caused by KB policy quotations.

### Why the Week 3.4 regression mattered

Deliberately modify the `workorder_agent` prompt, verify:

1. eval can catch bad behavior
2. release gate will BLOCK
3. the gate passes after restoration

This is **proof** of the safety valve before release, not a product change.

### `--skip-llm-judge` and gate

Skip LLM judge during fast regression; gate will automatically skip `avg_task_success` / `avg_groundedness` items.

---

## Deployment

### Cloud Run Permissions

The service account requires `roles/aiplatform.user` to call Vertex Gemini.

### Local vs Cloud Run Latency

Local investigate ~60-120s; Cloud Run ~20-30s (after cold start). The behavior is consistent, the difference in latency comes mainly from environment.

### curl line continuation character

There must be no space after `\` in the shell, otherwise line continuation will fail:

```bash
# Error: There is a space after \
curl -X POST ... \  
  -d '...'

# correct
curl -X POST ... \
  -d '...'
```

---

## Phase 2 follow-up status

- [x] Router + Planner agents
- [x] Standalone MCP servers
- [x] Core 30-case `all` dataset, including `safety_cases.json`
- [x] LLM judge and release-gate hardening
- [x] Cloud Build CI regression gate
- [ ] Vector memory (FAISS / Vertex Vector Search) - stretch scope
