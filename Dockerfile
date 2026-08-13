FROM ghcr.io/astral-sh/uv:0.6.17 AS uv

FROM python:3.12-slim AS runtime

COPY --from=uv /uv /uvx /bin/

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

COPY alembic.ini ./
COPY migrations ./migrations
COPY src ./src
RUN uv sync --frozen --no-dev

RUN useradd --create-home --uid 10001 terrasatch
USER terrasatch

EXPOSE 8000

CMD ["uvicorn", "terrasatch.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]