"""ADR-015 Fase E: chat media transcription / document summary (staff-facing)."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from factory_os.api.main import create_app
from factory_os.domain.chat_media import store_inbound_chat_media
from factory_os.domain.media_enrichment import (
    FakeMediaEnricher,
    enrich_conversation_media,
)
from factory_os.domain.models import OrderItem, PILOT_TENANT_ID, PaymentStatus
from factory_os.tools.channel import FakeChannel
from factory_os.tools.inbound_dedup import MemoryInboundDeduper
from tests.conftest import api_settings, make_shop, owner_client

PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000a49444154789c63000100000500010d0a2db40000000049454e44ae426082"
)
PDF = b"%PDF-1.4 fake-document-for-summary\n%%EOF\n"
AUDIO = b"ID3fake-audio-bytes-for-transcript"


def _store_kind(
    shop,
    *,
    wa: str,
    kind: str,
    data: bytes,
    mime: str,
    filename: str,
    caption: str = "",
):
    customer = shop.store.get_or_create_customer(PILOT_TENANT_ID, wa)
    conv = shop.store.get_or_create_conversation(PILOT_TENANT_ID, customer)
    shop.store.append_message(conv, "Cliente", caption or f"archivo {kind}")
    msg_index = max(0, len(conv.messages) - 1)

    def downloader(media_id: str, **_kwargs) -> tuple[bytes, str]:
        return data, mime

    link = store_inbound_chat_media(
        shop.store,
        PILOT_TENANT_ID,
        conversation_id=conv.id,
        provider_ref=f"wamid.{kind}.{uuid4().hex[:8]}",
        media_id=f"meta.{kind}",
        media_kind=kind,
        mime=mime,
        filename=filename,
        caption=caption,
        text_for_origin=caption or f"archivo {kind}",
        message_index=msg_index,
        downloader=downloader,
    )
    shop.store.save_conversation_state(conv)
    return conv, link


def test_fake_enricher_audio_transcript_document_summary_image_empty() -> None:
    enricher = FakeMediaEnricher()
    audio = enricher.enrich("audio", "audio/ogg", "voice.ogg", AUDIO)
    assert audio.transcript
    assert audio.summary is None

    doc = enricher.enrich("document", "application/pdf", "nota.pdf", PDF)
    assert doc.summary
    assert doc.transcript is None

    image = enricher.enrich("image", "image/png", "shot.png", PNG)
    assert image.transcript is None
    assert image.summary is None


def test_enrich_audio_persists_transcript(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MEDIA_DIR", str(tmp_path))
    shop = make_shop()
    conv, link = _store_kind(
        shop,
        wa="59190001111",
        kind="audio",
        data=AUDIO,
        mime="audio/ogg",
        filename="voice.ogg",
    )
    assert link.status == "ready"
    assert (link.enrichment_status or "none") == "none"

    updated = enrich_conversation_media(
        shop.store,
        PILOT_TENANT_ID,
        link.id,
        enricher=FakeMediaEnricher(),
    )
    assert updated is not None
    assert updated.enrichment_status == "ready"
    assert updated.transcript_text
    assert updated.summary_text is None

    client = owner_client(shop)
    detail = client.get(f"/api/conversations/{conv.id}").json()
    files = detail.get("files") or []
    row = next(f for f in files if f["id"] == str(link.id))
    assert row["enrichment_status"] == "ready"
    assert row["transcript_text"]
    assert row.get("summary_text") in (None, "")


def test_enrich_pdf_persists_summary(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MEDIA_DIR", str(tmp_path))
    shop = make_shop()
    conv, link = _store_kind(
        shop,
        wa="59190002222",
        kind="document",
        data=PDF,
        mime="application/pdf",
        filename="nota.pdf",
        caption="te mando la nota",
    )
    updated = enrich_conversation_media(
        shop.store,
        PILOT_TENANT_ID,
        link.id,
        enricher=FakeMediaEnricher(),
    )
    assert updated is not None
    assert updated.enrichment_status == "ready"
    assert updated.summary_text
    assert updated.transcript_text is None

    client = owner_client(shop)
    detail = client.get(f"/api/conversations/{conv.id}").json()
    row = next(f for f in detail["files"] if f["id"] == str(link.id))
    assert row["summary_text"]
    assert row["enrichment_status"] == "ready"


def test_enrich_image_is_noop_none(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MEDIA_DIR", str(tmp_path))
    shop = make_shop()
    _conv, link = _store_kind(
        shop,
        wa="59190003333",
        kind="image",
        data=PNG,
        mime="image/png",
        filename="shot.png",
        caption="foto",
    )
    updated = enrich_conversation_media(
        shop.store,
        PILOT_TENANT_ID,
        link.id,
        enricher=FakeMediaEnricher(),
    )
    assert updated is not None
    assert updated.enrichment_status == "none"
    assert updated.transcript_text is None
    assert updated.summary_text is None


def test_enrich_does_not_confirm_payment(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MEDIA_DIR", str(tmp_path))
    shop = make_shop()
    customer = shop.store.get_or_create_customer(PILOT_TENANT_ID, "59190004444")
    order = shop.store.create_order(
        PILOT_TENANT_ID,
        customer.id,
        OrderItem("h001-M-VP", "H001", 1, Decimal("1"), "BOB"),
    )
    payment = shop.store.create_payment(
        PILOT_TENANT_ID,
        order.id,
        "fake",
        "bn-enrich-receipt",
        Decimal("1"),
        "BOB",
        "QR:enrich-receipt",
        customer_id=customer.id,
    )
    assert payment.status is PaymentStatus.PENDING

    _conv, link = _store_kind(
        shop,
        wa="59190004444",
        kind="document",
        data=PDF,
        mime="application/pdf",
        filename="comprobante.pdf",
        caption="comprobante de pago",
    )
    enrich_conversation_media(
        shop.store,
        PILOT_TENANT_ID,
        link.id,
        enricher=FakeMediaEnricher(),
    )
    still = shop.store.get_payment(PILOT_TENANT_ID, payment.id)
    assert still is not None
    assert still.status is not PaymentStatus.CONFIRMED


def test_enrich_endpoint_audio_and_auth(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MEDIA_DIR", str(tmp_path))
    shop = make_shop()
    shop.channel = FakeChannel()
    conv, link = _store_kind(
        shop,
        wa="59190005555",
        kind="audio",
        data=AUDIO,
        mime="audio/ogg",
        filename="voice.ogg",
    )
    client = owner_client(
        shop,
        api_settings(),
        deduper=MemoryInboundDeduper(),
        media_enricher=FakeMediaEnricher(),
    )
    ok = client.post(f"/api/conversations/{conv.id}/media/{link.id}/enrich")
    assert ok.status_code == 200, ok.text
    body = ok.json()
    files = body.get("files") or []
    row = next(f for f in files if f["id"] == str(link.id))
    assert row["enrichment_status"] == "ready"
    assert row["transcript_text"]

    bare = TestClient(create_app(shop=shop, media_enricher=FakeMediaEnricher()))
    assert (
        bare.post(f"/api/conversations/{conv.id}/media/{link.id}/enrich").status_code
        == 401
    )


def test_enrich_unknown_media_404(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MEDIA_DIR", str(tmp_path))
    shop = make_shop()
    customer = shop.store.get_or_create_customer(PILOT_TENANT_ID, "59190006666")
    conv = shop.store.get_or_create_conversation(PILOT_TENANT_ID, customer)
    client = owner_client(shop, media_enricher=FakeMediaEnricher())
    missing = uuid4()
    res = client.post(f"/api/conversations/{conv.id}/media/{missing}/enrich")
    assert res.status_code == 404
