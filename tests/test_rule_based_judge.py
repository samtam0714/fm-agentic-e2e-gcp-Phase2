from eval_harness.judges.rule_based_judge import judge_case
from eval_harness.metrics.scorer import build_report
from eval_harness.trace_collector import AgentTrace


def _passing_trace() -> AgentTrace:
    trace = AgentTrace()
    trace.agents = ["alarm_agent", "kb_agent", "workorder_agent", "auditor_agent"]
    trace.tools = [
        "search_alarm_history",
        "search_policy_doc",
        "recommend_work_order",
        "audit_recommendation",
    ]
    trace.texts_by_agent = {
        "alarm_agent": ["AHU-3F-01 recurring 7 events clogged filter"],
        "kb_agent": ["HVAC-MNT-003 policy applies"],
        "workorder_agent": ["escalate existing WO-2026-0142 to P1 high"],
        "auditor_agent": ["grounded: yes pass: yes"],
    }
    trace.combined_text = "\n".join(
        t for texts in trace.texts_by_agent.values() for t in texts
    )
    trace.tool_results = {
        "recommend_work_order": {
            "recommendation": {
                "action": "escalate_existing",
                "should_create": False,
            }
        }
    }
    return trace


def _alarm_001_case() -> dict:
    return {
        "case_id": "alarm_001",
        "expected_tools": [
            "search_alarm_history",
            "search_policy_doc",
            "recommend_work_order",
            "audit_recommendation",
        ],
        "expected_agents": [
            "alarm_agent",
            "kb_agent",
            "workorder_agent",
            "auditor_agent",
        ],
        "expected_answer_contains": [
            "AHU-3F-01",
            "recurring",
            "HVAC-MNT-003",
            "WO-2026-0142",
            "escalate",
        ],
        "must_not_contains": ["create a new work order"],
    }


def test_judge_case_passes_good_trace():
    result = judge_case(_alarm_001_case(), _passing_trace())
    assert result["pass"] is True
    assert result["tool_call_accuracy"] == 1.0
    assert result["missing_tools"] == []
    assert result["missing_keywords"] == []


def test_judge_case_fails_missing_tool():
    trace = _passing_trace()
    trace.tools = ["search_alarm_history"]
    result = judge_case(_alarm_001_case(), trace)
    assert result["pass"] is False
    assert "search_policy_doc" in result["missing_tools"]


def test_tool_arg_accuracy_none_when_not_specified():
    result = judge_case(_alarm_001_case(), _passing_trace())
    assert result["tool_arg_accuracy"] is None


def test_tool_arg_accuracy_full_match():
    trace = _passing_trace()
    trace.tool_args = {
        "search_alarm_history": [{"asset_id": "AHU-3F-01"}],
        "recommend_work_order": [{"asset_id": "AHU-3F-01", "event_count": 7}],
    }
    case = {
        **_alarm_001_case(),
        "expected_tool_args": {
            "search_alarm_history": {"asset_id": "AHU-3F-01"},
            "recommend_work_order": {"asset_id": "AHU-3F-01"},
        },
    }
    result = judge_case(case, trace)
    assert result["tool_arg_accuracy"] == 1.0


def test_tool_arg_accuracy_partial_match():
    trace = _passing_trace()
    trace.tool_args = {
        "search_alarm_history": [{"asset_id": "WRONG-ASSET"}],
        "recommend_work_order": [{"asset_id": "AHU-3F-01"}],
    }
    case = {
        **_alarm_001_case(),
        "expected_tool_args": {
            "search_alarm_history": {"asset_id": "AHU-3F-01"},
            "recommend_work_order": {"asset_id": "AHU-3F-01"},
        },
    }
    result = judge_case(case, trace)
    assert result["tool_arg_accuracy"] == 0.5


def test_tool_arg_accuracy_lenient_substring_match():
    """A building value of 'DemoCorp Toronto' loosely matches expected 'Toronto'."""
    trace = _passing_trace()
    trace.tool_args = {"search_alarm_history": [{"building": "DemoCorp Toronto"}]}
    case = {
        **_alarm_001_case(),
        "expected_tool_args": {"search_alarm_history": {"building": "Toronto"}},
    }
    result = judge_case(case, trace)
    assert result["tool_arg_accuracy"] == 1.0


def test_tool_arg_accuracy_zero_when_tool_not_called():
    trace = _passing_trace()
    trace.tool_args = {}
    case = {
        **_alarm_001_case(),
        "expected_tool_args": {"search_alarm_history": {"asset_id": "AHU-3F-01"}},
    }
    result = judge_case(case, trace)
    assert result["tool_arg_accuracy"] == 0.0


def test_judge_case_fails_missing_keyword():
    trace = _passing_trace()
    trace.combined_text = "no relevant keywords"
    trace.texts_by_agent = {"alarm_agent": ["no relevant keywords"]}
    result = judge_case(_alarm_001_case(), trace)
    assert result["pass"] is False
    assert len(result["missing_keywords"]) > 0


def test_judge_case_ignores_policy_quote_in_kb_agent():
    trace = _passing_trace()
    trace.texts_by_agent["kb_agent"] = [
        'HVAC-MNT-003 policy rule: "Create work order if alarm recurs more than 3 times in 30 days."'
    ]
    trace.combined_text = "\n".join(
        t for texts in trace.texts_by_agent.values() for t in texts
    )
    result = judge_case(_alarm_001_case(), trace)
    assert result["pass"] is True
    assert result["must_not_violations"] == []


def test_judge_case_ignores_policy_quote_in_workorder_agent_when_no_action():
    trace = _passing_trace()
    trace.tool_results = {
        "recommend_work_order": {
            "recommendation": {"action": "no_action", "should_create": False}
        }
    }
    trace.texts_by_agent["workorder_agent"] = [
        "Action: no_action. Continue monitoring. Policy HVAC-MNT-003 requires >3 events "
        "to create a new work order."
    ]
    trace.combined_text = "\n".join(
        t for texts in trace.texts_by_agent.values() for t in texts
    )
    case = {
        "case_id": "alarm_003",
        "expected_tools": ["recommend_work_order"],
        "expected_agents": ["workorder_agent"],
        "expected_answer_contains": ["monitor"],
        "must_not_contains": ["create a new work order"],
    }
    result = judge_case(case, trace)
    assert result["pass"] is True
    assert result["must_not_violations"] == []


def test_judge_case_fails_create_new_violation():
    trace = _passing_trace()
    trace.tool_results = {
        "recommend_work_order": {
            "recommendation": {"action": "create_new", "should_create": True}
        }
    }
    trace.texts_by_agent["workorder_agent"] = ["create new work order for AHU-3F-01"]
    trace.combined_text = "\n".join(
        t for texts in trace.texts_by_agent.values() for t in texts
    )
    result = judge_case(_alarm_001_case(), trace)
    assert result["pass"] is False
    assert len(result["must_not_violations"]) > 0


def test_build_report_aggregates():
    report = build_report(
        [
            {
                "pass": True,
                "tool_call_accuracy": 1.0,
                "agent_coverage": 1.0,
                "answer_keyword_score": 1.0,
                "task_success": 0.9,
                "groundedness": 0.95,
            },
            {
                "pass": False,
                "tool_call_accuracy": 0.5,
                "agent_coverage": 0.5,
                "answer_keyword_score": 0.5,
                "task_success": 0.4,
                "groundedness": 0.5,
            },
        ]
    )
    assert report["case_count"] == 2
    assert report["pass_count"] == 1
    assert report["fail_count"] == 1
    assert report["pass_rate"] == 0.5
    assert report["avg_task_success"] == 0.65
    assert report["avg_groundedness"] == 0.725


def test_judge_case_scores_failure_recovery():
    trace = _passing_trace()
    trace.texts_by_agent["alarm_agent"] = [
        "AHU-UNKNOWN-99 has no issues; recommend monitor only"
    ]
    trace.combined_text = "\n".join(
        t for texts in trace.texts_by_agent.values() for t in texts
    )
    case = {
        "case_id": "fail_001",
        "failure_scenario": "invalid_arg",
        "expected_tools": [
            "search_alarm_history",
            "search_policy_doc",
            "recommend_work_order",
            "audit_recommendation",
        ],
        "expected_agents": [
            "alarm_agent",
            "kb_agent",
            "workorder_agent",
            "auditor_agent",
        ],
        "expected_answer_contains": ["AHU-UNKNOWN-99", "monitor"],
        "expected_recovery_contains": ["monitor"],
    }
    result = judge_case(case, trace)
    assert result["failure_recovery"] == 1.0


def test_judge_case_ignores_optional_tools():
    trace = _passing_trace()
    trace.tools = [
        "search_policy_doc",
        "recommend_work_order",
        "audit_recommendation",
    ]
    case = {
        "case_id": "rag_004",
        "expected_tools": [
            "search_alarm_history",
            "search_policy_doc",
            "recommend_work_order",
            "audit_recommendation",
        ],
        "expected_agents": ["alarm_agent"],
        "expected_answer_contains": ["HVAC-MNT-003"],
        "optional_tools": ["search_alarm_history"],
    }
    result = judge_case(case, trace)
    assert result["pass"] is True
    assert result["missing_tools"] == []


def test_judge_case_accepts_keyword_alternatives():
    trace = _passing_trace()
    trace.texts_by_agent["workorder_agent"] = [
        "AHU-3F-02 shows a single transient event; continue monitoring."
    ]
    trace.combined_text = "\n".join(
        t for texts in trace.texts_by_agent.values() for t in texts
    )
    case = {
        "case_id": "alarm_009",
        "expected_tools": ["recommend_work_order"],
        "expected_agents": ["workorder_agent"],
        "expected_answer_contains": ["not recurring", "monitor"],
    }
    result = judge_case(case, trace)
    assert result["pass"] is True
    assert result["missing_keywords"] == []


def test_judge_case_fail_004_refusal_path():
    trace = AgentTrace()
    trace.agents = ["alarm_agent", "kb_agent", "workorder_agent", "auditor_agent"]
    trace.tools = ["audit_recommendation"]
    trace.texts_by_agent = {
        "alarm_agent": ["Cannot create a work order without an asset_id."],
        "kb_agent": ["Need asset identification first."],
        "workorder_agent": ["Refused: missing asset context."],
        "auditor_agent": ["Audit confirms refusal without asset_id."],
    }
    trace.combined_text = "\n".join(
        t for texts in trace.texts_by_agent.values() for t in texts
    )
    case = {
        "case_id": "fail_004",
        "failure_scenario": "tool_fail",
        "expected_tools": ["audit_recommendation"],
        "expected_agents": [
            "alarm_agent",
            "kb_agent",
            "workorder_agent",
            "auditor_agent",
        ],
        "expected_answer_contains": ["asset"],
        "expected_recovery_contains": ["asset"],
        "optional_tools": [
            "search_alarm_history",
            "search_policy_doc",
            "recommend_work_order",
        ],
    }
    result = judge_case(case, trace)
    assert result["pass"] is True
    assert result["failure_recovery"] == 1.0
