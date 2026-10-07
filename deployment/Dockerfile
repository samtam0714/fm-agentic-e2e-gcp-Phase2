# Facility Management AgentOps  -  Phase 2 API (Cloud Run / local Docker)
FROM python:3.11-slim-bookworm

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 \
    PORT=8080

# Dependency layer (cache-friendly)
COPY pyproject.toml uv.lock ./

# Application source
COPY agents/ agents/
COPY api/ api/
COPY tools/ tools/
COPY services/ services/
COPY memory/ memory/
COPY observability/ observability/
COPY eval_harness/ eval_harness/
COPY mcp_servers/ mcp_servers/
COPY skills/ skills/
COPY data/ data/

RUN uv sync --frozen --no-dev

ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health')"

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8080"]
