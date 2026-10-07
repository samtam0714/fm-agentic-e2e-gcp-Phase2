---
name: workorder-recommendation
description: >-
  Decide create / escalate / monitor / no_action for a maintenance work order or
  ticket. Use when the user asks to open, escalate, or triage a work order and alarm
  investigation is complete or not required as a standalone invent-from-scratch task.
allowed-tools: recommend_work_order
metadata:
  version: "1.0.0"
  adk_additional_tools:
    - recommend_work_order
  legacy_router:
    intent: workorder
    match_hints:
    - work order
    - workorder
    - escalate
    - ticket
    - create a new
    - open a
    - wo-
---

# Work Order Recommendation

Recommend a work-order action from tool evidence only. Do not invent ticket ids or
priorities.

## Steps

1. Collect `asset_id`, `event_count`, `is_recurring`, policy ids, and likely cause from
   the conversation when available. Never invent an asset id.
2. Call `recommend_work_order` before stating create / escalate / monitor / no_action.
3. If the tool returns `retryable=true`, a timeout, or an error, retry once with the
   same arguments. If it still fails, prefer monitoring / no_action rather than
   inventing a work order.
4. If an active work order already exists, follow the tool action
   (`escalate_existing` / `use_existing`) rather than forcing a new ticket.
5. Pass `event_count` from alarm evidence when present; if unknown, pass `0` so the
   tool can load the issue record.

## Output

Report:

- `action` - create_new / use_existing / escalate_existing / no_action
- `work_order_id` - only if the tool returned one
- `priority` - only from tool output
- `rationale` - grounded in tool fields (event_count, policy, existing WO)

## Scope

This skill covers work-order triage only. Do not search alarm history, do not quote
policy rules, and do not override a failed audit. If tool action is `no_action`,
recommend monitoring - never say "create a new work order" in that case.
