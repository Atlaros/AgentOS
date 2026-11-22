from factory_os.api.main import create_app
from factory_os.domain.models import PILOT_TENANT_ID
from factory_os.tools.channel import FakeChannel, parse_inbound
from factory_os.tools.inbound_dedup import MemoryInboundDeduper
from tests.conftest import api_settings, make_shop, owner_client, post_meta
from fastapi.testclient import TestClient


def test_parse_meta_and_simple_payloads() -> None:
    simple = parse_inbound({"from": "5917111", "text": "hola", "tenant_id": "should-ignore"})
    assert len(simple) == 1
    assert simple[0].wa_number == "5917111"
    assert simple[0].text == "hola"
    meta = parse_inbound(
        {
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "messages": [
                                    {
                                        "from": "5917222",
                                        "id": "wamid.X",
                                        "type": "text",
                                        "text": {"body": "blusa"},
                                    }
                                ]
                            }
                        }
                    ]
                }
            ]
        }
    )
    assert len(meta) == 1
    assert meta[0].wa_number == "5917222"
    assert meta[0].text == "blusa"
    assert meta[0].message_id == "wamid.X"


def test_webhook_verify_and_inbound() -> None:
    shop = make_shop()
    shop.channel = FakeChannel()
    settings = api_settings(meta_whatsapp_verify_token="closet-verify")
    client = owner_client(shop, settings, deduper=MemoryInboundDeduper())
    denied = client.get("/webhooks/whatsapp", params={"hub.mode": "subscribe", "hub.verify_token": "no", "hub.challenge": "99"})
    assert denied.status_code == 403
    ok = client.get(
        "/webhooks/whatsapp",
        params={"hub.mode": "subscribe", "hub.verify_token": "closet-verify", "hub.challenge": "99"},
    )
    assert ok.status_code == 200
    assert ok.text == "99"

    payload = {"from": "5917333", "text": "hola", "tenant_id": "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"}
    assert client.post("/webhooks/whatsapp", json=payload).status_code == 403
    assert post_meta(client, payload, secret="otro").status_code == 403
    posted = post_meta(client, payload)
    assert posted.status_code == 200
    listed = client.get("/api/conversations").json()["conversations"]
    assert listed
    assert listed[0]["wa_number"] == "5917333"
    assert shop.store.tenant_id == PILOT_TENANT_ID
    assert any(num == "5917333" for num, _ in shop.channel.sent)
    assert any(num == "5917333" for num, _ in shop.channel.typing)


def test_webhook_fails_closed_without_meta_secret() -> None:
    shop = make_shop()
    shop.channel = FakeChannel()
    client = TestClient(create_app(shop, api_settings(meta_whatsapp_app_secret="")))
    response = post_meta(client, {"from": "5917334", "text": "hola"})
    assert response.status_code == 503
    assert response.json()["detail"] == "meta_signature_not_configured"
    assert shop.channel.sent == []


def test_inbox_html() -> None:
    client = TestClient(create_app(make_shop()))
    page = client.get("/inbox")
    assert page.status_code == 200
    assert "Mesa Closet" in page.text
