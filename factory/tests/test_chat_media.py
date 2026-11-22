"""ADR-015 Fase C: WhatsApp inbound/outbound chat media."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from uuid import UUID

from factory_os.domain.models import OrderItem, PILOT_TENANT_ID, PaymentStatus
from factory_os.tools.channel import FakeChannel, parse_inbound
from factory_os.tools.inbound_dedup import MemoryInboundDeduper
from tests.conftest import api_settings, make_shop, owner_client, post_meta

PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000a49444154789c63000100000500010d0a2db40000000049454e44ae426082"
)


def _image_payload(*, wa: str, wamid: str, media_id: str, caption: str = "") -> dict:
    image: dict = {"id": media_id, "mime_type": "image/png"}
    if caption:
        image["caption"] = caption
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
                                    "type": "image",
                                    "image": image,
                                }
                            ]
                        }
                    }
                ]
            }
        ]
    }


def test_parse_inbound_keeps_media_id_for_image() -> None:
    parsed = parse_inbound(
        _image_payload(wa="5917111", wamid="wamid.img", media_id="media.99")
    )
    assert len(parsed) == 1
    assert parsed[0].media_id == "media.99"
    assert parsed[0].media_kind == "image"
    assert parsed[0].mime == "image/png"
    assert parsed[0].message_id == "wamid.img"
    assert parsed[0].text == "te envío el comprobante de pago"


def test_inbound_stores_asset_once_and_enriches_detail(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MEDIA_DIR", str(tmp_path))
    shop = make_shop()
    shop.channel = FakeChannel()
    downloads: list[str] = []

    def fake_download(media_id: str, **_kwargs) -> tuple[bytes, str]:
        downloads.append(media_id)
        return PNG, "image/png"

    client = owner_client(
        shop,
        api_settings(),
        deduper=MemoryInboundDeduper(),
        media_downloader=fake_download,
    )
    payload = _image_payload(
        wa="59180001111",
        wamid="wamid.once",
        media_id="meta.media.1",
        caption="foto de la blusa",
    )
    posted = post_meta(client, payload)
    assert posted.status_code == 200, posted.text
    assert downloads == ["meta.media.1"]

    listed = client.get("/api/conversations").json()["conversations"]
    assert listed
    conv_id = listed[0]["id"]
    detail = client.get(f"/api/conversations/{conv_id}").json()
    media_msgs = [m for m in detail["messages"] if m.get("media")]
    assert len(media_msgs) == 1
    media = media_msgs[0]["media"]
    assert media["status"] == "ready"
    assert media["kind"] == "image"
    assert media["asset_id"]
    assert media.get("thumb_url", "").startswith("/api/media/")

    files = detail.get("files") or []
    assert len(files) == 1
    assert files[0]["asset_id"] == media["asset_id"]

    # Duplicate wamid delivery must not create a second asset (deduper skips webhook).
    posted2 = post_meta(client, payload)
    assert posted2.status_code == 200
    assert downloads == ["meta.media.1"]
    detail2 = client.get(f"/api/conversations/{conv_id}").json()
    assert len([m for m in detail2["messages"] if m.get("media")]) == 1
    assert len(detail2.get("files") or []) == 1

    # Same provider_ref store path is also idempotent if invoked again.
    from factory_os.domain.chat_media import store_inbound_chat_media

    again = store_inbound_chat_media(
        shop.store,
        PILOT_TENANT_ID,
        conversation_id=UUID(conv_id),
        provider_ref="wamid.once",
        media_id="meta.media.1",
        media_kind="image",
        mime="image/png",
        filename=None,
        caption="foto de la blusa",
        text_for_origin="foto de la blusa",
        message_index=0,
        downloader=fake_download,
    )
    assert again.asset_id is not None
    assert str(again.asset_id) == media["asset_id"]
    assert downloads == ["meta.media.1"]


def test_invalid_media_does_not_break_inbound_text(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MEDIA_DIR", str(tmp_path))
    shop = make_shop()
    shop.channel = FakeChannel()

    def bad_download(media_id: str, **_kwargs) -> tuple[bytes, str]:
        return b"%PDF-1.4 not-an-image", "application/pdf"

    client = owner_client(
        shop,
        api_settings(),
        deduper=MemoryInboundDeduper(),
        media_downloader=bad_download,
    )
    # Claim image kind but bytes are pdf → validation fail; chat text still flows.
    payload = _image_payload(
        wa="59180002222",
        wamid="wamid.bad",
        media_id="meta.bad",
        caption="hola con archivo raro",
    )
    posted = post_meta(client, payload)
    assert posted.status_code == 200
    listed = client.get("/api/conversations").json()["conversations"]
    assert listed
    conv_id = listed[0]["id"]
    detail = client.get(f"/api/conversations/{conv_id}").json()
    assert any("hola con archivo raro" in (m.get("text") or "") for m in detail["messages"])
    files = detail.get("files") or []
    assert files
    assert files[0]["status"] == "failed"
    assert not files[0].get("asset_id")


def test_manual_send_requires_takeover(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MEDIA_DIR", str(tmp_path))
    shop = make_shop()
    shop.channel = FakeChannel()
    client = owner_client(shop)
    shop.handle_inbound(PILOT_TENANT_ID, "59180003333", "hola")
    conv = next(iter(shop.store.conversations.values()))
    assert conv.state.human_takeover is False

    denied = client.post(
        f"/api/conversations/{conv.id}/media",
        files={"file": ("shot.png", PNG, "image/png")},
    )
    assert denied.status_code in {403, 409}, denied.text

    client.post(f"/api/conversations/{conv.id}/takeover")
    ok = client.post(
        f"/api/conversations/{conv.id}/media",
        files={"file": ("shot.png", PNG, "image/png")},
        data={"caption": "te mando la foto"},
    )
    assert ok.status_code == 200, ok.text
    body = ok.json()
    files = body.get("files") or []
    assert any(f.get("origin") == "chat_outbound" or f.get("direction") == "outbound" for f in files)
    assert shop.channel.images
    assert shop.channel.images[-1]["wa_number"] == "59180003333"


def test_receipt_media_does_not_confirm_payment(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MEDIA_DIR", str(tmp_path))
    shop = make_shop()
    shop.channel = FakeChannel()

    def fake_download(media_id: str, **_kwargs) -> tuple[bytes, str]:
        return PNG, "image/png"

    # Seed a pending payment like QR flow, then send receipt image.
    customer = shop.store.get_or_create_customer(PILOT_TENANT_ID, "59180004444")
    order = shop.store.create_order(
        PILOT_TENANT_ID,
        customer.id,
        OrderItem("h001-M-VP", "H001", 1, Decimal("1"), "BOB"),
    )
    payment = shop.store.create_payment(
        PILOT_TENANT_ID,
        order.id,
        "fake",
        "bn-receipt-media",
        Decimal("1"),
        "BOB",
        "QR:receipt-media",
        customer_id=customer.id,
    )
    assert payment.status is PaymentStatus.PENDING

    client = owner_client(
        shop,
        api_settings(),
        deduper=MemoryInboundDeduper(),
        media_downloader=fake_download,
    )
    posted = post_meta(
        client,
        _image_payload(wa="59180004444", wamid="wamid.receipt", media_id="meta.receipt"),
    )
    assert posted.status_code == 200
    still = shop.store.get_payment(PILOT_TENANT_ID, payment.id)
    assert still is not None
    assert still.status is not PaymentStatus.CONFIRMED

    listed = client.get("/api/conversations").json()["conversations"]
    conv_id = next(c["id"] for c in listed if c["wa_number"] == "59180004444")
    detail = client.get(f"/api/conversations/{conv_id}").json()
    files = detail.get("files") or []
    assert files
    assert files[0].get("origin") == "receipt" or any(
        (m.get("media") or {}).get("origin") == "receipt" for m in detail["messages"] if m.get("media")
    )
