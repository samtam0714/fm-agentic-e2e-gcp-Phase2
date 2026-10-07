---
name: policy-lookup
description: >-
  Retrieve and cite governing maintenance policy documents (for example HVAC-MNT-*).
  Use when the user asks what a policy says, which rule applies, or needs verbatim
  compliance guidance without a full work-order create/escalate request.
allowed-tools: search_policy_doc
metadata:
  version: "1.0.0"
  adk_additional_tools:
    - search_policy_doc
  legacy_router:
    intent: policy
    match_hints:
    - policy
    - hvac-mnt
    - cite
    - quote
    - governing policy
    - what does
    - compliance
    - rules from
---

# Policy Lookup

Retrieve maintenance policy that matches the request and cite only what the tool
returns.

## Steps

1. Call `search_policy_doc` with a focused keyword query (policy id, alarm type, or
   maintenance topic). When the prior turn named an asset type (AHU, VAV), pass it as
   `asset_type`.
2. If the tool returns `retryable=true`, a timeout, or an error, retry once with the
   same arguments. If it still fails, say policy lookup degraded and do not invent
   rules.
3. Prefer the policy that matches the alarm or maintenance topic:
 - supply-air temperature recurrence -> HVAC-MNT-003
 - filter pressure / filter change -> HVAC-MNT-001
4. Quote `policy_id` and rule text **verbatim** from tool output. Never paraphrase a
   rule into something the tool did not return.
5. If multiple policies match, list only those present in the tool result and say which
   one governs the current ask.

## Output

Report:

- `policies` - each with policy_id and the cited rule text
- `match_reason` - why this policy applies to the user query
- `degraded` - true if policy search failed or returned empty

## Scope

This skill is policy evidence only. Do not investigate alarm history, do not create or
escalate work orders, and do not invent compliance requirements. Hand work-order
decisions and audit to downstream agents when the planner requires them.
