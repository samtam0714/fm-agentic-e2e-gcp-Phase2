from types import SimpleNamespace

from eval_harness.trace_collector import collect_trace_from_events


def _part(*, text=None, call=None, response=None):
    fc = None
    if call is not None:
        fc = SimpleNamespace(name=call[0], args=call[1])
    fr = None
    if response is not None:
        fr = SimpleNamespace(name=response[0], response=response[1])
    return SimpleNamespace(text=text, function_call=fc, function_response=fr)


def _event(author, parts):
    return SimpleNamespace(author=author, content=SimpleNamespace(parts=parts))


def test_record_event_captures_tool_args():
    events = [
        _event("alarm_agent", [_part(call=("search_alarm_history", {"asset_id": "AHU-3F-01"}))]),
        _event(
            "alarm_agent",
            [_part(response=("search_alarm_history", {"issues": []}))],
        ),
    ]
    trace = collect_trace_from_events(events)
    assert trace.tools == ["search_alarm_history"]
    assert trace.tool_args["search_alarm_history"] == [{"asset_id": "AHU-3F-01"}]


def test_record_event_captures_repeated_tool_calls():
    events = [
        _event("alarm_agent", [_part(call=("search_alarm_history", {"asset_id": "A"}))]),
        _event("alarm_agent", [_part(call=("search_alarm_history", {"asset_id": "B"}))]),
    ]
    trace = collect_trace_from_events(events)
    assert trace.tool_args["search_alarm_history"] == [{"asset_id": "A"}, {"asset_id": "B"}]


def test_record_event_handles_call_without_args():
    events = [_event("alarm_agent", [_part(call=("search_alarm_history", None))])]
    trace = collect_trace_from_events(events)
    assert trace.tool_args["search_alarm_history"] == [{}]
