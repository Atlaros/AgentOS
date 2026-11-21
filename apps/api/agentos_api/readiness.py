"""Read-only post-MVP surfaces: console shell, lab plan, connection report."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated, Any

from agentos.readiness import connection_report, current_plan
from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse

from agentos_api.deps import require_scope

router = APIRouter()
_CONSOLE = Path(__file__).with_name("console.html")


@router.get("/console", response_class=HTMLResponse)
async def console() -> HTMLResponse:
    return HTMLResponse(_CONSOLE.read_text(encoding="utf-8"))


@router.get("/v1/billing/plan")
async def billing_plan(
    _: Annotated[object, Depends(require_scope("orgs:read"))],
) -> dict[str, Any]:
    return current_plan()


@router.get("/v1/connections")
async def connections(
    _: Annotated[object, Depends(require_scope("orgs:read"))],
) -> list[dict[str, str]]:
    return connection_report(evm_rpc_url=os.environ.get("AGENTOS_EVM_RPC_URL", ""))
