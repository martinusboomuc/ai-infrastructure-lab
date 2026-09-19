# Serving image for the BankML Credit Risk FastAPI app (ROADMAP Phase 4).
#
# Build context is mlops/ (see .dockerignore) — `docker build -f mlops/Dockerfile mlops` from
# the repo root, or `docker build .` from inside mlops/. This image serves only; it does not
# ingest data, train, or need BANKML_DATA_ROOT to point at raw Home Credit data — it needs
# MLFLOW_TRACKING_URI to reach a registry with a `credit-champion@production` model, and a
# writable path for the prediction log (BANKML_PREDICTION_LOG_DIR).

FROM python:3.12-slim AS base

RUN pip install --no-cache-dir uv

WORKDIR /app

# Dependencies first, separate from source, so an app-code-only change doesn't invalidate uv's
# resolved layer.
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-install-project --no-dev

COPY src/ src/
COPY configs/ configs/
RUN uv sync --locked --no-dev

ENV PATH="/app/.venv/bin:$PATH" \
    BANKML_PREDICTION_LOG_DIR=/data/predictions

RUN mkdir -p /data/predictions && useradd --create-home --uid 1000 bankml \
    && chown -R bankml:bankml /app /data
USER bankml

EXPOSE 8000

CMD ["uvicorn", "bankml.serving.app:app", "--host", "0.0.0.0", "--port", "8000"]
