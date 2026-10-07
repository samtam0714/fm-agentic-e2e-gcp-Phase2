"""Export traces + eval/gate results to BigQuery (Sprint 4 / 2.4.2).

Design:
- Disabled by default when ENABLE_BIGQUERY is unset; no GCP calls are made.
- When enabled, writes agent_spans, eval_runs, eval_cases, and gate_results.
- Failures are logged without blocking investigation, evaluation, or gates.
- Missing tables are created on first write.

Environment variables:
  ENABLE_BIGQUERY=1|true|yes
  GOOGLE_CLOUD_PROJECT (required when enabled)
  BIGQUERY_DATASET (optional; defaults to fm_agentops_observability)
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Protocol

from observability.logging.structured_logger import get_logger
from observability.tracing.models import TraceSpan

_log = get_logger(__name__)

DEFAULT_DATASET = "fm_agentops_observability"

_AGENT_SPANS_SCHEMA = [
    {"name": "inserted_at", "type": "TIMESTAMP", "mode": "REQUIRED"},
    {"name": "trace_id", "type": "STRING", "mode": "REQUIRED"},
    {"name": "agent", "type": "STRING", "mode": "NULLABLE"},
    {"name": "step", "type": "STRING", "mode": "NULLABLE"},
    {"name": "span_type", "type": "STRING", "mode": "NULLABLE"},
    {"name": "status", "type": "STRING", "mode": "NULLABLE"},
    {"name": "latency_ms", "type": "FLOAT", "mode": "NULLABLE"},
    {"name": "tokens_input", "type": "INTEGER", "mode": "NULLABLE"},
    {"name": "tokens_output", "type": "INTEGER", "mode": "NULLABLE"},
    {"name": "tool_calls", "type": "STRING", "mode": "NULLABLE"},
    {"name": "input_summary", "type": "STRING", "mode": "NULLABLE"},
    {"name": "output_summary", "type": "STRING", "mode": "NULLABLE"},
    {"name": "span_timestamp", "type": "FLOAT", "mode": "NULLABLE"},
]

_EVAL_RUNS_SCHEMA = [
    {"name": "inserted_at", "type": "TIMESTAMP", "mode": "REQUIRED"},
    {"name": "run_id", "type": "STRING", "mode": "REQUIRED"},
    {"name": "schema_version", "type": "STRING", "mode": "NULLABLE"},
    {"name": "case_count", "type": "INTEGER", "mode": "NULLABLE"},
    {"name": "pass_count", "type": "INTEGER", "mode": "NULLABLE"},
    {"name": "fail_count", "type": "INTEGER", "mode": "NULLABLE"},
    {"name": "pass_rate", "type": "FLOAT", "mode": "NULLABLE"},
    {"name": "avg_tool_call_accuracy", "type": "FLOAT", "mode": "NULLABLE"},
    {"name": "avg_tool_arg_accuracy", "type": "FLOAT", "mode": "NULLABLE"},
    {"name": "avg_task_success", "type": "FLOAT", "mode": "NULLABLE"},
    {"name": "avg_groundedness", "type": "FLOAT", "mode": "NULLABLE"},
    {"name": "avg_failure_recovery", "type": "FLOAT", "mode": "NULLABLE"},
    {"name": "p50_latency_seconds", "type": "FLOAT", "mode": "NULLABLE"},
    {"name": "p95_latency_seconds", "type": "FLOAT", "mode": "NULLABLE"},
    {"name": "critical_failures", "type": "INTEGER", "mode": "NULLABLE"},
    {"name": "report_json", "type": "STRING", "mode": "NULLABLE"},
]

_EVAL_CASES_SCHEMA = [
    {"name": "inserted_at", "type": "TIMESTAMP", "mode": "REQUIRED"},
    {"name": "run_id", "type": "STRING", "mode": "REQUIRED"},
    {"name": "case_id", "type": "STRING", "mode": "REQUIRED"},
    {"name": "case_category", "type": "STRING", "mode": "NULLABLE"},
    {"name": "pass", "type": "BOOLEAN", "mode": "NULLABLE"},
    {"name": "tool_call_accuracy", "type": "FLOAT", "mode": "NULLABLE"},
    {"name": "tool_arg_accuracy", "type": "FLOAT", "mode": "NULLABLE"},
    {"name": "agent_coverage", "type": "FLOAT", "mode": "NULLABLE"},
    {"name": "answer_keyword_score", "type": "FLOAT", "mode": "NULLABLE"},
    {"name": "task_success", "type": "FLOAT", "mode": "NULLABLE"},
    {"name": "groundedness", "type": "FLOAT", "mode": "NULLABLE"},
    {"name": "failure_recovery", "type": "FLOAT", "mode": "NULLABLE"},
    {"name": "latency_seconds", "type": "FLOAT", "mode": "NULLABLE"},
    {"name": "trace_id", "type": "STRING", "mode": "NULLABLE"},
    {"name": "llm_pass", "type": "BOOLEAN", "mode": "NULLABLE"},
    {"name": "rule_pass", "type": "BOOLEAN", "mode": "NULLABLE"},
    {"name": "case_json", "type": "STRING", "mode": "NULLABLE"},
]

_GATE_RESULTS_SCHEMA = [
    {"name": "inserted_at", "type": "TIMESTAMP", "mode": "REQUIRED"},
    {"name": "gate_id", "type": "STRING", "mode": "REQUIRED"},
    {"name": "overall_pass", "type": "BOOLEAN", "mode": "NULLABLE"},
    {"name": "absolute_pass", "type": "BOOLEAN", "mode": "NULLABLE"},
    {"name": "regression_pass", "type": "BOOLEAN", "mode": "NULLABLE"},
    {"name": "result_json", "type": "STRING", "mode": "NULLABLE"},
]

_TABLE_SCHEMAS: dict[str, list[dict[str, str]]] = {
    "agent_spans": _AGENT_SPANS_SCHEMA,
    "eval_runs": _EVAL_RUNS_SCHEMA,
    "eval_cases": _EVAL_CASES_SCHEMA,
    "gate_results": _GATE_RESULTS_SCHEMA,
}


class _BQClient(Protocol):
    def ensure_ready(self, *, project_id: str, dataset_id: str) -> None: ...

    def insert_rows(
        self, *, project_id: str, dataset_id: str, table_id: str, rows: list[dict[str, Any]]
    ) -> list[dict[str, Any]]: ...


def bigquery_enabled() -> bool:
    return os.getenv("ENABLE_BIGQUERY", "").strip().lower() in {"1", "true", "yes"}


def dataset_id() -> str:
    return os.getenv("BIGQUERY_DATASET", DEFAULT_DATASET).strip() or DEFAULT_DATASET


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def spans_to_rows(spans: list[TraceSpan], *, inserted_at: str | None = None) -> list[dict[str, Any]]:
    ts = inserted_at or _now_iso()
    rows: list[dict[str, Any]] = []
    for span in spans:
        rows.append(
            {
                "inserted_at": ts,
                "trace_id": span.trace_id,
                "agent": span.agent,
                "step": span.step,
                "span_type": span.span_type,
                "status": span.status,
                "latency_ms": span.latency_ms,
                "tokens_input": span.tokens_input,
                "tokens_output": span.tokens_output,
                "tool_calls": ",".join(span.tool_calls) if span.tool_calls else None,
                "input_summary": (span.input_summary or "")[:2000] or None,
                "output_summary": (span.output_summary or "")[:2000] or None,
                "span_timestamp": span.timestamp,
            }
        )
    return rows


def eval_report_to_rows(
    report: dict[str, Any],
    *,
    run_id: str | None = None,
    inserted_at: str | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str]:
    """Return (eval_run_rows, eval_case_rows, run_id)."""
    ts = inserted_at or _now_iso()
    rid = run_id or f"eval_{uuid.uuid4().hex[:12]}"
    # Strip nested cases from aggregate JSON to keep row smaller; cases go to eval_cases.
    report_without_cases = {k: v for k, v in report.items() if k != "cases"}
    run_row = {
        "inserted_at": ts,
        "run_id": rid,
        "schema_version": report.get("schema_version"),
        "case_count": report.get("case_count"),
        "pass_count": report.get("pass_count"),
        "fail_count": report.get("fail_count"),
        "pass_rate": report.get("pass_rate"),
        "avg_tool_call_accuracy": report.get("avg_tool_call_accuracy"),
        "avg_tool_arg_accuracy": report.get("avg_tool_arg_accuracy"),
        "avg_task_success": report.get("avg_task_success"),
        "avg_groundedness": report.get("avg_groundedness"),
        "avg_failure_recovery": report.get("avg_failure_recovery"),
        "p50_latency_seconds": report.get("p50_latency_seconds"),
        "p95_latency_seconds": report.get("p95_latency_seconds"),
        "critical_failures": report.get("critical_failures"),
        "report_json": json.dumps(report_without_cases, default=str),
    }
    case_rows: list[dict[str, Any]] = []
    for case in report.get("cases") or []:
        case_rows.append(
            {
                "inserted_at": ts,
                "run_id": rid,
                "case_id": case.get("case_id", ""),
                "case_category": case.get("case_category"),
                "pass": case.get("pass"),
                "tool_call_accuracy": case.get("tool_call_accuracy"),
                "tool_arg_accuracy": case.get("tool_arg_accuracy"),
                "agent_coverage": case.get("agent_coverage"),
                "answer_keyword_score": case.get("answer_keyword_score"),
                "task_success": case.get("task_success"),
                "groundedness": case.get("groundedness"),
                "failure_recovery": case.get("failure_recovery"),
                "latency_seconds": case.get("latency_seconds"),
                "trace_id": case.get("trace_id"),
                "llm_pass": case.get("llm_pass"),
                "rule_pass": case.get("rule_pass"),
                "case_json": json.dumps(case, default=str),
            }
        )
    return [run_row], case_rows, rid


def gate_result_to_rows(
    result: dict[str, Any],
    *,
    gate_id: str | None = None,
    inserted_at: str | None = None,
) -> list[dict[str, Any]]:
    ts = inserted_at or _now_iso()
    absolute = result.get("absolute") or {}
    regression = result.get("regression")
    return [
        {
            "inserted_at": ts,
            "gate_id": gate_id or f"gate_{uuid.uuid4().hex[:12]}",
            "overall_pass": result.get("pass"),
            "absolute_pass": absolute.get("pass"),
            "regression_pass": None if regression is None else regression.get("pass"),
            "result_json": json.dumps(result, default=str),
        }
    ]


class GoogleBigQueryClient:
    """Thin wrapper around google.cloud.bigquery.Client with auto-create."""

    def __init__(self, client: Any | None = None) -> None:
        if client is None:
            from google.cloud import bigquery

            client = bigquery.Client()
        self._client = client
        self._bigquery = None

    def _bq(self) -> Any:
        if self._bigquery is None:
            from google.cloud import bigquery

            self._bigquery = bigquery
        return self._bigquery

    def ensure_ready(self, *, project_id: str, dataset_id: str) -> None:
        bq = self._bq()
        dataset_ref = bq.Dataset(f"{project_id}.{dataset_id}")
        dataset_ref.location = os.getenv("BIGQUERY_LOCATION", "US")
        self._client.create_dataset(dataset_ref, exists_ok=True)
        for table_id, schema_fields in _TABLE_SCHEMAS.items():
            schema = [bq.SchemaField(f["name"], f["type"], mode=f["mode"]) for f in schema_fields]
            table = bq.Table(f"{project_id}.{dataset_id}.{table_id}", schema=schema)
            self._client.create_table(table, exists_ok=True)

    def insert_rows(
        self, *, project_id: str, dataset_id: str, table_id: str, rows: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        if not rows:
            return []
        table = f"{project_id}.{dataset_id}.{table_id}"
        errors = self._client.insert_rows_json(table, rows)
        return list(errors or [])


def _resolve_project(project_id: str | None) -> str | None:
    return (project_id or os.getenv("GOOGLE_CLOUD_PROJECT", "")).strip() or None


def _export(
    *,
    table_rows: dict[str, list[dict[str, Any]]],
    project_id: str | None = None,
    client: _BQClient | None = None,
    log_event: str,
    extra_log: dict[str, Any] | None = None,
) -> bool:
    if not bigquery_enabled():
        return False
    if not any(table_rows.values()):
        return False

    project = _resolve_project(project_id)
    if not project:
        _log.warning("bigquery.skipped", reason="GOOGLE_CLOUD_PROJECT missing")
        return False

    ds = dataset_id()
    try:
        bq_client: _BQClient = client or GoogleBigQueryClient()
        bq_client.ensure_ready(project_id=project, dataset_id=ds)
        for table_id, rows in table_rows.items():
            if not rows:
                continue
            errors = bq_client.insert_rows(
                project_id=project, dataset_id=ds, table_id=table_id, rows=rows
            )
            if errors:
                raise RuntimeError(f"insert_rows_json errors for {table_id}: {errors[:3]}")
        payload = {
            "project": project,
            "dataset": ds,
            "tables": {k: len(v) for k, v in table_rows.items() if v},
        }
        if extra_log:
            payload.update(extra_log)
        _log.info(log_event, **payload)
        return True
    except Exception as exc:
        _log.warning(
            "bigquery.export_failed",
            error=str(exc),
            **(extra_log or {}),
        )
        return False


def export_spans_to_bigquery(
    spans: list[TraceSpan],
    *,
    local_trace_id: str,
    project_id: str | None = None,
    client: _BQClient | None = None,
) -> bool:
    """Export spans when ENABLE_BIGQUERY is on. Returns True if exported."""
    rows = spans_to_rows(spans)
    return _export(
        table_rows={"agent_spans": rows},
        project_id=project_id,
        client=client,
        log_event="bigquery.spans_exported",
        extra_log={"local_trace_id": local_trace_id, "span_count": len(rows)},
    )


def export_eval_report_to_bigquery(
    report: dict[str, Any],
    *,
    run_id: str | None = None,
    project_id: str | None = None,
    client: _BQClient | None = None,
) -> bool:
    """Export eval aggregate + per-case rows. Returns True if exported."""
    run_rows, case_rows, rid = eval_report_to_rows(report, run_id=run_id)
    return _export(
        table_rows={"eval_runs": run_rows, "eval_cases": case_rows},
        project_id=project_id,
        client=client,
        log_event="bigquery.eval_exported",
        extra_log={"run_id": rid, "case_count": len(case_rows)},
    )


def export_gate_result_to_bigquery(
    result: dict[str, Any],
    *,
    gate_id: str | None = None,
    project_id: str | None = None,
    client: _BQClient | None = None,
) -> bool:
    """Export release-gate result. Returns True if exported."""
    rows = gate_result_to_rows(result, gate_id=gate_id)
    return _export(
        table_rows={"gate_results": rows},
        project_id=project_id,
        client=client,
        log_event="bigquery.gate_exported",
        extra_log={"gate_id": rows[0]["gate_id"], "overall_pass": rows[0]["overall_pass"]},
    )
