FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/root/.local/bin:$PATH"

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
COPY alembic ./alembic
COPY alembic.ini ./
COPY config ./config

RUN uv sync --no-dev --no-install-project && \
    uv sync --no-dev

RUN mkdir -p /data/shorts/tmp

EXPOSE 8742

CMD ["uv", "run", "uvicorn", "shorts_pipeline.api.app:app", "--host", "0.0.0.0", "--port", "8742"]
