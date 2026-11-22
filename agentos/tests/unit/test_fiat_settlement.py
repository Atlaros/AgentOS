"""A fiat settlement is an observed café payment, not a wallet transfer."""

from uuid import UUID

from agentos.ledger.fiat import replay_status, settlement_id, settlement_payload


ORG = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")


def test_same_provider_ref_keeps_the_same_ledger_id() -> None:
    first = settlement_id(ORG, "qr-77")
    second = settlement_id(ORG, "qr-77")
    other = settlement_id(ORG, "qr-78")
    assert first == second
    assert first != other


def test_payload_records_the_observed_payment_only() -> None:
    payload = settlement_payload(
        provider="baneco",
        provider_ref="qr-77",
        amount="15.50",
        currency="BOB",
    )
    assert payload == {
        "provider": "baneco",
        "provider_ref": "qr-77",
        "amount": "15.50",
        "currency": "BOB",
        "source": "factory",
    }
    assert "secret" not in payload
    assert "to_address" not in payload


def test_same_payload_replays_and_a_different_amount_conflicts() -> None:
    payload = settlement_payload(
        provider="baneco",
        provider_ref="qr-77",
        amount="15.50",
        currency="BOB",
    )
    changed = dict(payload)
    changed["amount"] = "16.00"
    assert replay_status(None, payload) == "created"
    assert replay_status(payload, payload) == "replay"
    assert replay_status(changed, payload) == "conflict"
