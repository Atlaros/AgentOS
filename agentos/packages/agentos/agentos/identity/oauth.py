from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import jwt


class TokenError(Exception):
    """Access token is missing, expired, or signed with the wrong key."""


def issue_access_token(
    *,
    organization_id: str,
    application_id: str,
    credential_id: str,
    scopes: list[str],
    signing_key: str,
    ttl_seconds: int = 900,
    now: datetime | None = None,
) -> str:
    issued = now or datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": application_id,
        "org": organization_id,
        "cred": credential_id,
        "scopes": scopes,
        "iat": int(issued.timestamp()),
        "exp": int((issued + timedelta(seconds=ttl_seconds)).timestamp()),
    }
    return jwt.encode(payload, signing_key, algorithm="HS256")


def verify_access_token(token: str, *, signing_key: str) -> dict[str, Any]:
    try:
        claims = jwt.decode(token, signing_key, algorithms=["HS256"])
    except jwt.PyJWTError as exc:
        raise TokenError("invalid_token") from exc
    if not isinstance(claims, dict):
        raise TokenError("invalid_token")
    return claims
