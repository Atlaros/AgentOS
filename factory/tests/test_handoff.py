from factory_os.agents.turn import CUSTOMER_NOTICE
from factory_os.domain.models import PILOT_TENANT_ID
from factory_os.tools.channel import FakeChannel
from tests.conftest import make_shop, owner_client, post_meta


def _shop() -> tuple:
    shop = make_shop()
    shop.channel = FakeChannel()
    shop.owner_numbers = ["59170009999"]
    shop.inbox_base_url = "http://test/inbox"
    return shop


def test_customer_asks_for_human_notifies_owner_once() -> None:
    shop = _shop()
    first = shop.handle_inbound(PILOT_TENANT_ID, "59171110000", "quiero un humano")
    assert first.needs_human
    assert not first.human_takeover
    assert CUSTOMER_NOTICE in first.reply
    owner_notes = [text for num, text in shop.channel.sent if num == "59170009999"]
    assert len(owner_notes) == 1
    assert "59171110000" in owner_notes[0]
    assert "http://test/inbox?c=" in owner_notes[0]
    shop.handle_inbound(PILOT_TENANT_ID, "59171110000", "sigue sin haber persona")
    owner_notes = [text for num, text in shop.channel.sent if num == "59170009999"]
    assert len(owner_notes) == 1


def test_hola_is_welcome_not_catalog_miss() -> None:
    shop = _shop()
    result = shop.handle_inbound(PILOT_TENANT_ID, "59171110004", "hola")
    assert result.employee == "Adri"
    assert "No encontré esa prenda" not in result.reply
    assert "Adri de Authentic Closet" in result.reply
    assert not result.needs_human
    assert not any(num == "59170009999" for num, _ in shop.channel.sent)


def test_typo_restart_clears_search_without_human() -> None:
    shop = _shop()
    shop.handle_turn(PILOT_TENANT_ID, "59171110005", "xyzqwerty-no-existe")
    restart = shop.handle_turn(PILOT_TENANT_ID, "59171110005", "emcpecemos de neuvo")
    assert "Adri de Authentic Closet" in restart.reply
    assert "No encontré esa prenda" not in restart.reply
    conv = shop.store.list_conversations(PILOT_TENANT_ID)[0]
    assert conv.state.considered_variant_sku is None


def test_unknown_product_marks_needs_human() -> None:
    shop = _shop()
    result = shop.handle_turn(PILOT_TENANT_ID, "59171110001", "xyzqwerty-no-existe")
    assert result.needs_human
    assert "No encontré esa prenda" in result.reply
    assert any(num == "59170009999" for num, _ in shop.channel.sent)


def test_takeover_silences_agent_and_human_replies() -> None:
    shop = _shop()
    shop.handle_inbound(PILOT_TENANT_ID, "59171110002", "quiero un humano")
    conv_id = shop.store.list_conversations(PILOT_TENANT_ID)[0].id
    shop.set_takeover(PILOT_TENANT_ID, conv_id, True)
    before = list(shop.channel.sent)
    silent = shop.handle_inbound(PILOT_TENANT_ID, "59171110002", "¿sigue ahí?")
    assert silent.human_takeover
    assert silent.reply == ""
    assert shop.channel.sent == before
    shop.human_reply(PILOT_TENANT_ID, conv_id, "Hola, te atiende el dueño")
    assert ("59171110002", "Hola, te atiende el dueño") in shop.channel.sent
    conv = shop.store.get_conversation(PILOT_TENANT_ID, conv_id)
    assert conv is not None
    assert conv.messages[-1] == ("Humano", "Hola, te atiende el dueño")


def test_operator_api_reply_pauses_agent_without_prior_takeover() -> None:
    shop = _shop()
    client = owner_client(shop)
    assert post_meta(client, {"from": "59171110003", "text": "quiero un humano"}).status_code == 200
    conv_id = client.get("/api/conversations").json()["conversations"][0]["id"]
    replied = client.post(f"/api/conversations/{conv_id}/reply", json={"text": "te ayudo yo"})
    assert replied.status_code == 200
    body = replied.json()
    assert body["human_takeover"] is True
    assert body["messages"][-1] == {"role": "Humano", "text": "te ayudo yo"}
    before = list(shop.channel.sent)
    silent = shop.handle_inbound(PILOT_TENANT_ID, "59171110003", "¿sigue ahí?")
    assert silent.human_takeover
    assert silent.reply == ""
    assert shop.channel.sent == before
    released = client.post(f"/api/conversations/{conv_id}/release")
    assert released.status_code == 200
    assert released.json()["human_takeover"] is False
