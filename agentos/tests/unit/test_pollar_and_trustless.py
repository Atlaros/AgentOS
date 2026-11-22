import json
import uuid
from decimal import Decimal

import httpx
import pytest
from agentos.adapters.registry import resolve_adapter
from agentos.escrow.trustless_work import TrustlessWorkClient, TrustlessWorkNotConfigured
from agentos.ramps.pollar import PollarClient, PollarNotConfigured, PollarRampError
from agentos.settings import Settings
from agentos_api.deps import AuthContext, require_auth
from agentos_api.main import create_app
from fastapi.testclient import TestClient


@pytest.mark.asyncio
async def test_pollar_refuses_without_a_secret_key() -> None:
    client = PollarClient(api_key="", base_url="https://server.api.pollar.xyz/v3")
    with pytest.raises(PollarNotConfigured, match="pollar_not_configured"):
        await client.list_routes(direction="ONRAMP", external_user_id="org-1")
    publishable = PollarClient(api_key="pub_testnet_example", base_url="https://server.api.pollar.xyz/v3")
    with pytest.raises(PollarNotConfigured, match="pollar_secret_key_required"):
        await publishable.list_routes(direction="ONRAMP", external_user_id="org-1")


@pytest.mark.asyncio
async def test_pollar_lists_routes_with_the_server_secret() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["key"] = request.headers["x-pollar-api-key"]
        seen["user"] = request.headers["x-pollar-external-user-id"]
        return httpx.Response(200, json={"routes": [{"asset": {"code": "USDC", "chain": "STELLAR"}}]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = PollarClient(
            api_key="sec_testnet_example",
            base_url="https://server.api.pollar.xyz/v3",
            http=http,
        )
        body = await client.list_routes(direction="ONRAMP", external_user_id="org-1")
    assert body["routes"][0]["asset"]["code"] == "USDC"
    assert seen["url"].endswith("/ramps/routes?direction=ONRAMP")
    assert seen["key"] == "sec_testnet_example"
    assert seen["user"] == "org-1"


@pytest.mark.asyncio
async def test_pollar_quotes_an_onramp() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["method"] = request.method
        seen["key"] = request.headers["x-pollar-api-key"]
        seen["user"] = request.headers["x-pollar-external-user-id"]
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "code": "SDK_RAMPS_QUOTES",
                "success": True,
                "content": {"quotes": [{"quoteId": "q1", "amountIn": "2000", "amountOut": "1835"}]},
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = PollarClient(
            api_key="sec_testnet_example",
            base_url="https://server.api.pollar.xyz/v3",
            http=http,
        )
        body = await client.quote_ramp(
            external_user_id="user-1",
            direction="ONRAMP",
            fiat_currency="ARS",
            fiat_rail="HOSTED",
            fiat_country="AR",
            asset_code="ARS",
            asset_identifier="GCLAJ3NUQJPUIXMOP6EEQOOK556X6JUBSQEDGIYN2QD4MBEF3EVKCMDR",
            asset_chain="STELLAR",
            amount_value="2000",
            amount_denomination="in",
        )
    assert body["content"]["quotes"][0]["quoteId"] == "q1"
    assert seen["method"] == "POST"
    assert str(seen["url"]).endswith("/ramps/quotes")
    assert seen["user"] == "user-1"
    assert seen["body"] == {
        "direction": "ONRAMP",
        "fiat": {"currency": "ARS", "rail": "HOSTED", "country": "AR"},
        "asset": {
            "code": "ARS",
            "identifier": "GCLAJ3NUQJPUIXMOP6EEQOOK556X6JUBSQEDGIYN2QD4MBEF3EVKCMDR",
            "chain": "STELLAR",
        },
        "amount": {"value": "2000", "denomination": "in"},
    }


@pytest.mark.asyncio
async def test_pollar_quote_surfaces_wallet_missing() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            422,
            json={
                "code": "SDK_RAMPS_NO_ROUTE",
                "success": False,
                "rejected": [
                    {
                        "failure": {
                            "code": "WALLET_MISSING",
                            "resolutionAction": "link_wallet",
                            "detail": "STELLAR",
                        }
                    }
                ],
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = PollarClient(
            api_key="sec_testnet_example",
            base_url="https://server.api.pollar.xyz/v3",
            http=http,
        )
        with pytest.raises(PollarRampError, match="SDK_RAMPS_NO_ROUTE") as raised:
            await client.quote_ramp(
                external_user_id="user-1",
                direction="ONRAMP",
                fiat_currency="ARS",
                fiat_rail="HOSTED",
                fiat_country="AR",
                asset_code="ARS",
                asset_identifier="GCLAJ3",
                asset_chain="STELLAR",
                amount_value="2000",
                amount_denomination="in",
            )
    assert raised.value.body["rejected"][0]["failure"]["code"] == "WALLET_MISSING"


@pytest.mark.asyncio
async def test_pollar_links_an_external_stellar_wallet() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["method"] = request.method
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "code": "SDK_RAMPS_CUSTOMER_WALLET_LINKED",
                "success": True,
                "content": {"chain": "STELLAR", "address": "GDNGAFUJ", "mode": "EXTERNAL"},
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = PollarClient(
            api_key="sec_testnet_example",
            base_url="https://server.api.pollar.xyz/v3",
            http=http,
        )
        body = await client.link_external_wallet(
            external_user_id="user-1",
            chain="STELLAR",
            address="GDNGAFUJ4S7JELRSJXQ3MFOIPPXC636S7D2S7JSCN5NUSA66MFKNQ7U6",
        )
    assert body["content"]["mode"] == "EXTERNAL"
    assert seen["method"] == "PUT"
    assert str(seen["url"]).endswith("/ramps/customers/wallets/STELLAR")
    assert seen["body"] == {"address": "GDNGAFUJ4S7JELRSJXQ3MFOIPPXC636S7D2S7JSCN5NUSA66MFKNQ7U6"}


@pytest.mark.asyncio
async def test_trustless_work_returns_unsigned_xdr_and_does_not_sign() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["key"] = request.headers["x-api-key"]
        captured["body"] = json.loads(request.content)
        return httpx.Response(201, json={"status": "SUCCESS", "unsignedTransaction": "AAAA"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = TrustlessWorkClient(
            api_key="tw_test_example",
            base_url="https://dev.api.trustlesswork.com",
            http=http,
        )
        xdr = await client.fund_escrow_unsigned(
            contract_id="CABC",
            signer="GABC",
            amount=Decimal("10.50"),
        )
    assert xdr == "AAAA"
    assert captured["url"] == "https://dev.api.trustlesswork.com/escrow/multi-release/fund-escrow"
    assert captured["key"] == "tw_test_example"
    assert captured["body"] == {"contractId": "CABC", "signer": "GABC", "amount": "10.50"}
    assert "signedXdr" not in captured["body"]


@pytest.mark.asyncio
async def test_trustless_work_refuses_without_a_key() -> None:
    client = TrustlessWorkClient(api_key="", base_url="https://dev.api.trustlesswork.com")
    with pytest.raises(TrustlessWorkNotConfigured, match="trustless_work_not_connected"):
        await client.fund_escrow_unsigned(contract_id="CABC", signer="GABC", amount=Decimal(1))


def test_shared_settings_and_routes_stay_put(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENTOS_POLLAR_API_KEY", "")
    monkeypatch.setenv("AGENTOS_TRUSTLESS_WORK_API_KEY", "")
    fields = Settings.model_fields
    assert fields["stellar_horizon_url"].default == "https://horizon-testnet.stellar.org"
    assert fields["stellar_network_passphrase"].default == "Test SDF Network ; September 2015"
    assert fields["stellar_secret_key"].default == ""
    assert "pollar_api_key" not in fields
    assert "trustless_work_api_key" not in fields
    with pytest.raises(ValueError, match="mainnet_denied"):
        resolve_adapter("stellar", "public")

    app = create_app()
    paths: set[str] = set()
    for route in app.routes:
        path = getattr(route, "path", None)
        if isinstance(path, str) and path:
            paths.add(path)
        original = getattr(route, "original_router", None)
        if original is not None:
            for sub in original.routes:
                sub_path = getattr(sub, "path", None)
                if isinstance(sub_path, str) and sub_path:
                    paths.add(sub_path)
    assert "/health" in paths
    assert "/oauth/token" in paths
    assert "/v1/wallets" in paths
    assert "/v1/transfers" in paths
    assert "/v1/wallets/link" in paths
    rail_paths = {path for path in paths if path.startswith("/v1/ramps")}
    assert rail_paths == {"/v1/ramps/routes", "/v1/ramps/quotes", "/v1/ramps/wallets"}

    client = TestClient(app)
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/v1/wallets").status_code == 401
    assert client.post("/v1/transfers", json={}).status_code == 401
    assert client.post("/oauth/token").status_code == 422

    async def fake_auth() -> AuthContext:
        org = uuid.UUID("11111111-1111-1111-1111-111111111111")
        return AuthContext(
            organization_id=org,
            application_id=uuid.UUID("22222222-2222-2222-2222-222222222222"),
            credential_id=uuid.UUID("33333333-3333-3333-3333-333333333333"),
            scopes=["orgs:read", "payments:create"],
            subject_type="application",
            subject_id=org,
        )

    app.dependency_overrides[require_auth] = fake_auth
    client = TestClient(app)
    routes = client.get("/v1/ramps/routes")
    assert routes.status_code == 503
    assert routes.json()["detail"] == "pollar_not_configured"
    quote = client.post(
        "/v1/ramps/quotes",
        json={
            "direction": "ONRAMP",
            "fiat_currency": "ARS",
            "fiat_rail": "HOSTED",
            "fiat_country": "AR",
            "asset_code": "ARS",
            "asset_identifier": "GCLAJ3",
            "asset_chain": "STELLAR",
            "amount_value": "2000",
        },
    )
    assert quote.status_code == 503
    assert quote.json()["detail"] == "pollar_not_configured"
    wallet_link = client.put(
        "/v1/ramps/wallets",
        json={"address": "GDNGAFUJ4S7JELRSJXQ3MFOIPPXC636S7D2S7JSCN5NUSA66MFKNQ7U6"},
    )
    assert wallet_link.status_code == 503
    assert wallet_link.json()["detail"] == "pollar_not_configured"
    fund = client.post(
        "/v1/escrows/fund",
        json={"contract_id": "CABC", "signer": "GABC", "amount": "1"},
    )
    assert fund.status_code == 404
