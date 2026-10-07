import argparse
import asyncio

from services.investigate import run_investigation

DEFAULT_QUERY = (
    "The HVAC alarm on Floor 3 keeps recurring. "
    "Check the issue, search policy, decide if we should create a work order, "
    "and recommend priority."
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the FM AgentOps investigate pipeline locally (full agent chain)."
    )
    parser.add_argument(
        "--query",
        default=DEFAULT_QUERY,
        help="Investigation query (default: Floor 3 HVAC demo story)",
    )
    return parser.parse_args()


async def main():
    query = parse_args().query

    print(f"\n[user]: {query}\n")
    result = await run_investigation(query, user_id="demo-user")

    print(f"\n[trace] id={result.trace_id}")
    print(f"[trace] saved to {result.trace_path}")
    print(f"\n[memory] session snapshot saved to {result.session_path}")
    snapshot = result.session_snapshot
    print(
        f"[memory] keys: {', '.join(k for k in snapshot if k not in ('similar_cases',))}"
    )
    similar = snapshot.get("similar_cases", [])
    if similar:
        print(f"[memory] similar_cases ({len(similar)}):")
        for case in similar:
            print(
                f"  - {case['case_id']}: {case['asset_id']} - {case['summary'][:80]}"
            )

    wo = result.tool_results.get("recommend_work_order", {}).get("recommendation", {})
    if wo:
        print(
            f"\n[recommendation] action={wo.get('action')} priority={wo.get('priority')}"
        )

    audit = result.tool_results.get("audit_recommendation", {})
    if audit:
        print(f"[audit] grounded={audit.get('grounded')} pass={audit.get('pass')}")


if __name__ == "__main__":
    asyncio.run(main())
