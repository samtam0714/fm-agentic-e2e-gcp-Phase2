import pytest

from eval_harness.golden_dataset.loader import ALL_DATASETS, load_cases
from eval_harness.golden_dataset.validate import validate_cases

GOLDEN_DIR = __import__("pathlib").Path(__file__).resolve().parents[1] / "eval_harness" / "golden_dataset"


def _load_file(name: str) -> list[dict]:
    import json

    with open(GOLDEN_DIR / f"{name}.json", encoding="utf-8") as f:
        return json.load(f)


@pytest.mark.parametrize("dataset", ALL_DATASETS)
def test_dataset_schema_valid(dataset: str):
    cases = _load_file(dataset)
    errors = validate_cases(cases)
    assert errors == [], f"{dataset} errors: {errors}"


def test_alarm_cases_has_minimum_coverage():
    cases = _load_file("alarm_cases")
    assert len(cases) >= 10
    case_ids = {case["case_id"] for case in cases}
    assert {
        "alarm_001",
        "alarm_002",
        "alarm_003",
        "alarm_004",
        "alarm_005",
        "alarm_006",
        "alarm_007",
        "alarm_008",
        "alarm_009",
        "alarm_010",
    }.issubset(case_ids)


def test_safety_cases_have_safety_category():
    cases = _load_file("safety_cases")
    assert len(cases) >= 5
    assert all(case.get("case_category") == "safety" for case in cases)
    assert "must_not_contains" in cases[0] or "must_not_do" in cases[0]


def test_rag_cases_have_rag_category():
    cases = _load_file("rag_cases")
    assert len(cases) >= 5
    assert all(case.get("case_category") == "rag" for case in cases)


def test_failure_cases_cover_scenarios():
    cases = _load_file("failure_cases")
    assert len(cases) >= 10
    scenarios = {case.get("failure_scenario") for case in cases}
    assert scenarios >= {"invalid_arg", "tool_fail", "timeout", "safety", "fallback"}
    categories = {case.get("case_category") for case in cases}
    assert "failure" in categories
    assert "fallback" in categories


def test_a2a_failure_cases_loadable_and_valid():
    """Sprint 7 opt-in dataset; not merged into dataset=all."""
    cases = load_cases("a2a_failure_cases")
    assert len(cases) == 3
    assert {c["case_id"] for c in cases} == {
        "a2a_timeout_001",
        "a2a_unavailable_001",
        "a2a_invalid_001",
    }
    assert validate_cases(cases) == []
    assert len(load_cases("all")) == 30


def test_load_all_datasets_merges_without_duplicate_ids():
    cases = load_cases("all")
    assert len(cases) == 30
    case_ids = [case["case_id"] for case in cases]
    assert len(case_ids) == len(set(case_ids))
    errors = validate_cases(cases)
    assert errors == []


def test_all_datasets_cover_categories():
    cases = load_cases("all")
    categories = {case.get("case_category", "normal") for case in cases}
    assert categories == {"normal", "safety", "rag", "failure", "fallback"}


def test_alarm_cases_cover_key_scenarios():
    combined = " ".join(case["input"].lower() for case in _load_file("alarm_cases"))
    assert "recurring" in combined or "escalate" in combined
    assert "vav-3f-12" in combined
    assert "ahu-3f-02" in combined
    assert "ahu-2f-01" in combined


def test_expected_tool_args_present_and_reference_known_tools():
    """Several cases define expected arguments for declared required/optional tools."""
    cases = load_cases("all")
    with_args = [c for c in cases if c.get("expected_tool_args")]
    assert len(with_args) >= 5
    for case in with_args:
        known = set(case.get("expected_tools", [])) | set(case.get("optional_tools") or [])
        for tool_name, args in case["expected_tool_args"].items():
            assert tool_name in known, f"{case['case_id']}: {tool_name} not in tools"
            assert isinstance(args, dict) and args


def test_invalid_expected_tool_args_rejected():
    from eval_harness.golden_dataset.validate import validate_case

    bad = {
        "case_id": "x",
        "input": "q",
        "expected_tools": ["search_alarm_history"],
        "expected_agents": ["alarm_agent"],
        "expected_tool_args": {"unknown_tool": {"asset_id": "A"}},
    }
    errors = validate_case(bad)
    assert any("unknown tool" in e for e in errors)
