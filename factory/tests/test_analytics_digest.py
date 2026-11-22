"""T3: one opt-in WhatsApp digest per La Paz day, only when typed alerts are active."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from factory_os.api.main import create_app
from factory_os.domain.analytics_digest import format_analytics_digest, run_owner_analytics_digest
from factory_os.domain.models import PILOT_TENANT_ID
from factory_os.tools.channel import FakeChannel
from tests.conftest import api_settings, make_shop, owner_client

# 16:00 UTC is 12:00 in America/La_Paz. 03:30 UTC next calendar day is still 23:30 the same La Paz date.
NOW = datetime(2026, 11, 11, 16, 0, tzinfo=UTC)
LATER_SAME_LA_PAZ_DAY = datetime(2026, 11, 12, 3, 30, tzinfo=UTC)
OWNERS = ["59170009999", "59170008888"]


def _channel(shop) -> FakeChannel:
    channel = FakeChannel()
    shop.channel = channel
    shop.owner_numbers = list(OWNERS)
    return channel


def _enable(shop, enabled: bool = True) -> None:
    current = shop.store.get_analytics_thresholds(PILOT_TENANT_ID)
    shop.store.put_analytics_thresholds(
        PILOT_TENANT_ID,
        replace(current, digest_whatsapp_enabled=enabled),
    )


def _low_stock(shop) -> None:
    records = list(shop.store.iter_variants())
    for record in records:
        record.stock = 8
        record.reorder_threshold = 1
    records[0].stock = 0


def _quiet(shop) -> None:
    for record in shop.store.iter_variants():
        record.stock = 8
        record.reorder_threshold = 1


def _run(shop, channel, *, now: datetime = NOW, force: bool = False) -> dict:
    return run_owner_analytics_digest(
        shop.store,
        PILOT_TENANT_ID,
        channel,
        list(OWNERS),
        now=now,
        force=force,
    )


def test_format_lists_active_alert_labels_counts_and_paths() -> None:
    text = format_analytics_digest(
        {
            "alert_type_count": 1,
            "alerts": [
                {
                    "type": "low_stock",
                    "label": "Stock bajo",
                    "count": 2,
                    "href": "/suppliers?tab=reposicion",
                }
            ],
            "kpis": [
                {"id": "revenue", "kind": "money", "current": "10.00"},
                {"id": "sales", "kind": "count", "current": 1},
            ],
        }
    )
    assert "Stock bajo" in text
    assert "2" in text
    assert "/suppliers?tab=reposicion" in text
    assert "10.00" in text


def test_disabled_digest_does_not_send() -> None:
    shop = make_shop()
    channel = _channel(shop)
    _low_stock(shop)
    _enable(shop, False)

    result = _run(shop, channel)

    assert result["status"] == "disabled"
    assert result["sent"] == 0
    assert channel.sent == []


def test_enabled_with_alerts_sends_once_per_la_paz_day() -> None:
    shop = make_shop()
    channel = _channel(shop)
    _low_stock(shop)
    _enable(shop, True)

    first = _run(shop, channel, now=NOW)
    assert first["status"] == "sent"
    assert first["sent"] == len(OWNERS)
    assert first["alert_type_count"] >= 1
    assert len(channel.sent) == len(OWNERS)
    assert {number for number, _text in channel.sent} == set(OWNERS)
    sent_text = channel.sent[0][1]
    assert "Stock bajo" in sent_text
    assert "/suppliers?tab=reposicion" in sent_text
    assert first["text_preview"] == sent_text

    second = _run(shop, channel, now=LATER_SAME_LA_PAZ_DAY)
    assert second["status"] == "skipped"
    assert second["reason"] == "already_sent"
    assert second["sent"] == 0
    assert len(channel.sent) == len(OWNERS)


def test_enabled_without_alerts_does_not_send() -> None:
    shop = make_shop()
    channel = _channel(shop)
    _quiet(shop)
    _enable(shop, True)

    result = _run(shop, channel)

    assert result["status"] == "no_alerts"
    assert result["sent"] == 0
    assert channel.sent == []


def test_force_resends_on_the_same_la_paz_day() -> None:
    shop = make_shop()
    channel = _channel(shop)
    _low_stock(shop)
    _enable(shop, True)

    assert _run(shop, channel, now=NOW)["status"] == "sent"
    forced = _run(shop, channel, now=LATER_SAME_LA_PAZ_DAY, force=True)
    assert forced["status"] == "sent"
    assert forced["sent"] == len(OWNERS)
    assert len(channel.sent) == len(OWNERS) * 2
    assert "Stock bajo" in channel.sent[-1][1]


def test_digest_route_uses_shop_channel_and_staff_cannot_run_it() -> None:
    shop = make_shop()
    channel = _channel(shop)
    _low_stock(shop)
    client = owner_client(shop)

    fresh = client.get("/api/analytics/thresholds")
    assert fresh.status_code == 200
    assert fresh.json()["digest_whatsapp_enabled"] is False

    patched = client.patch(
        "/api/analytics/thresholds",
        json={"digest_whatsapp_enabled": True},
    )
    assert patched.status_code == 200
    assert patched.json()["digest_whatsapp_enabled"] is True
    kept = client.patch("/api/analytics/thresholds", json={"qr_pending_hours": 36})
    assert kept.status_code == 200
    assert kept.json()["digest_whatsapp_enabled"] is True
    assert kept.json()["qr_pending_hours"] == 36

    denied = client.post(
        "/api/panel/users",
        json={
            "name": "Luis Staff",
            "email": "luis-digest@taller.local",
            "role": "staff",
            "secret": "staff-digest",
        },
    )
    assert denied.status_code == 200
    staff = TestClient(create_app(shop, api_settings()))
    staff.headers["Authorization"] = "Bearer staff-digest"
    assert staff.post("/api/analytics/digest/run", json={}).status_code == 403

    sent = client.post("/api/analytics/digest/run", json={})
    assert sent.status_code == 200
    body = sent.json()
    assert body["status"] == "sent"
    assert body["sent"] == len(OWNERS)
    assert len(channel.sent) == len(OWNERS)
    assert "Stock bajo" in channel.sent[0][1]

    again = client.post("/api/analytics/digest/run", json={"force": False})
    assert again.status_code == 200
    assert again.json()["status"] == "skipped"
    assert len(channel.sent) == len(OWNERS)

    manual = client.post("/api/analytics/digest/run", json={"force": True})
    assert manual.status_code == 200
    assert manual.json()["status"] == "sent"
    assert len(channel.sent) == len(OWNERS) * 2


def test_dry_run_previews_without_sending_and_force_is_owner_only() -> None:
    shop = make_shop()
    channel = _channel(shop)
    _low_stock(shop)
    _enable(shop, False)
    client = owner_client(shop)
    created = client.post(
        "/api/panel/users",
        json={
            "name": "Ana Super",
            "email": "ana-digest@taller.local",
            "role": "supervisor",
            "secret": "super-digest",
        },
    )
    assert created.status_code == 200
    supervisor = TestClient(create_app(shop, api_settings()))
    supervisor.headers["Authorization"] = "Bearer super-digest"

    assert supervisor.post("/api/analytics/digest/run", json={"force": True}).status_code == 403
    assert (
        supervisor.post(
            "/api/analytics/digest/run",
            json={"force": True, "dry_run": True},
        ).status_code
        == 403
    )
    cron = supervisor.post("/api/analytics/digest/run", json={})
    assert cron.status_code == 200
    assert cron.json()["status"] == "disabled"
    assert channel.sent == []

    preview = client.post("/api/analytics/digest/run", json={"force": True, "dry_run": True})
    assert preview.status_code == 200
    body = preview.json()
    assert body["status"] == "preview"
    assert body["sent"] == 0
    assert "Stock bajo" in body["text_preview"]
    assert channel.sent == []

    _quiet(shop)
    empty = client.post("/api/analytics/digest/run", json={"force": True, "dry_run": True})
    assert empty.status_code == 200
    assert empty.json()["status"] == "no_alerts"
    assert channel.sent == []
