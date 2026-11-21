from __future__ import annotations

import uuid
from decimal import Decimal

from pydantic import BaseModel, Field


class BootstrapRequest(BaseModel):
    org_slug: str = Field(min_length=2, max_length=64)
    org_name: str = Field(min_length=2, max_length=128)
    app_name: str = Field(default="demo-app", min_length=2, max_length=128)
    owner_email: str = Field(default="owner@example.com")
    bootstrap_token: str


class BootstrapResponse(BaseModel):
    organization_id: uuid.UUID
    application_id: uuid.UUID
    user_id: uuid.UUID
    api_key: str
    scopes: list[str]


class OrgResponse(BaseModel):
    id: uuid.UUID
    slug: str
    name: str


class LinkWalletRequest(BaseModel):
    provider: str = "fake"
    network: str = "fake"
    public_address: str = Field(min_length=3, max_length=128)
    label: str = ""


class WalletResponse(BaseModel):
    id: uuid.UUID
    provider: str
    network: str
    public_address: str
    label: str
    link_status: str


class BalanceResponse(BaseModel):
    asset_code: str
    amount: Decimal
    issuer: str | None = None


class CreatePaymentRequest(BaseModel):
    from_wallet_id: uuid.UUID
    to_address: str
    amount: Decimal = Field(gt=0)
    asset_code: str = "XLM"
    memo: str | None = None


class PaymentRequestResponse(BaseModel):
    id: uuid.UUID
    status: str
    amount: Decimal
    to_address: str
    from_wallet_id: uuid.UUID | None
    policy_effect: str | None = None


class ApproveRequest(BaseModel):
    reason: str | None = None


class RejectRequest(BaseModel):
    reason: str | None = None


class CreateApplicationRequest(BaseModel):
    name: str = Field(min_length=2, max_length=128)
    scopes: list[str] | None = None


class ApplicationResponse(BaseModel):
    id: uuid.UUID
    name: str
    status: str
    api_key: str | None = None
    scopes: list[str]


class CreateAgentRequest(BaseModel):
    name: str = Field(min_length=2, max_length=128)
    application_id: uuid.UUID
    scopes: list[str] | None = None


class AgentResponse(BaseModel):
    id: uuid.UUID
    name: str
    application_id: uuid.UUID
    scopes: list[str]
    status: str


class ExecuteTransferRequest(BaseModel):
    payment_request_id: uuid.UUID


class TransferResponse(BaseModel):
    id: uuid.UUID
    status: str
    network_tx_id: str | None
    amount: Decimal
    to_address: str


class LedgerEntryResponse(BaseModel):
    id: uuid.UUID
    entry_type: str
    ref_type: str
    ref_id: uuid.UUID
    payload: dict
