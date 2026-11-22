"""A reserved WhatsApp phone answers on its own shop, never on the live channel."""

from __future__ import annotations

import json
from uuid import UUID

from factory_os.agents.turn import ShopRuntime
from factory_os.domain.seed import catalog_seed_path, load_catalog_for_store
from factory_os.domain.store import MemoryCommerceStore
from factory_os.tools.channel import FakeChannel
from factory_os.tools.registry import FakePaymentProvider

_SHOPS: dict[UUID, ShopRuntime] = {}
_REPLIES: dict[UUID, list[dict[str, object]]] = {}
_LATEST_BATCH: dict[UUID, int] = {}
_REPLIES_LOADED = False


def clear_reserved_shops() -> None:
    global _REPLIES_LOADED
    _SHOPS.clear()
    _REPLIES.clear()
    _LATEST_BATCH.clear()
    _REPLIES_LOADED = False


def answer_reserved(
    tenant_id: UUID,
    *,
    industry: str,
    wa_number: str,
    text: str,
    url: str | None = None,
) -> str:
    shop = _shop_for(tenant_id, industry)
    channel = shop.channel
    before = len(channel.sent) if isinstance(channel, FakeChannel) else 0
    result = shop.handle_inbound(tenant_id, wa_number, text)
    after = len(channel.sent) if isinstance(channel, FakeChannel) else before
    added = max(0, after - before)
    batch: list[dict[str, object]] = []
    if isinstance(channel, FakeChannel):
        for number, body in channel.sent[before:after]:
            entry: dict[str, object] = {
                "wa_number": number,
                "text": body,
                "delivered": False,
            }
            batch.append(entry)
            _REPLIES.setdefault(tenant_id, []).append(entry)
            _persist_reply(url, tenant_id, entry)
    _LATEST_BATCH[tenant_id] = len(batch)
    return result.reply or ""


def mark_reserved_delivered(tenant_id: UUID, *, url: str | None = None) -> None:
    added = _LATEST_BATCH.get(tenant_id, 0)
    replies = _REPLIES.get(tenant_id)
    if replies is None or added <= 0:
        return
    ids: list[int] = []
    for index in range(len(replies) - added, len(replies)):
        replies[index]["delivered"] = True
        reply_id = replies[index].get("id")
        if isinstance(reply_id, int):
            ids.append(reply_id)
    _mark_persisted(url, ids)


def deliver_reserved(access_token: str, phone_number_id: str, wa_number: str, text: str) -> None:
    """Send with this business token. Callers must not pass the live channel token."""
    from factory_os.tools.channel import MetaChannel

    MetaChannel(access_token, phone_number_id).send_text(wa_number, text)


def reserved_messages(tenant_id: UUID, *, url: str | None = None) -> list[dict[str, object]]:
    load_reserved_replies(url)
    return [
        {
            "wa_number": str(item.get("wa_number") or ""),
            "text": str(item.get("text") or ""),
            "delivered": bool(item.get("delivered")),
        }
        for item in _REPLIES.get(tenant_id, [])
    ]


def load_reserved_replies(url: str | None) -> None:
    """Fill the reply map from the database. A missing table leaves memory as it is."""
    global _REPLIES_LOADED
    database = (url or "").strip()
    if not database or _REPLIES_LOADED:
        return
    from factory_os.domain.postgres import connect

    try:
        conn = connect(database)
    except Exception as exc:
        if _missing_relation(exc):
            return
        raise
    try:
        rows = conn.execute(
            """
            SELECT id, tenant_id, wa_number, body, delivered
            FROM business_reserved_replies
            ORDER BY id
            """
        ).fetchall()
    except Exception as exc:
        if _missing_relation(exc):
            return
        raise
    finally:
        conn.close()
    loaded: dict[UUID, list[dict[str, object]]] = {}
    for row in rows:
        tenant_id = row["tenant_id"] if isinstance(row["tenant_id"], UUID) else UUID(str(row["tenant_id"]))
        loaded.setdefault(tenant_id, []).append(
            {
                "id": int(row["id"]),
                "wa_number": str(row.get("wa_number") or ""),
                "text": str(row.get("body") or ""),
                "delivered": bool(row.get("delivered")),
            }
        )
    for tenant_id, items in loaded.items():
        if tenant_id not in _REPLIES:
            _REPLIES[tenant_id] = items
    _REPLIES_LOADED = True


def _shop_for(tenant_id: UUID, industry: str) -> ShopRuntime:
    existing = _SHOPS.get(tenant_id)
    if existing is not None:
        return existing
    store = MemoryCommerceStore(tenant_id)
    kind = "closet" if industry in {"ropa", "closet"} else "cafe"
    load_catalog_for_store(store, catalog_seed_path(kind))
    card_name = "shop_cafe.json" if kind == "cafe" else "shop_closet.json"
    card = json.loads((catalog_seed_path(kind).parent / card_name).read_text(encoding="utf-8"))
    store.put_shop_knowledge(tenant_id, card)
    shop = ShopRuntime(store, FakePaymentProvider(), channel=FakeChannel())
    _SHOPS[tenant_id] = shop
    return shop


def _persist_reply(url: str | None, tenant_id: UUID, entry: dict[str, object]) -> None:
    database = (url or "").strip()
    if not database:
        return
    from factory_os.domain.postgres import connect

    try:
        conn = connect(database)
    except Exception as exc:
        if _missing_relation(exc):
            return
        raise
    try:
        row = conn.execute(
            """
            INSERT INTO business_reserved_replies (tenant_id, wa_number, body, delivered)
            VALUES (%s, %s, %s, %s)
            RETURNING id
            """,
            (
                str(tenant_id),
                str(entry.get("wa_number") or ""),
                str(entry.get("text") or ""),
                bool(entry.get("delivered")),
            ),
        ).fetchone()
        conn.commit()
        if row is not None:
            entry["id"] = int(row["id"])
    except Exception as exc:
        if _missing_relation(exc):
            return
        raise
    finally:
        conn.close()


def _mark_persisted(url: str | None, ids: list[int]) -> None:
    database = (url or "").strip()
    if not database or not ids:
        return
    from factory_os.domain.postgres import connect

    try:
        conn = connect(database)
    except Exception as exc:
        if _missing_relation(exc):
            return
        raise
    try:
        conn.execute(
            "UPDATE business_reserved_replies SET delivered = true WHERE id = ANY(%s)",
            (ids,),
        )
        conn.commit()
    except Exception as exc:
        if _missing_relation(exc):
            return
        raise
    finally:
        conn.close()


def _missing_relation(exc: BaseException) -> bool:
    import psycopg

    return isinstance(exc, psycopg.errors.UndefinedTable)
