from __future__ import annotations

import json
import uuid
from decimal import Decimal
from typing import Annotated

from agentos.adapters.registry import resolve_adapter
from agentos.adapters.stellar import is_stellar_address
from agentos.db.models import (
    AgentIdentity,
    ApiCredential,
    Application,
    Approval,
    Asset,
    Membership,
    Organization,
    PaymentRequest,
    PolicyRule,
    TransferIntent,
    User,
    Wallet,
)
from agentos.db.session import set_org_context
from agentos.identity.security import ALL_SCOPES, body_hash, generate_api_key
from agentos.ledger.service import append_ledger
from agentos.policy.engine import evaluate_policy
from agentos.settings import Settings
from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from agentos_api.deps import AuthContext, get_session, require_scope, settings_dep
from agentos_api.schemas import (
    AgentResponse,
    ApplicationResponse,
    ApproveRequest,
    BalanceResponse,
    BootstrapRequest,
    BootstrapResponse,
    CreateAgentRequest,
    CreateApplicationRequest,
    CreatePaymentRequest,
    ExecuteTransferRequest,
    LedgerEntryResponse,
    LinkWalletRequest,
    OrgResponse,
    PaymentRequestResponse,
    RejectRequest,
    TransferResponse,
    WalletResponse,
)

router = APIRouter()


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/v1/bootstrap", response_model=BootstrapResponse)
async def bootstrap(
    body: BootstrapRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(settings_dep)],
) -> BootstrapResponse:
    if body.bootstrap_token != settings.bootstrap_token:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")

    existing = await session.scalar(select(Organization).where(Organization.slug == body.org_slug))
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="conflict")

    org = Organization(slug=body.org_slug, name=body.org_name)
    session.add(org)
    await session.flush()
    await set_org_context(session, str(org.id))

    user = await session.scalar(select(User).where(User.email == body.owner_email))
    if user is None:
        user = User(email=body.owner_email)
        session.add(user)
        await session.flush()

    session.add(Membership(organization_id=org.id, user_id=user.id, role="owner"))
    app = Application(organization_id=org.id, name=body.app_name, status="active")
    session.add(app)
    await session.flush()

    raw_key, prefix, key_hash = generate_api_key()
    session.add(
        ApiCredential(
            application_id=app.id,
            key_prefix=prefix,
            key_hash=key_hash,
            scopes=ALL_SCOPES,
        )
    )
    # Default require_human rule for amounts above auto_allow via engine default;
    # seed an explicit high-amount require_human rule for clarity in demos.
    session.add(
        PolicyRule(
            organization_id=org.id,
            name="require_human_above_auto",
            effect="require_human",
            match={"amount_min": str(Decimal(settings.auto_allow_amount_max) + Decimal("0.0000001"))},
            priority=10,
            enabled=True,
        )
    )
    session.add(
        Asset(
            organization_id=org.id,
            code="XLM",
            issuer=None,
            network="fake",
            decimals=7,
        )
    )
    session.add(
        Asset(
            organization_id=org.id,
            code="XLM",
            issuer=None,
            network="testnet",
            decimals=7,
        )
    )
    await append_ledger(
        session,
        organization_id=org.id,
        entry_type="org_bootstrapped",
        ref_type="organization",
        ref_id=org.id,
        payload={"slug": org.slug},
    )
    await session.commit()
    return BootstrapResponse(
        organization_id=org.id,
        application_id=app.id,
        user_id=user.id,
        api_key=raw_key,
        scopes=ALL_SCOPES,
    )


@router.get("/v1/organizations/me", response_model=OrgResponse)
async def org_me(
    auth: Annotated[AuthContext, Depends(require_scope("orgs:read"))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> OrgResponse:
    org = await session.get(Organization, auth.organization_id)
    if org is None:
        raise HTTPException(status_code=404, detail="not_found")
    return OrgResponse(id=org.id, slug=org.slug, name=org.name)


@router.post("/v1/applications", response_model=ApplicationResponse, status_code=201)
async def create_application(
    body: CreateApplicationRequest,
    auth: Annotated[AuthContext, Depends(require_scope("apps:write"))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ApplicationResponse:
    scopes = body.scopes or ALL_SCOPES
    unknown = [s for s in scopes if s not in ALL_SCOPES]
    if unknown:
        raise HTTPException(status_code=422, detail="validation")
    app = Application(organization_id=auth.organization_id, name=body.name, status="active")
    session.add(app)
    await session.flush()
    raw_key, prefix, key_hash = generate_api_key()
    session.add(
        ApiCredential(
            application_id=app.id,
            key_prefix=prefix,
            key_hash=key_hash,
            scopes=scopes,
        )
    )
    await append_ledger(
        session,
        organization_id=auth.organization_id,
        entry_type="application_created",
        ref_type="application",
        ref_id=app.id,
        payload={"name": app.name},
    )
    await session.commit()
    return ApplicationResponse(
        id=app.id,
        name=app.name,
        status=app.status,
        api_key=raw_key,
        scopes=scopes,
    )


@router.post("/v1/agents", response_model=AgentResponse, status_code=201)
async def create_agent(
    body: CreateAgentRequest,
    auth: Annotated[AuthContext, Depends(require_scope("agents:write"))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AgentResponse:
    app = await session.get(Application, body.application_id)
    if app is None or app.organization_id != auth.organization_id:
        raise HTTPException(status_code=404, detail="not_found")
    scopes = body.scopes or [
        "wallets:read",
        "balances:read",
        "payments:create",
        "transfers:execute",
        "audit:read",
    ]
    unknown = [s for s in scopes if s not in ALL_SCOPES]
    if unknown:
        raise HTTPException(status_code=422, detail="validation")
    agent = AgentIdentity(
        organization_id=auth.organization_id,
        application_id=app.id,
        name=body.name,
        scopes=scopes,
        status="active",
    )
    session.add(agent)
    await session.flush()
    await append_ledger(
        session,
        organization_id=auth.organization_id,
        entry_type="agent_created",
        ref_type="agent_identity",
        ref_id=agent.id,
        payload={"name": agent.name, "application_id": str(app.id)},
    )
    await session.commit()
    return AgentResponse(
        id=agent.id,
        name=agent.name,
        application_id=agent.application_id,
        scopes=agent.scopes,
        status=agent.status,
    )


@router.get("/v1/agents", response_model=list[AgentResponse])
async def list_agents(
    auth: Annotated[AuthContext, Depends(require_scope("agents:read"))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[AgentResponse]:
    rows = (
        await session.scalars(
            select(AgentIdentity).where(AgentIdentity.organization_id == auth.organization_id)
        )
    ).all()
    return [
        AgentResponse(
            id=a.id,
            name=a.name,
            application_id=a.application_id,
            scopes=a.scopes,
            status=a.status,
        )
        for a in rows
    ]


@router.get("/v1/agents/{agent_id}", response_model=AgentResponse)
async def get_agent(
    agent_id: uuid.UUID,
    auth: Annotated[AuthContext, Depends(require_scope("agents:read"))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AgentResponse:
    agent = await session.get(AgentIdentity, agent_id)
    if agent is None or agent.organization_id != auth.organization_id:
        raise HTTPException(status_code=404, detail="not_found")
    return AgentResponse(
        id=agent.id,
        name=agent.name,
        application_id=agent.application_id,
        scopes=agent.scopes,
        status=agent.status,
    )


@router.post("/v1/wallets/link", response_model=WalletResponse)
async def link_wallet(
    body: LinkWalletRequest,
    auth: Annotated[AuthContext, Depends(require_scope("wallets:link"))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> WalletResponse:
    allowed = {("fake", "fake"), ("stellar", "testnet")}
    if (body.provider, body.network) not in allowed:
        raise HTTPException(status_code=422, detail="validation")
    if body.network in {"public", "mainnet"}:
        raise HTTPException(status_code=422, detail="validation")
    if body.provider == "stellar" and not is_stellar_address(body.public_address):
        raise HTTPException(status_code=422, detail="validation")
    wallet = Wallet(
        organization_id=auth.organization_id,
        provider=body.provider,
        network=body.network,
        public_address=body.public_address,
        label=body.label,
        link_status="linked",
    )
    session.add(wallet)
    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(status_code=409, detail="conflict") from exc
    await append_ledger(
        session,
        organization_id=auth.organization_id,
        entry_type="wallet_linked",
        ref_type="wallet",
        ref_id=wallet.id,
        payload={"public_address": wallet.public_address, "provider": wallet.provider},
    )
    await session.commit()
    return WalletResponse(
        id=wallet.id,
        provider=wallet.provider,
        network=wallet.network,
        public_address=wallet.public_address,
        label=wallet.label,
        link_status=wallet.link_status,
    )


@router.get("/v1/wallets", response_model=list[WalletResponse])
async def list_wallets(
    auth: Annotated[AuthContext, Depends(require_scope("wallets:read"))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[WalletResponse]:
    rows = (
        await session.scalars(
            select(Wallet).where(
                Wallet.organization_id == auth.organization_id,
                Wallet.link_status == "linked",
            )
        )
    ).all()
    return [
        WalletResponse(
            id=w.id,
            provider=w.provider,
            network=w.network,
            public_address=w.public_address,
            label=w.label,
            link_status=w.link_status,
        )
        for w in rows
    ]


@router.get("/v1/wallets/{wallet_id}/balances", response_model=list[BalanceResponse])
async def wallet_balances(
    wallet_id: uuid.UUID,
    auth: Annotated[AuthContext, Depends(require_scope("balances:read"))],
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(settings_dep)],
) -> list[BalanceResponse]:
    wallet = await session.get(Wallet, wallet_id)
    if wallet is None or wallet.organization_id != auth.organization_id:
        raise HTTPException(status_code=404, detail="not_found")
    try:
        adapter = resolve_adapter(wallet.provider, wallet.network, settings)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="validation") from exc
    balances = await adapter.get_balances(wallet.public_address)
    return [
        BalanceResponse(asset_code=b.asset_code, amount=b.amount, issuer=b.issuer) for b in balances
    ]


@router.post("/v1/payment-requests", response_model=PaymentRequestResponse, status_code=201)
async def create_payment_request(
    body: CreatePaymentRequest,
    auth: Annotated[AuthContext, Depends(require_scope("payments:create"))],
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(settings_dep)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> PaymentRequestResponse:
    if not idempotency_key:
        raise HTTPException(status_code=422, detail="validation")

    canonical = json.dumps(body.model_dump(mode="json"), sort_keys=True)
    digest = body_hash(canonical)

    existing = await session.scalar(
        select(PaymentRequest).where(
            PaymentRequest.organization_id == auth.organization_id,
            PaymentRequest.idempotency_key == idempotency_key,
        )
    )
    if existing is not None:
        if existing.request_body_hash != digest:
            raise HTTPException(status_code=409, detail="conflict")
        return PaymentRequestResponse(
            id=existing.id,
            status=existing.status,
            amount=existing.amount,
            to_address=existing.to_address,
            from_wallet_id=existing.from_wallet_id,
            policy_effect=None,
        )

    wallet = await session.get(Wallet, body.from_wallet_id)
    if wallet is None or wallet.organization_id != auth.organization_id:
        raise HTTPException(status_code=404, detail="not_found")

    asset = await session.scalar(
        select(Asset).where(
            Asset.organization_id == auth.organization_id,
            Asset.code == body.asset_code,
            Asset.network == wallet.network,
        )
    )
    if asset is None:
        raise HTTPException(status_code=422, detail="validation")
    if wallet.provider == "stellar" and not is_stellar_address(body.to_address):
        raise HTTPException(status_code=422, detail="validation")

    rules = (
        await session.scalars(
            select(PolicyRule).where(
                PolicyRule.organization_id == auth.organization_id,
                PolicyRule.enabled.is_(True),
            )
        )
    ).all()
    decision = evaluate_policy(
        amount=body.amount,
        rules=[
            {
                "name": r.name,
                "effect": r.effect,
                "match": r.match,
                "priority": r.priority,
                "enabled": r.enabled,
            }
            for r in rules
        ],
        auto_allow_max=Decimal(settings.auto_allow_amount_max),
    )
    if decision.effect == "deny":
        raise HTTPException(status_code=403, detail="forbidden")

    status_value = "approved" if decision.effect == "allow" else "pending_approval"
    pr = PaymentRequest(
        organization_id=auth.organization_id,
        created_by_subject_type=auth.subject_type,
        created_by_subject_id=auth.subject_id,
        from_wallet_id=wallet.id,
        to_address=body.to_address,
        asset_id=asset.id,
        amount=body.amount,
        memo=body.memo,
        status=status_value,
        idempotency_key=idempotency_key,
        request_body_hash=digest,
    )
    session.add(pr)
    await session.flush()
    await append_ledger(
        session,
        organization_id=auth.organization_id,
        entry_type="payment_requested",
        ref_type="payment_request",
        ref_id=pr.id,
        payload={"amount": str(body.amount), "status": status_value},
    )
    await append_ledger(
        session,
        organization_id=auth.organization_id,
        entry_type="policy_decision",
        ref_type="payment_request",
        ref_id=pr.id,
        payload={"effect": decision.effect, "rule": decision.rule_name, "reason": decision.reason},
    )
    await session.commit()
    return PaymentRequestResponse(
        id=pr.id,
        status=pr.status,
        amount=pr.amount,
        to_address=pr.to_address,
        from_wallet_id=pr.from_wallet_id,
        policy_effect=decision.effect,
    )


@router.get("/v1/payment-requests/{payment_id}", response_model=PaymentRequestResponse)
async def get_payment_request(
    payment_id: uuid.UUID,
    auth: Annotated[AuthContext, Depends(require_scope("payments:create"))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> PaymentRequestResponse:
    pr = await session.get(PaymentRequest, payment_id)
    if pr is None or pr.organization_id != auth.organization_id:
        raise HTTPException(status_code=404, detail="not_found")
    return PaymentRequestResponse(
        id=pr.id,
        status=pr.status,
        amount=pr.amount,
        to_address=pr.to_address,
        from_wallet_id=pr.from_wallet_id,
    )


@router.post("/v1/payment-requests/{payment_id}/approve", response_model=PaymentRequestResponse)
async def approve_payment(
    payment_id: uuid.UUID,
    body: ApproveRequest,
    auth: Annotated[AuthContext, Depends(require_scope("approvals:decide"))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> PaymentRequestResponse:
    pr = await session.get(PaymentRequest, payment_id)
    if pr is None or pr.organization_id != auth.organization_id:
        raise HTTPException(status_code=404, detail="not_found")
    if pr.status != "pending_approval":
        raise HTTPException(status_code=409, detail="conflict")

    # Lab shortcut: use first membership owner as approver subject for application keys.
    membership = await session.scalar(
        select(Membership).where(
            Membership.organization_id == auth.organization_id,
            Membership.role == "owner",
        )
    )
    if membership is None:
        raise HTTPException(status_code=422, detail="validation")

    session.add(
        Approval(
            organization_id=auth.organization_id,
            payment_request_id=pr.id,
            decided_by_user_id=membership.user_id,
            decision="approved",
            reason=body.reason,
        )
    )
    pr.status = "approved"
    await append_ledger(
        session,
        organization_id=auth.organization_id,
        entry_type="payment_approved",
        ref_type="payment_request",
        ref_id=pr.id,
        payload={"reason": body.reason},
    )
    await session.commit()
    return PaymentRequestResponse(
        id=pr.id,
        status=pr.status,
        amount=pr.amount,
        to_address=pr.to_address,
        from_wallet_id=pr.from_wallet_id,
        policy_effect="allow",
    )


@router.post("/v1/payment-requests/{payment_id}/reject", response_model=PaymentRequestResponse)
async def reject_payment(
    payment_id: uuid.UUID,
    body: RejectRequest,
    auth: Annotated[AuthContext, Depends(require_scope("approvals:decide"))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> PaymentRequestResponse:
    pr = await session.get(PaymentRequest, payment_id)
    if pr is None or pr.organization_id != auth.organization_id:
        raise HTTPException(status_code=404, detail="not_found")
    if pr.status != "pending_approval":
        raise HTTPException(status_code=409, detail="conflict")

    membership = await session.scalar(
        select(Membership).where(
            Membership.organization_id == auth.organization_id,
            Membership.role == "owner",
        )
    )
    if membership is None:
        raise HTTPException(status_code=422, detail="validation")

    session.add(
        Approval(
            organization_id=auth.organization_id,
            payment_request_id=pr.id,
            decided_by_user_id=membership.user_id,
            decision="rejected",
            reason=body.reason,
        )
    )
    pr.status = "rejected"
    await append_ledger(
        session,
        organization_id=auth.organization_id,
        entry_type="payment_rejected",
        ref_type="payment_request",
        ref_id=pr.id,
        payload={"reason": body.reason},
    )
    await session.commit()
    return PaymentRequestResponse(
        id=pr.id,
        status=pr.status,
        amount=pr.amount,
        to_address=pr.to_address,
        from_wallet_id=pr.from_wallet_id,
        policy_effect="deny",
    )


@router.post("/v1/transfers", response_model=TransferResponse)
async def execute_transfer(
    body: ExecuteTransferRequest,
    auth: Annotated[AuthContext, Depends(require_scope("transfers:execute"))],
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(settings_dep)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> TransferResponse:
    if not idempotency_key:
        raise HTTPException(status_code=422, detail="validation")

    existing = await session.scalar(
        select(TransferIntent).where(
            TransferIntent.organization_id == auth.organization_id,
            TransferIntent.idempotency_key == idempotency_key,
        )
    )
    if existing is not None:
        return TransferResponse(
            id=existing.id,
            status=existing.status,
            network_tx_id=existing.network_tx_id,
            amount=existing.amount,
            to_address=existing.to_address,
        )

    pr = await session.get(PaymentRequest, body.payment_request_id)
    if pr is None or pr.organization_id != auth.organization_id:
        raise HTTPException(status_code=404, detail="not_found")
    if pr.status != "approved":
        raise HTTPException(status_code=403, detail="forbidden")
    if pr.from_wallet_id is None:
        raise HTTPException(status_code=422, detail="validation")

    wallet = await session.get(Wallet, pr.from_wallet_id)
    asset = await session.get(Asset, pr.asset_id)
    if wallet is None or asset is None:
        raise HTTPException(status_code=404, detail="not_found")

    try:
        adapter = resolve_adapter(wallet.provider, wallet.network, settings)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="validation") from exc

    intent = TransferIntent(
        organization_id=auth.organization_id,
        payment_request_id=pr.id,
        from_wallet_id=wallet.id,
        to_address=pr.to_address,
        asset_id=asset.id,
        amount=pr.amount,
        status="queued",
        idempotency_key=idempotency_key,
    )
    session.add(intent)
    await session.flush()

    result = await adapter.submit_payment(
        from_address=wallet.public_address,
        to_address=pr.to_address,
        asset_code=asset.code,
        amount=pr.amount,
        memo=pr.memo,
        idempotency_key=idempotency_key,
    )
    intent.network_tx_id = result.network_tx_id or None
    intent.status = result.status
    await append_ledger(
        session,
        organization_id=auth.organization_id,
        entry_type="transfer_submitted"
        if result.status in {"submitted", "confirmed"}
        else "transfer_failed",
        ref_type="transfer_intent",
        ref_id=intent.id,
        payload={"status": result.status, "network_tx_id": result.network_tx_id},
    )
    if result.status == "confirmed":
        await append_ledger(
            session,
            organization_id=auth.organization_id,
            entry_type="transfer_confirmed",
            ref_type="transfer_intent",
            ref_id=intent.id,
            payload={"network_tx_id": result.network_tx_id},
        )
    await session.commit()
    return TransferResponse(
        id=intent.id,
        status=intent.status,
        network_tx_id=intent.network_tx_id,
        amount=intent.amount,
        to_address=intent.to_address,
    )


@router.get("/v1/transfers/{transfer_id}", response_model=TransferResponse)
async def get_transfer(
    transfer_id: uuid.UUID,
    auth: Annotated[AuthContext, Depends(require_scope("transfers:execute"))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> TransferResponse:
    intent = await session.get(TransferIntent, transfer_id)
    if intent is None or intent.organization_id != auth.organization_id:
        raise HTTPException(status_code=404, detail="not_found")
    return TransferResponse(
        id=intent.id,
        status=intent.status,
        network_tx_id=intent.network_tx_id,
        amount=intent.amount,
        to_address=intent.to_address,
    )


@router.get("/v1/ledger", response_model=list[LedgerEntryResponse])
async def list_ledger(
    auth: Annotated[AuthContext, Depends(require_scope("audit:read"))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[LedgerEntryResponse]:
    from agentos.db.models import LedgerEntry

    rows = (
        await session.scalars(
            select(LedgerEntry)
            .where(LedgerEntry.organization_id == auth.organization_id)
            .order_by(LedgerEntry.created_at.asc())
        )
    ).all()
    return [
        LedgerEntryResponse(
            id=e.id,
            entry_type=e.entry_type,
            ref_type=e.ref_type,
            ref_id=e.ref_id,
            payload=e.payload,
        )
        for e in rows
    ]


@router.get("/v1/policies")
async def list_policies(
    auth: Annotated[AuthContext, Depends(require_scope("policies:read"))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[dict]:
    rows = (
        await session.scalars(
            select(PolicyRule).where(PolicyRule.organization_id == auth.organization_id)
        )
    ).all()
    return [
        {
            "id": str(r.id),
            "name": r.name,
            "effect": r.effect,
            "match": r.match,
            "priority": r.priority,
            "enabled": r.enabled,
        }
        for r in rows
    ]
