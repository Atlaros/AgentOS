from __future__ import annotations

import uuid
from typing import Annotated

from agentos.db.models import ApiCredential, Application
from agentos.db.session import set_org_context
from agentos.identity.oauth import TokenError, issue_access_token
from agentos.identity.security import verify_api_key
from agentos.settings import Settings
from fastapi import APIRouter, Depends, Form, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentos_api.deps import get_session, settings_dep

router = APIRouter()


@router.post("/oauth/token")
async def oauth_token(
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(settings_dep)],
    grant_type: Annotated[str, Form()],
    client_id: Annotated[str, Form()],
    client_secret: Annotated[str, Form()],
    organization_id: Annotated[str, Form()],
) -> dict[str, str | int]:
    if grant_type != "client_credentials":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="unauthorized")
    try:
        org_id = uuid.UUID(organization_id)
        app_id = uuid.UUID(client_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="unauthorized") from exc

    await set_org_context(session, str(org_id))
    result = await session.execute(
        select(ApiCredential, Application)
        .join(Application, Application.id == ApiCredential.application_id)
        .where(
            Application.id == app_id,
            Application.organization_id == org_id,
            Application.status == "active",
            ApiCredential.revoked_at.is_(None),
        )
    )
    matched: tuple[ApiCredential, Application] | None = None
    for cred, app in result.all():
        if verify_api_key(client_secret, cred.key_hash):
            matched = (cred, app)
            break
    if matched is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="unauthorized")

    cred, app = matched
    try:
        token = issue_access_token(
            organization_id=str(org_id),
            application_id=str(app.id),
            credential_id=str(cred.id),
            scopes=list(cred.scopes or []),
            signing_key=settings.oauth_signing_key,
            ttl_seconds=settings.oauth_token_ttl_seconds,
        )
    except TokenError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="unauthorized") from exc
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": settings.oauth_token_ttl_seconds,
    }
