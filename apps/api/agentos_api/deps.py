from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Annotated

from agentos.db.models import ApiCredential, Application
from agentos.db.session import get_session_factory, set_org_context
from agentos.identity.oauth import TokenError, verify_access_token
from agentos.identity.security import verify_api_key
from agentos.settings import Settings, get_settings
from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass
class AuthContext:
    organization_id: uuid.UUID
    application_id: uuid.UUID
    credential_id: uuid.UUID
    scopes: list[str]
    subject_type: str
    subject_id: uuid.UUID


async def get_session() -> AsyncSession:
    factory = get_session_factory()
    async with factory() as session:
        yield session


def settings_dep() -> Settings:
    return get_settings()


async def require_auth(
    session: Annotated[AsyncSession, Depends(get_session)],
    authorization: Annotated[str | None, Header()] = None,
    x_organization_id: Annotated[str | None, Header(alias="X-Organization-Id")] = None,
) -> AuthContext:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="unauthorized")
    raw_key = authorization.split(" ", 1)[1].strip()
    if not raw_key or not x_organization_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="unauthorized")

    try:
        org_id = uuid.UUID(x_organization_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="unauthorized") from exc

    # Set tenant context before RLS-protected reads; key must still match this org.
    await set_org_context(session, str(org_id))

    if raw_key.count(".") == 2:
        return await _auth_from_jwt(session, raw_key, org_id)

    result = await session.execute(
        select(ApiCredential, Application)
        .join(Application, Application.id == ApiCredential.application_id)
        .where(
            Application.organization_id == org_id,
            Application.status == "active",
            ApiCredential.revoked_at.is_(None),
        )
    )
    rows = result.all()
    matched: tuple[ApiCredential, Application] | None = None
    for cred, app in rows:
        if verify_api_key(raw_key, cred.key_hash):
            matched = (cred, app)
            break
    if matched is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="unauthorized")

    cred, app = matched
    return AuthContext(
        organization_id=org_id,
        application_id=app.id,
        credential_id=cred.id,
        scopes=list(cred.scopes or []),
        subject_type="application",
        subject_id=app.id,
    )


async def _auth_from_jwt(
    session: AsyncSession, raw_token: str, org_id: uuid.UUID
) -> AuthContext:
    settings = get_settings()
    try:
        claims = verify_access_token(raw_token, signing_key=settings.oauth_signing_key)
        token_org = uuid.UUID(str(claims["org"]))
        app_id = uuid.UUID(str(claims["sub"]))
        cred_id = uuid.UUID(str(claims["cred"]))
    except (TokenError, ValueError, KeyError) as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="unauthorized") from exc
    if token_org != org_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="unauthorized")

    cred = await session.get(ApiCredential, cred_id)
    app = await session.get(Application, app_id)
    if (
        cred is None
        or app is None
        or cred.revoked_at is not None
        or app.status != "active"
        or app.organization_id != org_id
        or cred.application_id != app.id
    ):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="unauthorized")
    return AuthContext(
        organization_id=org_id,
        application_id=app.id,
        credential_id=cred.id,
        scopes=list(cred.scopes or []),
        subject_type="application",
        subject_id=app.id,
    )


def require_scope(scope: str):
    async def _inner(auth: Annotated[AuthContext, Depends(require_auth)]) -> AuthContext:
        if scope not in auth.scopes and "*" not in auth.scopes:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
        return auth

    return _inner
