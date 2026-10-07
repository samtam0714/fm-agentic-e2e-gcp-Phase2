# Mock Data - FM AgentOps DemoCorp / Toronto

Simulated FM data for Phase 1 agent development. All records use site **Toronto**, customer **DemoCorp**, building **BLD-001**.

## Primary user story

> "The HVAC alarm on Floor 3 keeps recurring. Check the issue, search policy, decide if we should create a work order, and recommend priority."

**Expected path through data:**

1. `issues.json` + `alarm_events.json` -> **issue_demo_001** / **AHU-3F-01** (7 events, recurring)
2. `policies.json` -> **HVAC-MNT-003** (recurring temp alarm -> inspect filter, medium WO)
3. `tickets.json` -> **WO-2026-0142** (open, deferred once - agent may recommend completing it)
4. `data/memory/cases.json` -> **case_002** (similar active case), **case_001** (resolved precedent)

## Files

| File | Entity | Used by |
|------|--------|---------|
| `mailgun_emails.json` | Raw inbound BAS emails | Email ingestion (source) |
| `alarm_events.json` | Parsed alarm events | Alarm history tools |
| `issues.json` | Aggregated issues | Alarm investigation |
| `alarms.json` | Alarm analytics rollup (30d stats) | Alarm summary / dashboards |
| `assets.json` | Asset master + context | `get_asset_context` (planned) |
| `policies.json` | Maintenance policies | `search_policy_doc` (planned) |
| `tickets.json` | Work orders / tickets | `recommend_work_order` (planned) |
| `../memory/cases.json` | Resolved case history | Case memory (planned) |

## Entity relationships

```
mailgun_email ──► alarm_event ──► issue ──► linked_workorders ──► ticket
                      │              │
                      └──── asset_id ┴────► assets.json
                                           alarms.json (rollup)
policies.json ◄── linked_policy_id ── tickets.json
cases.json ──► asset_id, work_order_id, policy_id (historical patterns)
```

## Key demo records

| ID | Role |
|----|------|
| `issue_demo_001` | Main recurring Floor 3 AHU story |
| `AHU-3F-01` | Primary asset (7 events / 30d) |
| `HVAC-MNT-003` | Policy for recurring temp alarms |
| `WO-2026-0142` | Open work order (deferred) |
| `issue_demo_002` | Old single event - should NOT match 30d floor-3 query |

## Cross-reference rules (enforced by tests)

- Every `events[]` id in `issues.json` exists in `alarm_events.json`
- Every `mailgun_email_id` in events exists in `mailgun_emails.json`
- Every `related_work_orders[]` in `alarms.json` exists in `tickets.json`
- Every `linked_workorders[]` in issues exists in `tickets.json`
- Every `asset_id` in assets exists in alarms rollup (where applicable)

Run integrity checks:

```bash
uv run pytest tests/test_mock_data.py -v
```
