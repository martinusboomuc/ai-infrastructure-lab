"""MLflow request header provider for the self-hosted tracking server (ADR-0013).

Registered via the `mlflow.request_header_provider` entry point (see pyproject.toml), MLflow
calls every registered provider on every REST request it makes — this is the only supported way
to attach custom headers to the MLflow client's own HTTP calls, since MLflow has no built-in
option for arbitrary headers.

A no-op wherever CF_ACCESS_CLIENT_ID/CF_ACCESS_CLIENT_SECRET aren't set — local training on the
LAN reaches the tracking server directly and never needs these; only a client going through the
Cloudflare Tunnel (the deployed Container App) does.
"""

from __future__ import annotations

import os

from mlflow.tracking.request_header.abstract_request_header_provider import RequestHeaderProvider

_CLIENT_ID_ENV_VAR = "CF_ACCESS_CLIENT_ID"
_CLIENT_SECRET_ENV_VAR = "CF_ACCESS_CLIENT_SECRET"


class CloudflareAccessRequestHeaderProvider(RequestHeaderProvider):
    def in_context(self) -> bool:
        return bool(os.environ.get(_CLIENT_ID_ENV_VAR)) and bool(
            os.environ.get(_CLIENT_SECRET_ENV_VAR)
        )

    def request_headers(self) -> dict[str, str]:
        return {
            "CF-Access-Client-Id": os.environ[_CLIENT_ID_ENV_VAR],
            "CF-Access-Client-Secret": os.environ[_CLIENT_SECRET_ENV_VAR],
        }
