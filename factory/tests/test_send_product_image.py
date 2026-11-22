"""ADR-015 Fase D: send_product_image tool (sku only; caption from store)."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest

from factory_os.contracts.employees import EmployeeRole, identity_for
from factory_os.domain.models import PILOT_TENANT_ID
from factory_os.domain.sales_decision import (
    ADRI_TOOLS,
    parse_sales_decision,
    validate_sales_decision,
)
from factory_os.domain.stock import tracks_stock
from factory_os.harness.policy import PolicyDenied
from factory_os.harness.tools import PermissionDenied
from factory_os.tools.channel import FakeChannel
from tests.conftest import make_shop, owner_client

PRODUCT_SKU = "h001"
VARIANT_SKU = "h001-M-VP"
PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000a49444154789c63000100000500010d0a2db40000000049454e44ae426082"
)
WA = "59170009999"


def _seed_primary_media(shop, tmp_path: Path, monkeypatch) -> str:
    monkeypatch.setenv("MEDIA_DIR", str(tmp_path))
    monkeypatch.setenv("CATALOG_IMAGES_DIR", str(tmp_path))
    client = owner_client(shop)
    uploaded = client.post(
        f"/api/catalog/{VARIANT_SKU}/image",
        files={"file": ("one.png", PNG, "image/png")},
    )
    assert uploaded.status_code == 200, uploaded.text
    asset_id = uploaded.json()["asset_id"]
    links = shop.store.list_product_media(PILOT_TENANT_ID, PRODUCT_SKU)
    assert links, "expected product_media after catalog upload"
    assert any(row.is_primary for row in links)
    return asset_id


def _sales_payload(
    *,
    product_sku: str = PRODUCT_SKU,
    wa_number: str = WA,
    conversation_id: str | None = None,
    human_takeover: bool = False,
    sent_product_skus: list[str] | None = None,
    **extra,
) -> dict:
    body = {
        "product_sku": product_sku,
        "wa_number": wa_number,
        "conversation_id": conversation_id or str(uuid4()),
        "human_takeover": human_takeover,
        "sent_product_skus": list(sent_product_skus or []),
    }
    body.update(extra)
    return body


def test_send_product_image_valid_sku_sends_bytes_and_store_caption(
    tmp_path: Path, monkeypatch
) -> None:
    shop = make_shop()
    shop.channel = FakeChannel()
    shop._bind_tools()
    asset_id = _seed_primary_media(shop, tmp_path, monkeypatch)
    record = shop.store.get_variant(PILOT_TENANT_ID, VARIANT_SKU)
    assert record is not None
    adri = identity_for(EmployeeRole.SALES, PILOT_TENANT_ID)
    cid = uuid4()

    result = shop.tools.execute(
        adri, "send_product_image", _sales_payload(conversation_id=str(cid))
    )

    assert result.get("ok") is True
    assert result.get("asset_id") == asset_id
    assert shop.channel.images, "expected FakeChannel.images entry"
    image = shop.channel.images[0]
    assert image["wa_number"] == WA
    assert image["size"] == len(PNG)
    caption = image["caption"]
    assert record.name.split()[0] in caption or record.name in caption
    assert str(record.price) in caption
    linked = shop.store.list_conversation_media(PILOT_TENANT_ID, cid)
    assert linked
    assert linked[0].direction == "outbound"
    assert str(linked[0].asset_id) == asset_id


def test_send_product_image_denies_url_in_payload(tmp_path: Path, monkeypatch) -> None:
    shop = make_shop()
    shop.channel = FakeChannel()
    shop._bind_tools()
    _seed_primary_media(shop, tmp_path, monkeypatch)
    adri = identity_for(EmployeeRole.SALES, PILOT_TENANT_ID)

    with pytest.raises(PolicyDenied) as exc:
        shop.tools.execute(
            adri,
            "send_product_image",
            _sales_payload(url="https://evil.example/x.png"),
        )
    assert exc.value.code == "model_media_url"
    assert shop.channel.images == []


def test_send_product_image_denies_human_takeover(tmp_path: Path, monkeypatch) -> None:
    shop = make_shop()
    shop.channel = FakeChannel()
    shop._bind_tools()
    _seed_primary_media(shop, tmp_path, monkeypatch)
    adri = identity_for(EmployeeRole.SALES, PILOT_TENANT_ID)

    with pytest.raises(PolicyDenied) as exc:
        shop.tools.execute(
            adri,
            "send_product_image",
            _sales_payload(human_takeover=True),
        )
    assert exc.value.code == "human_takeover"
    assert shop.channel.images == []


def test_send_product_image_denies_out_of_stock(tmp_path: Path, monkeypatch) -> None:
    shop = make_shop()
    shop.channel = FakeChannel()
    shop._bind_tools()
    _seed_primary_media(shop, tmp_path, monkeypatch)
    for record in shop.store.iter_variants():
        if record.product_sku != PRODUCT_SKU:
            continue
        if tracks_stock(record):
            shop.store.set_variant_availability(
                PILOT_TENANT_ID, record.variant_sku, available=False, stock=0
            )
    adri = identity_for(EmployeeRole.SALES, PILOT_TENANT_ID)

    with pytest.raises(PolicyDenied) as exc:
        shop.tools.execute(adri, "send_product_image", _sales_payload())
    assert exc.value.code == "out_of_stock"
    assert shop.channel.images == []


def test_send_product_image_duplicate_same_turn_denied(tmp_path: Path, monkeypatch) -> None:
    shop = make_shop()
    shop.channel = FakeChannel()
    shop._bind_tools()
    _seed_primary_media(shop, tmp_path, monkeypatch)
    adri = identity_for(EmployeeRole.SALES, PILOT_TENANT_ID)
    cid = str(uuid4())

    first = shop.tools.execute(
        adri, "send_product_image", _sales_payload(conversation_id=cid)
    )
    assert first.get("ok") is True
    assert len(shop.channel.images) == 1

    with pytest.raises(PolicyDenied) as exc:
        shop.tools.execute(
            adri,
            "send_product_image",
            _sales_payload(conversation_id=cid, sent_product_skus=[PRODUCT_SKU]),
        )
    assert exc.value.code == "already_sent"
    assert len(shop.channel.images) == 1


def test_send_product_image_unknown_sku_denied() -> None:
    shop = make_shop()
    shop.channel = FakeChannel()
    shop._bind_tools()
    adri = identity_for(EmployeeRole.SALES, PILOT_TENANT_ID)

    with pytest.raises(PolicyDenied) as exc:
        shop.tools.execute(
            adri, "send_product_image", _sales_payload(product_sku="no-such-sku")
        )
    assert exc.value.code == "unknown_product"
    assert shop.channel.images == []


def test_send_product_image_permission_sales_only() -> None:
    shop = make_shop()
    shop.channel = FakeChannel()
    shop._bind_tools()
    cobros = identity_for(EmployeeRole.COBROS, PILOT_TENANT_ID)
    with pytest.raises(PermissionDenied):
        shop.tools.execute(cobros, "send_product_image", _sales_payload())


def test_adri_allowlist_includes_send_product_image() -> None:
    assert "send_product_image" in ADRI_TOOLS
    decision = parse_sales_decision(
        {
            "action": "recommend",
            "tool_call": {
                "name": "send_product_image",
                "arguments": {"product_sku": PRODUCT_SKU},
            },
        },
        provider="gemini",
    )
    assert decision is not None
    assert validate_sales_decision(decision) == []
