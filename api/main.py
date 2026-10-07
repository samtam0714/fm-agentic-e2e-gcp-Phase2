"""FastAPI application entrypoint."""

from __future__ import annotations

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse

from api.middleware import TraceIdMiddleware
from api.routes.investigate import router as investigate_router
from api.schemas import HealthResponse
from observability.dashboard.metrics import build_reliability_metrics
from observability.dashboard.render import render_reliability_html
from observability.logging import configure_structured_logging

load_dotenv()
configure_structured_logging()

app = FastAPI(
    title="Facility Management AgentOps",
    description="Phase 2 investigate API for reliable building-operations agent workflows.",
    version="0.1.0",
)
app.add_middleware(TraceIdMiddleware)
app.include_router(investigate_router)


@app.get("/health", response_model=HealthResponse, tags=["health"])
async def health() -> HealthResponse:
    return HealthResponse()


@app.get("/dashboard", response_class=HTMLResponse, tags=["observability"])
async def reliability_dashboard() -> HTMLResponse:
    metrics = build_reliability_metrics()
    return HTMLResponse(render_reliability_html(metrics))


@app.get("/dashboard/metrics", tags=["observability"])
async def reliability_dashboard_metrics() -> JSONResponse:
    return JSONResponse(build_reliability_metrics())


def main() -> None:
    import uvicorn

    uvicorn.run("api.main:app", host="0.0.0.0", port=8080, reload=False)


if __name__ == "__main__":
    main()
