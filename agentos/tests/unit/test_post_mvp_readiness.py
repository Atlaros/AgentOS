import json
import uuid
from decimal import Decimal

import httpx
import pytest
from agentos.adapters.evm import CustodyRefused, EvmNotConnected, EvmRpcAdapter
from agentos.db.models import Wallet
from agentos.readiness import connection_report, current_plan, refuse_secret
from agentos_api.deps import AuthContext, require_auth
from agentos_api.main import create_app
from fastapi.testclient import TestClient

_ORG = uuid.UUID("11111111-1111-1111-1111-111111111111")
_APP = uuid.UUID("22222222-2222-2222-2222-222222222222")
_CRED = uuid.UUID("33333333-3333-3333-3333-333333333333")


def test_lab_plan_does_not_charge() -> None:
    plan = current_plan()
    assert plan["code"] == "lab"
    assert plan["payment_provider"] is None
    assert plan["charges"] is False


def test_connections_fail_closed_without_live_credentials() -> None:
    report = {item["name"]: item for item in connection_report(evm_rpc_url="")}
    assert report["billing"]["status"] == "ready"
    assert report["evm"]["status"] == "not_connected"
    assert report["evm"]["detail"] == "evm_not_connected"
    assert report["baneco"]["status"] == "unverified"
    assert report["baneco"]["detail"] == "baneco_api_unverified"
    assert report["mainnet"]["status"] == "denied"
    assert report["mainnet"]["detail"] == "mainnet_denied"
    assert report["custody"]["status"] == "refused"
    assert report["console"]["status"] == "ready"
    assert report["stellar"]["status"] == "ready"
    assert report["stellar"]["detail"] == "testnet_xlm"
    assert report["pollar"]["status"] == "not_configured"
    assert report["pollar"]["detail"] == "pollar_not_configured"
    assert report["trustless_work"]["status"] == "not_connected"
    keyed = connection_report(pollar_api_key="pub_testnet_example")
    pollar = next(item for item in keyed if item["name"] == "pollar")
    assert pollar["status"] == "not_configured"
    assert pollar["detail"] == "pollar_secret_key_required"
    assert "pub_testnet_example" not in pollar["detail"]
    ready = connection_report(
        pollar_api_key="sec_testnet_example",
        trustless_api_key="tw_test_example",
    )
    by_name = {item["name"]: item for item in ready}
    assert by_name["pollar"]["status"] == "configured"
    assert by_name["pollar"]["detail"] == "pollar_ready"
    assert "sec_testnet_example" not in by_name["pollar"]["detail"]
    assert by_name["trustless_work"]["status"] == "configured"
    assert "tw_test_example" not in by_name["trustless_work"]["detail"]


def test_configured_evm_rpc_is_reported_without_calling_it() -> None:
    report = {item["name"]: item for item in connection_report(evm_rpc_url="http://rpc.test")}
    assert report["evm"]["status"] == "configured"
    assert report["mainnet"]["detail"] == "mainnet_denied"


def test_secret_material_is_refused() -> None:
    with pytest.raises(CustodyRefused, match="custody_refused"):
        refuse_secret({"secret_key": "SABC"})
    with pytest.raises(CustodyRefused, match="custody_refused"):
        refuse_secret({"mnemonic": "word " * 12})
    refuse_secret({"public_address": "GFAKE"})


def test_wallet_table_has_no_secret_column() -> None:
    names = set(Wallet.__table__.columns.keys())
    assert "public_address" in names
    assert not any("secret" in name or "private" in name or name in {"seed", "mnemonic"} for name in names)


@pytest.mark.asyncio
async def test_evm_balance_requires_rpc() -> None:
    adapter = EvmRpcAdapter(rpc_url="")
    with pytest.raises(EvmNotConnected, match="evm_not_connected"):
        await adapter.get_balances("0x" + "ab" * 20)


@pytest.mark.asyncio
async def test_evm_reads_balance_through_injected_client() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["method"] == "eth_getBalance"
        assert body["params"][0] == "0x" + "ab" * 20
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": body["id"], "result": "0x10"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = EvmRpcAdapter(rpc_url="http://rpc.test", client=client)
    balances = await adapter.get_balances("0x" + "ab" * 20)
    assert balances[0].asset_code == "ETH"
    assert balances[0].amount == Decimal(16) / Decimal(10**18)


@pytest.mark.asyncio
async def test_evm_submit_does_not_send() -> None:
    adapter = EvmRpcAdapter(rpc_url="http://rpc.test")
    with pytest.raises(CustodyRefused, match="custody_refused"):
        await adapter.submit_payment(
            from_address="0x" + "ab" * 20,
            to_address="0x" + "cd" * 20,
            asset_code="ETH",
            amount=Decimal(1),
            memo=None,
            idempotency_key="idem-1",
        )


def test_health_route_stays_ok() -> None:
    client = TestClient(create_app())
    assert client.get("/health").json() == {"status": "ok"}


def test_billing_and_connections_require_auth() -> None:
    client = TestClient(create_app())
    assert client.get("/v1/billing/plan").status_code == 401
    assert client.get("/v1/connections").status_code == 401


def test_billing_and_connections_for_an_org_reader() -> None:
    app = create_app()

    async def fake_auth() -> AuthContext:
        return AuthContext(
            organization_id=_ORG,
            application_id=_APP,
            credential_id=_CRED,
            scopes=["orgs:read"],
            subject_type="application",
            subject_id=_APP,
        )

    app.dependency_overrides[require_auth] = fake_auth
    client = TestClient(app)
    plan = client.get("/v1/billing/plan")
    assert plan.status_code == 200
    assert plan.json()["code"] == "lab"
    assert plan.json()["payment_provider"] is None
    report = client.get("/v1/connections")
    assert report.status_code == 200
    names = {item["name"] for item in report.json()}
    assert names == {
        "billing",
        "evm",
        "baneco",
        "mainnet",
        "custody",
        "console",
        "stellar",
        "pollar",
        "trustless_work",
    }


def test_console_shell_embeds_no_lab_secret() -> None:
    client = TestClient(create_app())
    response = client.get("/console")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    body = response.text
    assert "AgentOS" in body
    for needle in ("change-me-lab-only", "stellar_secret_key", "aos_", "lab-only-change-me"):
        assert needle not in body
