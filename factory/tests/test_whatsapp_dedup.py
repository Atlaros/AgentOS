from factory_os.api.main import create_app
from factory_os.harness.model_gateway import draft_leaks_prompt, grounded_draft
from factory_os.tools.channel import FakeChannel, parse_inbound
from factory_os.tools.inbound_dedup import MemoryInboundDeduper
from tests.conftest import api_settings, make_shop, post_meta
from fastapi.testclient import TestClient


def _meta_payload(wa: str, text: str, wamid: str) -> dict:
    return {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "messages": [
                                {
                                    "from": wa,
                                    "id": wamid,
                                    "type": "text",
                                    "text": {"body": text},
                                }
                            ]
                        }
                    }
                ]
            }
        ]
    }


def test_parse_inbound_includes_wamid() -> None:
    msgs = parse_inbound(_meta_payload("5917001", "hola", "wamid.ABC"))
    assert len(msgs) == 1
    assert msgs[0].wa_number == "5917001"
    assert msgs[0].text == "hola"
    assert msgs[0].message_id == "wamid.ABC"


def test_same_wamid_is_new_for_another_tenant() -> None:
    deduper = MemoryInboundDeduper()
    assert deduper.claim("wamid.SAME", tenant_id="tenant-a") is True
    assert deduper.claim("wamid.SAME", tenant_id="tenant-b") is True
    assert deduper.claim("wamid.SAME", tenant_id="tenant-a") is False


def test_claim_without_tenant_stays_duplicate() -> None:
    deduper = MemoryInboundDeduper()
    assert deduper.claim("wamid.ONE") is True
    assert deduper.claim("wamid.ONE") is False


def test_postgres_claim_is_per_tenant() -> None:
    import os
    from uuid import uuid4

    import pytest

    from factory_os.domain.postgres import apply_migrations
    from factory_os.tools.inbound_dedup import PostgresInboundDeduper

    url = os.environ.get("FACTORY_OS_TEST_DATABASE_URL")
    if not url:
        pytest.skip("FACTORY_OS_TEST_DATABASE_URL not set")
    try:
        apply_migrations(url)
    except Exception as exc:
        pytest.skip(f"postgres not reachable: {exc}")
    mid = f"wamid.PG-{uuid4().hex}"
    a = str(uuid4())
    b = str(uuid4())
    with __import__("psycopg").connect(url) as conn:
        conn.execute(
            "INSERT INTO tenants (id, name) VALUES (%s, 'A'), (%s, 'B') ON CONFLICT (id) DO NOTHING",
            (a, b),
        )
        conn.commit()
    deduper = PostgresInboundDeduper(url)
    assert deduper.claim(mid, tenant_id=a) is True
    assert deduper.claim(mid, tenant_id=b) is True
    assert deduper.claim(mid, tenant_id=a) is False


def test_duplicate_wamid_sends_once() -> None:
    shop = make_shop()
    shop.channel = FakeChannel()
    deduper = MemoryInboundDeduper()
    client = TestClient(
        create_app(shop, api_settings(meta_whatsapp_verify_token="t"), deduper=deduper)
    )
    body = _meta_payload("59174440001", "hola", "wamid.DEDUP1")
    assert post_meta(client, body).status_code == 200
    assert post_meta(client, body).status_code == 200
    assert post_meta(client, body).status_code == 200
    sent = [t for wa, t in shop.channel.sent if wa == "59174440001"]
    assert len(sent) == 1


def test_draft_rejects_prompt_leak() -> None:
    leak = (
        'We need to output a short (2-4 sentences) response in Spanish of Bolivia, '
        'using "tú" form. The last Adri message: "Hola". The customer said "Hola".'
    )
    assert draft_leaks_prompt(leak) is True
    assert grounded_draft(leak, {"hits": []}, "Hola, ¿qué prenda buscas?") == "Hola, ¿qué prenda buscas?"
