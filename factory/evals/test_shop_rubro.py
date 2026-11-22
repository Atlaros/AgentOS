"""Evaluation: a non-Closet knowledge card answers its own FAQ and does not confirm payment."""

from factory_os.domain.knowledge import compact_shop_card, shop_reply
from factory_os.domain.models import PILOT_TENANT_ID
from tests.conftest import make_shop


def test_other_rubro_faq_does_not_confirm_payment_or_change_price() -> None:
    shop = make_shop()
    price = next(item.price for item in shop.store.iter_variants() if item.variant_sku == "h001-M-VP")
    shop.store.put_shop_knowledge(
        PILOT_TENANT_ID,
        {
            "profile": {"name": "Taller Luna", "hours": "10 a 19"},
            "vocabulary": {"item": "servicio"},
            "faqs": [
                {
                    "id": "turno",
                    "category": "Turnos",
                    "question": "puedo reservar un turno",
                    "answer": "Sí, decime el día y la hora.",
                }
            ],
            "payment_status": "confirmed",
            "price": "0",
        },
    )
    pack = shop.store.get_shop_knowledge(PILOT_TENANT_ID)
    assert pack is not None
    card = compact_shop_card(PILOT_TENANT_ID, pack)
    assert "Taller Luna" in card
    assert "turno" in card
    assert "confirmed" not in card
    reply = shop_reply("puedo reservar un turno", PILOT_TENANT_ID, pack)
    assert reply and "día" in reply
    assert "bolivia" not in (reply or "").lower()
    from factory_os.domain.knowledge_rag import retrieve_knowledge_snippets

    snippets = retrieve_knowledge_snippets(pack, "puedo reservar un turno")
    assert any(item["id"] == "turno" for item in snippets)
    assert "confirmed" not in str(snippets).lower()
    assert all("price" not in item for item in snippets)
    assert next(item.price for item in shop.store.iter_variants() if item.variant_sku == "h001-M-VP") == price
    assert shop.store.list_payments(PILOT_TENANT_ID) == []
