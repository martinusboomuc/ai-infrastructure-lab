"""Prometheus metrics for the serving app (Phase 5, ARCHITECTURE.md §7).

Domain-agnostic HTTP metrics (request count, latency) come from one middleware wired onto the
FastAPI app in `serving/app.py`; the `bankml_predictions_total` counter is domain-aware (it takes
a `domain` label) since which domain scored a request is meaningful, but nothing here should ever
need a second, domain-specific middleware — a new domain gets this for free.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from starlette.requests import Request
from starlette.responses import Response

REQUEST_COUNT = Counter(
    "bankml_requests_total",
    "Total HTTP requests handled by the serving app.",
    ["method", "path", "status_code"],
)
REQUEST_LATENCY = Histogram(
    "bankml_request_duration_seconds",
    "HTTP request latency in seconds.",
    ["method", "path"],
)
PREDICTIONS = Counter(
    "bankml_predictions_total",
    "Total scored predictions, by domain and decision.",
    ["domain", "decision"],
)


async def metrics_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    start = time.perf_counter()
    response = await call_next(request)
    duration = time.perf_counter() - start

    # The matched route template (e.g. "/predict/credit"), not the raw URL — the raw path would
    # be fine today since no route takes a path parameter, but labeling by template is what keeps
    # this correct if one ever does, instead of exploding cardinality per distinct URL requested.
    route = request.scope.get("route")
    path = route.path if route is not None else request.url.path

    REQUEST_COUNT.labels(method=request.method, path=path, status_code=response.status_code).inc()
    REQUEST_LATENCY.labels(method=request.method, path=path).observe(duration)
    return response


def render_metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
