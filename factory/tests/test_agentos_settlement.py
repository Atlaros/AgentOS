"""Adapter confirm builds one AgentOS fiat settlement. It does not move a wallet."""

from decimal import Decimal
from uuid import uuid4

from factory_os.domain.models import Payment, PaymentStatus, PILOT_TENANT_ID
from factory_os.tools.agentos_settlement import settlement_request


def test_settlement_request_uses_provider_ref_and_skips_wallets() -> None:
    payment = Payment(
        id=uuid4(),
        tenant_id=PILOT_TENANT_ID,
        order_id=None,
        provider="baneco",
        provider_ref="qr-77",
        amount=Decimal("15.50"),
        currency="BOB",
        status=PaymentStatus.CONFIRMED,
        qr_payload="QR:qr-77",
    )
    request = settlement_request(
        payment,
        base_url="http://127.0.0.1:8080",
        api_key="lab-key",
        organization_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
    )
    assert request["method"] == "POST"
    assert request["url"] == "http://127.0.0.1:8080/v1/fiat-settlements"
    assert request["headers"]["Idempotency-Key"] == "qr-77"
    assert request["headers"]["Authorization"] == "Bearer lab-key"
    assert request["headers"]["X-Organization-Id"] == "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    assert request["json"] == {
        "provider": "baneco",
        "provider_ref": "qr-77",
        "amount": "15.50",
        "currency": "BOB",
    }
    assert "from_wallet_id" not in request["json"]
    assert "to_address" not in request["json"]
