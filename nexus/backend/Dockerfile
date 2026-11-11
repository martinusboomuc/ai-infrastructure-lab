FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.5 /uv /uvx /usr/local/bin/

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --no-dev --locked

COPY app/ app/

# A fixed numeric UID, so the Kubernetes manifest can require runAsNonRoot and verify it.
RUN useradd --uid 10001 --no-create-home nexus
USER 10001

# The venv's own uvicorn, not `uv run`: uv would try to re-sync the environment at startup, which
# fails on the read-only root filesystem the pod runs with.
CMD ["/app/.venv/bin/uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
