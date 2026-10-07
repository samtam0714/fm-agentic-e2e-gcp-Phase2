"""HTML renderer for the reliability dashboard."""

from __future__ import annotations

import html
from typing import Any


def _fmt(value: Any, *, pct: bool = False, suffix: str = "") -> str:
    if value is None:
        return " - "
    if pct and isinstance(value, (int, float)):
        return f"{value * 100:.1f}%"
    if isinstance(value, float):
        return f"{value:.4g}{suffix}"
    return f"{value}{suffix}"


def _gate_label(value: bool | None) -> str:
    if value is True:
        return "PASS"
    if value is False:
        return "FAIL"
    return " - "


def render_reliability_html(metrics: dict[str, Any]) -> str:
    """Return a self-contained HTML page for /dashboard."""
    latency = metrics.get("latency") or {}
    gate = metrics.get("release_gate") or {}
    cost = metrics.get("cost_estimate") or {}
    summary = metrics.get("eval_summary") or {}
    failing = metrics.get("top_failing_cases") or []
    source = metrics.get("source") or {}

    fail_rows = ""
    if failing:
        for case in failing:
            fail_rows += (
                "<tr>"
                f"<td>{html.escape(str(case.get('case_id') or ''))}</td>"
                f"<td>{html.escape(str(case.get('case_category') or ''))}</td>"
                f"<td>{html.escape(', '.join(case.get('missing_tools') or []) or ' - ')}</td>"
                f"<td>{html.escape(str(case.get('llm_reason') or ' - '))}</td>"
                "</tr>"
            )
    else:
        fail_rows = '<tr><td colspan="4">No failing cases in latest eval report.</td></tr>'

    breakdown = summary.get("case_category_breakdown") or {}
    breakdown_items = "".join(
        f"<li><strong>{html.escape(cat)}</strong>: "
        f"{data.get('pass_count', 0)}/{data.get('case_count', 0)} "
        f"(pass_rate={_fmt(data.get('pass_rate'), pct=True)})</li>"
        for cat, data in sorted(breakdown.items())
    ) or "<li>No category breakdown</li>"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>FM AgentOps Reliability Dashboard</title>
  <style>
    :root {{
      --bg: #0f1419;
      --panel: #1a222c;
      --text: #e7ecf1;
      --muted: #9aa7b5;
      --accent: #3d9bfd;
      --ok: #3dd68c;
      --bad: #ff6b6b;
      --line: #2a3542;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "IBM Plex Sans", "Segoe UI", sans-serif;
      background:
        radial-gradient(1200px 600px at 10% -10%, #1c2a3a 0%, transparent 60%),
        radial-gradient(900px 500px at 100% 0%, #243018 0%, transparent 55%),
        var(--bg);
      color: var(--text);
      min-height: 100vh;
    }}
    main {{ max-width: 1100px; margin: 0 auto; padding: 2.5rem 1.25rem 4rem; }}
    h1 {{ font-size: 1.75rem; margin: 0 0 0.35rem; letter-spacing: -0.02em; }}
    .sub {{ color: var(--muted); margin-bottom: 1.75rem; font-size: 0.95rem; }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 0.85rem;
      margin-bottom: 1.5rem;
    }}
    .card {{
      background: color-mix(in srgb, var(--panel) 92%, black);
      border: 1px solid var(--line);
      border-radius: 10px;
      padding: 1rem 1.1rem;
    }}
    .card .label {{ color: var(--muted); font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.06em; }}
    .card .value {{ font-size: 1.45rem; margin-top: 0.35rem; font-weight: 600; }}
    .pass {{ color: var(--ok); }}
    .fail {{ color: var(--bad); }}
    section {{
      background: color-mix(in srgb, var(--panel) 92%, black);
      border: 1px solid var(--line);
      border-radius: 12px;
      padding: 1.15rem 1.25rem;
      margin-bottom: 1rem;
    }}
    section h2 {{ margin: 0 0 0.75rem; font-size: 1.05rem; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 0.9rem; }}
    th, td {{ text-align: left; padding: 0.55rem 0.4rem; border-bottom: 1px solid var(--line); vertical-align: top; }}
    th {{ color: var(--muted); font-weight: 500; font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.04em; }}
    ul {{ margin: 0; padding-left: 1.1rem; color: var(--text); }}
    code {{ color: var(--accent); font-size: 0.85rem; }}
  </style>
</head>
<body>
  <main>
    <h1>FM AgentOps Reliability</h1>
    <p class="sub">
      Local eval / gate / trace snapshot ·
      source <code>{html.escape(str(source.get("reports_dir") or ""))}</code>
    </p>

    <div class="grid">
      <div class="card"><div class="label">p50 latency</div><div class="value">{_fmt(latency.get("p50_seconds"), suffix="s")}</div></div>
      <div class="card"><div class="label">p95 latency</div><div class="value">{_fmt(latency.get("p95_seconds"), suffix="s")}</div></div>
      <div class="card"><div class="label">Judge pass rate</div><div class="value">{_fmt(metrics.get("judge_pass_rate"), pct=True)}</div></div>
      <div class="card"><div class="label">Tool error rate</div><div class="value">{_fmt(metrics.get("tool_error_rate"), pct=True)}</div></div>
      <div class="card"><div class="label">Fallback rate</div><div class="value">{_fmt(metrics.get("fallback_rate"), pct=True)}</div></div>
      <div class="card"><div class="label">Failure recovery</div><div class="value">{_fmt(metrics.get("failure_recovery_rate"), pct=True)}</div></div>
      <div class="card"><div class="label">Avg cost / request</div><div class="value">${_fmt(cost.get("avg_cost_usd"))}</div></div>
      <div class="card">
        <div class="label">Release gate</div>
        <div class="value {"pass" if gate.get("overall_pass") is True else "fail" if gate.get("overall_pass") is False else ""}">
          {_gate_label(gate.get("overall_pass"))}
        </div>
      </div>
    </div>

    <section>
      <h2>Eval summary</h2>
      <p>
        Cases: {_fmt(summary.get("pass_count"))}/{_fmt(summary.get("case_count"))} passed ·
        task_success={_fmt(summary.get("avg_task_success"))} ·
        groundedness={_fmt(summary.get("avg_groundedness"))}
      </p>
      <ul>{breakdown_items}</ul>
      <p style="color:var(--muted);margin:0.75rem 0 0;font-size:0.85rem;">
        Gate absolute={_gate_label(gate.get("absolute_pass"))} ·
        regression={_gate_label(gate.get("regression_pass"))} ·
        traces scanned={_fmt(source.get("trace_span_count"))} spans ·
        cost tokens in/out={_fmt(cost.get("total_tokens_input"))}/{_fmt(cost.get("total_tokens_output"))}
      </p>
    </section>

    <section>
      <h2>Top failing eval cases</h2>
      <table>
        <thead><tr><th>Case</th><th>Category</th><th>Missing tools</th><th>Reason</th></tr></thead>
        <tbody>{fail_rows}</tbody>
      </table>
    </section>
  </main>
</body>
</html>
"""
