"""Bearer-key authentication for the serving API (ADR-0017).

Each caller has its own named key, so one can be revoked without touching the others and every
logged prediction records which caller made it. Keys come from `BANKML_API_KEYS` as
`name:key` pairs separated by commas, set from a Container App secret, never from the image.

The check fails closed: with no keys configured, protected endpoints answer 503 rather than
serving anyone. `/health` and the OpenAPI docs stay open, because the platform's own probes and
Nexus read them and they carry nothing private.
"""

from __future__ import annotations

import hmac
import os
from typing import Annotated

from fastapi import HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

API_KEYS_ENV = "BANKML_API_KEYS"

_bearer = HTTPBearer(auto_error=False, description="A per-client key from BANKML_API_KEYS.")


def parse_api_keys(raw: str | None) -> dict[str, str]:
    """`name:key,name:key` into {name: key}. Rejects a malformed entry, a duplicate name, and a
    key shorter than 32 characters, so a typo in the secret is a startup error, not a weak key.
    """
    keys: dict[str, str] = {}
    for entry in (raw or "").split(","):
        entry = entry.strip()
        if not entry:
            continue
        name, sep, key = entry.partition(":")
        if not sep or not name or not key:
            raise ValueError(f"{API_KEYS_ENV}: entry must be name:key")
        if name in keys:
            raise ValueError(f"{API_KEYS_ENV}: duplicate client name {name!r}")
        if len(key) < 32:
            raise ValueError(f"{API_KEYS_ENV}: key for {name!r} is shorter than 32 characters")
        keys[name] = key
    return keys


def load_api_keys() -> dict[str, str]:
    return parse_api_keys(os.environ.get(API_KEYS_ENV))


def identify_client(keys: dict[str, str], presented: str) -> str | None:
    """The name of the client whose key matches, comparing every key in constant time."""
    match = None
    for name, key in keys.items():
        if hmac.compare_digest(key.encode(), presented.encode()):
            match = name
    return match


class ApiKeyAuth:
    """FastAPI dependency. Holds the key table so the app loads it once at startup."""

    def __init__(self) -> None:
        self.keys: dict[str, str] = {}

    def __call__(
        self, credentials: Annotated[HTTPAuthorizationCredentials | None, Security(_bearer)]
    ) -> str:
        if not self.keys:
            raise HTTPException(status_code=503, detail="authentication is not configured")
        client = identify_client(self.keys, credentials.credentials) if credentials else None
        if client is None:
            raise HTTPException(
                status_code=401,
                detail="missing or invalid API key",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return client
