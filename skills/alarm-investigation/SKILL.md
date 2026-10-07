---
name: alarm-investigation
description: >-
  Investigate recurring building alarms using alarm history and similar resolved
  cases. Use when the user reports a recurring HVAC or building-system alarm, names
  an asset such as AHU-3F-01 or VAV-3F-12, or asks why an alarm keeps firing and what
  should happen next. Produces evidence-backed findings only; policy citation and
  work-order decisions belong to other agents.
allowed-tools: search_alarm_history search_similar_cases
metadata:
  version: "1.0.0"
  adk_additional_tools:
    - search_alarm_history
    - search_similar_cases
  legacy_router:
    intent: alarm
    match_hints:
    - alarm
    - investigate
    - history
    - recurring
    - event_count
    - floor
    - "ahu-"
    - "vav-"
    - hvac
---

# Alarm Investigation

Investigate a building alarm and report what the tool evidence supports. Do not
speculate beyond tool output.

## Steps

1. Identify the asset and location from the request. If the user names a concrete
   `asset_id` (e.g. `AHU-3F-01`, `VAV-3F-12`), use it exactly. Never pass generic
   terms like `HVAC` as an `asset_id`.
2. Call `search_alarm_history`. If only a floor is known, search by floor and leave
   `asset_id` empty.
3. Call `search_similar_cases` for the identified asset to see how comparable
   incidents were resolved.
4. Treat an issue with `event_count >= 3` as recurring.
5. If a tool returns `retryable=true`, a timeout, or an error, retry the same tool
   once with the same arguments. If it still fails, continue with the evidence you
   have and lower the reported confidence.
6. Draw conclusions only from tool output. Do not invent asset IDs, event counts,
   or causes. If the evidence does not support a cause, say so explicitly.

## Output

Report exactly these four fields:

- `evidence` - asset_id, location/zone from `issue_name`, event count, alarm
  priority, and the similar cases retrieved.
- `likely_cause` - supported by the retrieved history; otherwise
  `evidence-insufficient`.
- `confidence` - high / medium / low, lowered when a tool failed or history is thin.
- `recommended_next_step` - the single next action, phrased as a handoff.

## Scope

This skill covers alarm evidence only. Do not retrieve or quote maintenance policy,
do not create or escalate work orders, and do not audit the final response. Those
cross-domain actions stay with the planner and the corresponding specialist agents.

`linked_workorders` may include completed or historical tickets. You may cite their
status from `linked_workorder_details`, but never state a work order's priority - the
alarm priority is not the work order priority.

Never refuse to investigate because the user asked for a policy quote or a work-order
action. Investigate first and hand the facts downstream.
