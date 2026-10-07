

# Facility Management AgentOps - North-Star Plan

Project positioning:

> **GCP Enterprise Multi-Agent Release Platform**
> A production-level multi-agent platform for Building Operations / facility management scenarios, covering agent orchestration, MCP tools, A2A agent collaboration, agent skills, memory, tracing, evaluation harness, LLM judge, observability, and release gate.

Google ADK supports the agent build, test, evaluation, and deployment lifecycle, including Cloud Run, A2A, multi-agent workflows, Cloud Trace, MCP tools, and evaluation workflows. These capabilities make the project relevant to a Google GenAI Forward Deployed Engineer or Developer role. ([Google GitHub][1])

> **Current implementation snapshot:** Phase 1 is complete, and Phase 2 core is complete. RootAgent currently runs RouterAgent -> PlannerAgent -> a bounded specialist execution loop with recovery. The `dataset=all` regression suite contains exactly 30 cases. [plan_phase3.md](../plan_phase3.md) now defines the next retrieval, execution-memory, and Plan -> Check -> Act phase. Sections below preserve the original north-star design where they describe future or stretch capabilities.

---

# Project name

## **Facility Management AgentOps on GCP**

One sentence introduction:

> A production-grade multi-agent platform for building operations, with ADK-based orchestration, MCP-style tool servers, A2A agent collaboration, memory, tracing, automated eval harness, LLM-as-a-judge, observability, and release gates.

---

# Business scenario

User input:

> “The HVAC alarm on Floor 3 keeps recurring. Check the issue, search policy, decide if we should create a work order, and recommend priority.”

The system needs to automatically complete:

```text
Understand user intent
-> Call Alarm Agent to check alarm history
-> Call Knowledge Agent to search for maintenance policy
-> Call Work Order Agent to determine whether to create a ticket
-> Call Auditor Agent to check whether the result is grounded
-> Output recommendation
-> Log trace / latency / cost / tool calls
-> Automatically run eval
-> Determine whether this agent version can be released
```

---

# Core architecture

```text
User / API Client
        ↓
FastAPI Gateway
        ↓
ADK Root Agent / Orchestrator
        ↓
Router Agent
        ↓
Planner Agent
        ↓
 ┌───────────────┬────────────────┬────────────────┐
 │               │                │                │
Alarm Agent   KB/RAG Agent    WorkOrder Agent   Auditor Agent
 │               │                │                │
MCP Alarm     MCP Policy       MCP Ticket        Judge / Eval
Server        Server           Server            Engine
 │               │                │                │
BigQuery /    Vertex AI         Firestore /       Eval Store
Mock DB       Vector Search     Mock Ticket DB
        ↓
Trace + Logs + Metrics
        ↓
Cloud Logging / Cloud Trace / BigQuery Agent Analytics
        ↓
Eval Harness + Release Gate
```

Google Cloud's A2A documentation emphasizes that agents can discover, communicate, collaborate, and delegate tasks through the Agent2Agent protocol; Cloud Run also has a hosting guide for A2A agents. ([Google Cloud Documentation][2])

---

# Technical scope

## 1. Multi-agent orchestration

ADK is the primary framework.

Current core agents:

```text
Root Agent
Router Agent
Planner Agent
Alarm Agent
Knowledge Agent
WorkOrder Agent
Auditor Agent
Evaluation Agent
```

RouterAgent classifies intent, PlannerAgent creates a three-step plan, and RootAgent runs the specialist pipeline in a bounded recovery loop. An Evaluation Agent remains a north-star concept rather than a separate core runtime agent.

The point is not the number of agents, but:

```text
handoff
state
tool use
memory
failure recovery
traceability
```

---

## 2. Agent Skills

Use native ADK Agent Skills (`SKILL.md` + `SkillToolset`) with on-demand `load_skill` activation. The repository does not use a separate custom skills-registry node.

```text
skills/
  alarm-investigation/SKILL.md
  policy-lookup/SKILL.md
  workorder-recommendation/SKILL.md
  loader.py

eval_harness/
  skill_cases/
    alarm-investigation.json
    policy-lookup.json
    workorder-recommendation.json
```

Each `SKILL.md` contains metadata and task-specific instructions. Skill eval cases remain external to the skill definition.

```yaml
name: alarm_investigation
description: Investigate recurring building alarms and summarize likely root cause.
tools:
  - search_alarm_history
  - get_asset_context
outputs:
  - root_cause_summary
  - recommended_action
```

This supports the following interview summary:

> I implemented native ADK Agent Skills that load task-specific instructions on demand and activate MCP-backed tools only when needed, with evaluation cases maintained separately.

---

## 3. MCP Tool Servers

Phase 2 provides three MCP-style servers:

```text
Alarm MCP Server
Policy MCP Server
Ticket MCP Server
```

nature:

```text
Agent -> MCP client -> MCP server -> enterprise tool/data
```

Google ADK documentation has integration instructions for MCP tools. MCP itself is a protocol for standardized models/agents to use tools, resources, and prompts. ([Google GitHub][3])

You don’t need to make a complicated enterprise connector at the beginning. You can mock first:

```python
search_alarm_history(asset_id, time_range)
search_policy_doc(query)
create_work_order(asset_id, priority, summary)
update_ticket_priority(ticket_id, priority)
```

---

## 4. A2A Collaboration

Don't just do local sub-agent here. You need to design it to:

```text
Root Agent
  -> calls remote Alarm Agent via A2A
  -> calls remote WorkOrder Agent via A2A
```

A2A agent exposure:

```text
/.well-known/agent-card.json
/invoke
/status
```

Google's A2A guide mentions that Agent Card is used to describe the name, capabilities and endpoint of the agent. ([Google Developers Blog][4])

In your interview you can talk about:

> Local sub-agents are good for fast in-process delegation, but A2A is better when agents are independently deployed, owned by different teams, or need cross-system interoperability.

---

## 5. Memory

Divided into two layers:

```text
Short-term memory:
session state, current task, intermediate results

Long-term memory:
historical resolved cases, policy snippets, prior user preferences
```

accomplish:

```text
ADK session state
+
Vertex AI Vector Search / FAISS first
+
BigQuery / Firestore memory table
```

Google ADK documentation also has state / session related modules. ([Google GitHub][5])

Memory schema:

```json
{
  "memory_id": "mem_001",
  "case_type": "recurring_hvac_alarm",
  "asset_id": "AHU-3F-01",
  "summary": "Recurring high temperature alarm resolved by filter replacement.",
  "resolution": "Create medium priority work order",
  "embedding_id": "vec_001",
  "created_at": "..."
}
```

---

## 6. Tracing

Each request must generate:

```text
trace_id
session_id
conversation_id
agent_run_id
tool_call_id
eval_run_id
```

Each agent outputs structured trace:

```json
{
  "trace_id": "tr_123",
  "agent": "PlannerAgent",
  "step": "decompose_task",
  "input": "...",
  "output": "...",
  "latency_ms": 820,
  "tokens_input": 400,
  "tokens_output": 180,
  "tool_calls": ["search_alarm_history"],
  "status": "success"
}
```

Cloud Trace can be used to monitor, debug, and improve ADK agent interactions. ([Google GitHub][6])

---

## 7. Observability

You want to monitor:

```text
latency p50 / p95
token usage
cost per request
tool-call success rate
tool-call error rate
task success rate
fallback rate
human escalation rate
groundedness score
```

use:

```text
Cloud Logging
Cloud Monitoring
Cloud Trace
BigQuery Agent Analytics
Looker Studio dashboard
```

Google BigQuery agent analytics is an open source solution that captures agent interactions such as requests, responses, tool calls, errors, and is used for evaluation, prompt optimization, and long-term memory. ([Google Cloud Documentation][7])

---

# Evaluation Pipeline

This is the core part of the entire project.

## Eval Harness

You do an `eval_harness/`:

```text
eval_harness/
  golden_dataset/
    alarm_cases.json       # 10
    safety_cases.json      # 5
    rag_cases.json         # 5
    failure_cases.json     # 10

  runners/
    run_agent_eval.py
    run_tool_eval.py
    run_rag_eval.py

  judges/
    llm_judge.py
    rule_based_judge.py
    debate_judge.py

  reports/
    eval_report.md
    regression_report.json
```

ADK eval official codelab emphasizes golden dataset, evaluation configuration, automated evaluations and regression detection. ([Google Codelabs][8])

---

## Golden Dataset Example

```json
{
  "case_id": "alarm_001",
  "input": "The HVAC alarm on Floor 3 keeps recurring. What should we do?",
  "expected_tools": [
    "search_alarm_history",
    "search_policy_doc"
  ],
  "expected_behavior": [
    "Check historical alarm frequency",
    "Retrieve relevant maintenance policy",
    "Recommend whether to create work order"
  ],
  "expected_answer_contains": [
    "recurring alarm",
    "work order",
    "priority"
  ],
  "must_not_do": [
    "create ticket without checking policy",
    "claim root cause without evidence"
  ]
}
```

---

## Metrics

You need to implement these:

```text
Task Success
Tool-call Accuracy
Tool Argument Accuracy
Groundedness
Completeness
Latency
Cost
Failure Recovery
Safety / Policy Compliance
Regression Rate
```

Example score:

```json
{
  "case_id": "alarm_001",
  "task_success": 0.9,
  "tool_call_accuracy": 1.0,
  "tool_arg_accuracy": 0.85,
  "groundedness": 0.92,
  "latency_seconds": 3.4,
  "cost_usd": 0.018,
  "failure_recovery": true,
  "pass": true
}
```

Google's production-ready multi-agent evaluation codelab mentioned using Vertex AI Gen AI Evaluation Service to implement adaptive rubrics, tool use quality metrics, and automate eval to the CI/CD pipeline. ([Google Codelabs][9])

---

# LLM-as-a-Judge

Judge rubric:

```json
{
  "correctness": "Does the answer solve the user task?",
  "groundedness": "Is the answer supported by retrieved evidence or tool outputs?",
  "tool_use": "Did the agent call the correct tools in the correct order?",
  "risk": "Did the agent avoid unsafe or unsupported actions?",
  "clarity": "Is the final recommendation clear?"
}
```

Judge output:

```json
{
  "correctness": 4,
  "groundedness": 5,
  "tool_use": 4,
  "risk": 5,
  "clarity": 4,
  "overall": 4.4,
  "pass": true,
  "reason": "The agent checked alarm history and policy before recommending a work order."
}
```

---

# Multi-Judge Evaluation (stretch)

This remains Phase 2 stretch scope rather than a completed core requirement.

Proposed structure:

```text
Judge Agent 1: Correctness Judge
Judge Agent 2: Groundedness Judge
Judge Agent 3: Risk Judge
Debate Coordinator
Final Arbiter
```

Proposed evaluation flow:

```text
Each judge scores independently
-> judges explain disagreement
-> final arbiter produces final score
```

After implementation, the interview summary would be:

> I implemented multi-agent debate evaluation to reduce single-judge bias and improve scoring reliability.

---

# Release Gate

You need to make a real release gate.

```yaml
release_criteria:
  task_success: ">= 0.85"
  tool_call_accuracy: ">= 0.90"
  groundedness: ">= 0.90"
  p95_latency_seconds: "<= 5"
  cost_per_request_usd: "<= 0.03"
  failure_recovery: ">= 0.80"
  critical_failures: "== 0"
```

If it doesn't pass:

```text
Block deployment
Generate regression report
Recommend failing cases
```

This is what you want to align:

> release gates for domain-specific models / agents

---

# GCP deployment architecture

```text
GitHub
  ↓
Cloud Build
  ↓
Artifact Registry
  ↓
Cloud Run Services
  - api-gateway
  - root-agent
  - alarm-agent-a2a
  - kb-agent-a2a
  - ticket-agent-a2a
  - eval-service
  - mcp-alarm-server
  - mcp-policy-server
  - mcp-ticket-server
  ↓
Cloud Logging / Cloud Trace / Cloud Monitoring
  ↓
BigQuery eval_results + agent_traces
  ↓
Looker Studio Dashboard
```

The official Cloud Run documentation has an ADK agent deployment tutorial, and the ADK documentation also recommends `adk deploy cloud_run` or `gcloud run deploy`. ([Google GitHub][10])

---

# Optional Phase 3 post-training direction: SFT / preference data / DPO

Do not begin by training a large model. Phase 3 first defines an eval-driven data and retrieval flywheel; SFT or DPO is optional follow-up work after the data is stable.

## Data

Generated from eval failures:

```text
instruction data
preference data
rubric-driven synthetic data
human review labels
```

Instruction example:

```json
{
  "instruction": "Investigate a recurring HVAC alarm and recommend next action.",
  "input": "Alarm history: ... Policy: ...",
  "output": "Recommended action: create medium priority work order because..."
}
```

Preference example:

```json
{
  "prompt": "Investigate recurring HVAC alarm...",
  "chosen": "Answer with evidence, policy citation, and priority reasoning.",
  "rejected": "Answer that creates ticket without checking policy."
}
```

Then:

```text
SFT small model
-> DPO preference tuning
-> rerun eval harness
-> compare base vs tuned model
-> release gate
```

---

# North-star repository structure

```text
fm-agentops-platform/
  agents/
    root_agent/
    router_agent/
    planner_agent/
    alarm_agent/
    kb_agent/
    ticket_agent/
    auditor_agent/
    eval_agent/

  skills/
    alarm_investigation/
    policy_search/
    work_order_triage/
    audit_response/

  mcp_servers/
    alarm_server/
    policy_server/
    ticket_server/

  a2a/
    agent_cards/
    clients/
    servers/

  memory/
    short_term/
    long_term/
    vector_store/

  eval_harness/
    golden_dataset/
    judges/
    metrics/
    runners/
    release_gate/

  observability/
    tracing/
    logging/
    dashboards/

  deployment/
    cloud_run/
    cloud_build/
    terraform/

  post_training/
    synthetic_data/
    instruction_data/
    preference_data/
    sft/
    dpo/

  docs/
    architecture.md
    eval_methodology.md
    release_gate.md
    interview_story.md
```

---


---

# By the end of this project you will be able to tell 5 Google interview stories

1. **System Design**
   How to design a production multi-agent platform.

2. **Agent Reliability**
   How to deal with hallucination, tool failure, latency, fallback.

3. **Evaluation**
   How to build eval harness, LLM judge, release gate.

4. **GCP Deployment**
   How to use Cloud Run, Logging, Trace, and BigQuery for production deployment.

5. **Customer-facing FDE Story**
   How to turn a vague business problem into an agent workflow.

---



The main line of your project is:

> **Facility Management AgentOps: Build, Evaluate, Deploy, Monitor, and Release Enterprise Multi-Agent Systems on GCP.**

After completing this project, you will also complete:

```text
ADK
MCP
A2A
Agent Skills
Multi-agent Orchestration
Memory
Tracing
Eval Harness
LLM Judge
Multi-agent Debate Eval
Observability
Release Gate
GCP Deployment
Post-training Data
SFT / DPO direction
```



[1]: https://google.github.io/adk-docs/?utm_source=chatgpt.com "Agent Development Kit (ADK) - Agent Development Kit (ADK)"
[2]: https://docs.cloud.google.com/run/docs/ai/a2a-agents?utm_source=chatgpt.com "Overview of A2A agents on Cloud Run"
[3]: https://google.github.io/adk-docs/tools/mcp-tools/?utm_source=chatgpt.com "MCP tools - Agent Development Kit (ADK)"
[4]: https://developers.googleblog.com/developers-guide-to-ai-agent-protocols/?utm_source=chatgpt.com "Developer's Guide to AI Agent Protocols"
[5]: https://google.github.io/adk-docs/sessions/state/?utm_source=chatgpt.com "State - Agent Development Kit (ADK)"
[6]: https://google.github.io/adk-docs/observability/cloud-trace/?utm_source=chatgpt.com "Google Cloud Trace observability for ADK"
[7]: https://docs.cloud.google.com/bigquery/docs/bigquery-agent-analytics?utm_source=chatgpt.com "Use BigQuery agent analytics"
[8]: https://codelabs.developers.google.com/adk-eval/instructions?utm_source=chatgpt.com "Evaluating Agents with ADK"
[9]: https://codelabs.developers.google.com/codelabs/production-ready-ai-roadshow/2-evaluating-multi-agent-systems/evaluating-multi-agent-systems?utm_source=chatgpt.com "From vibe checks to data-driven Agent Evaluation"
[10]: https://google.github.io/adk-docs/deploy/cloud-run/?utm_source=chatgpt.com "Cloud Run - Agent Development Kit (ADK)"
