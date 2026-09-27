FROM python:3.12-slim

# The tailscale CLI is what app/tailscale.py shells out to — it talks to the host's tailscaled
# over the bind-mounted socket (see docker-compose.yml), not a separate identity of its own.
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates \
    && curl -fsSL https://tailscale.com/install.sh | sh \
    && apt-get purge -y curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.5 /uv /uvx /usr/local/bin/

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --no-dev --locked

COPY app/ app/

CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
