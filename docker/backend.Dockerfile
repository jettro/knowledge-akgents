# Backend image. Build context is this project directory; every akgentic package
# comes from PyPI through the pinned akgentic-framework release set in uv.lock.
#
#   docker build -f docker/backend.Dockerfile -t knowledge-akgents-backend .
#
FROM python:3.12-slim

# uv (pinned) from the official distroless image.
COPY --from=ghcr.io/astral-sh/uv:0.12.3 /uv /usr/local/bin/uv

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /workspace/app
COPY pyproject.toml ./pyproject.toml
COPY uv.lock ./uv.lock
COPY README.md ./README.md
COPY config ./config
COPY src ./src

# Install into an in-project venv from the pinned lockfile for reproducible builds.
RUN uv sync --locked --no-dev

EXPOSE 8000
CMD ["uv", "run", "--frozen", "--no-dev", "uvicorn", "knowledge_akgents.app:app", "--host", "0.0.0.0", "--port", "8000"]
