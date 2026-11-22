"""Pollar ramp reads and quotes. Trustless Work is not exposed over HTTP."""

from __future__ import annotations

from typing import Annotated, Literal

from agentos.rails import get_rail_credentials
from agentos.ramps.pollar import PollarClient, PollarNotConfigured, PollarRampError
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from agentos_api.deps import AuthContext, require_scope

router = APIRouter()


class RampQuoteRequest(BaseModel):
    direction: Literal["ONRAMP", "OFFRAMP"]
    fiat_currency: str = Field(min_length=1, max_length=16)
    fiat_rail: str = Field(min_length=1, max_length=32)
    fiat_country: str = Field(min_length=2, max_length=8)
    asset_code: str = Field(min_length=1, max_length=16)
    asset_identifier: str = Field(min_length=1, max_length=128)
    asset_chain: Literal["STELLAR", "POLYGON", "SOLANA"]
    amount_value: str = Field(min_length=1, max_length=64)
    amount_denomination: Literal["in", "out"] = "in"
    customer_id: str | None = Field(default=None, min_length=1, max_length=128)
    stellar_address: str | None = Field(default=None, min_length=56, max_length=56)


class LinkRampWalletRequest(BaseModel):
    address: str = Field(min_length=56, max_length=56)
    customer_id: str | None = Field(default=None, min_length=1, max_length=128)
    chain: Literal["STELLAR", "POLYGON", "SOLANA"] = "STELLAR"


def _client() -> PollarClient:
    cfg = get_rail_credentials()
    return PollarClient(api_key=cfg.pollar_api_key, base_url=cfg.pollar_api_base)


def _customer_id(auth: AuthContext, customer_id: str | None) -> str:
    return customer_id or str(auth.organization_id)


@router.get("/v1/ramps/routes")
async def ramp_routes(
    auth: Annotated[AuthContext, Depends(require_scope("orgs:read"))],
    direction: str = "ONRAMP",
) -> dict[str, object]:
    if direction not in {"ONRAMP", "OFFRAMP"}:
        raise HTTPException(status_code=422, detail="validation")
    client = _client()
    try:
        return await client.list_routes(
            direction=direction,
            external_user_id=str(auth.organization_id),
        )
    except PollarNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except PollarRampError as exc:
        raise HTTPException(status_code=422, detail=exc.body) from exc


@router.post("/v1/ramps/quotes")
async def ramp_quotes(
    body: RampQuoteRequest,
    auth: Annotated[AuthContext, Depends(require_scope("payments:create"))],
) -> dict[str, object]:
    client = _client()
    customer = _customer_id(auth, body.customer_id)
    try:
        if body.stellar_address:
            await client.link_external_wallet(
                external_user_id=customer,
                chain="STELLAR",
                address=body.stellar_address,
            )
        return await client.quote_ramp(
            external_user_id=customer,
            direction=body.direction,
            fiat_currency=body.fiat_currency,
            fiat_rail=body.fiat_rail,
            fiat_country=body.fiat_country,
            asset_code=body.asset_code,
            asset_identifier=body.asset_identifier,
            asset_chain=body.asset_chain,
            amount_value=body.amount_value,
            amount_denomination=body.amount_denomination,
        )
    except PollarNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except PollarRampError as exc:
        raise HTTPException(status_code=422, detail=exc.body) from exc


@router.put("/v1/ramps/wallets")
async def link_ramp_wallet(
    body: LinkRampWalletRequest,
    auth: Annotated[AuthContext, Depends(require_scope("payments:create"))],
) -> dict[str, object]:
    client = _client()
    try:
        return await client.link_external_wallet(
            external_user_id=_customer_id(auth, body.customer_id),
            chain=body.chain,
            address=body.address,
        )
    except PollarNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except PollarRampError as exc:
        raise HTTPException(status_code=422, detail=exc.body) from exc
