# Backend image. Build context is the PARENT dir (akgents/) so the local editable
# akgentic-tool and akgentic-llm checkouts are available to uv.
#
#   docker build -f knowledge-akgents/docker/backend.Dockerfile -t knowledge-akgents-backend ..
#
FROM python:3.12-slim

# uv (pinned) from the official distroless image.
COPY --from=ghcr.io/astral-sh/uv:0.12.3 /uv /usr/local/bin/uv

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Local editable sibling packages referenced by [tool.uv.sources] as ../akgentic-*.
# Layout inside the image mirrors the host: /workspace/{akgentic-tool,akgentic-llm,app}.
WORKDIR /workspace
COPY akgentic-tool/ ./akgentic-tool/
COPY akgentic-llm/ ./akgentic-llm/

WORKDIR /workspace/app
COPY knowledge-akgents/pyproject.toml ./pyproject.toml
COPY knowledge-akgents/uv.lock ./uv.lock
COPY knowledge-akgents/README.md ./README.md
COPY knowledge-akgents/config ./config
COPY knowledge-akgents/src ./src

# Install into an in-project venv from the pinned lockfile for reproducible builds.
RUN uv sync --locked --no-dev

EXPOSE 8000
CMD ["uv", "run", "--frozen", "--no-dev", "uvicorn", "knowledge_akgents.app:app", "--host", "0.0.0.0", "--port", "8000"]
