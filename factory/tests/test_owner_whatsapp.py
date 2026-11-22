from factory_os.domain.operator_registry import clear_operator_registry
from factory_os.domain.signup_invites import clear_invites
from factory_os.domain.signup_rate_limit import clear_signup_limits
from factory_os.api.main import create_app
from fastapi.testclient import TestClient
from tests.conftest import api_settings, make_shop, owner_client, post_meta


def test_owner_reserves_a_phone_the_pilot_does_not_answer() -> None:
    from factory_os.domain.business_owners import clear_business_owners

    clear_operator_registry()
    clear_invites()
    clear_signup_limits()
    clear_business_owners()
    from factory_os.agents.reserved_shop import clear_reserved_shops

    clear_reserved_shops()
    shop = make_shop()
    client = owner_client(
        shop,
        api_settings(public_signup_enabled=True, meta_whatsapp_phone_number_id="100"),
    )
    code = client.post("/api/operator/invites").json()["code"]
    created = client.post(
        "/api/public/signup",
        json={"name": "Cafe Luna", "industry": "cafe", "invite": code},
    )
    assert created.status_code == 200
    email = created.json()["owner_email"]
    secret = created.json()["owner_secret"]
    session = client.post("/api/owner/login", json={"email": email, "secret": secret}).json()["session"]
    owner = {"Authorization": f"Bearer {session}"}
    reserved = client.post("/api/owner/whatsapp", json={"phone_number_id": "100"}, headers=owner)
    assert reserved.status_code == 409
    assert reserved.json()["detail"] == "pilot_phone_reserved"
    saved = client.post("/api/owner/whatsapp", json={"phone_number_id": "555"}, headers=owner)
    assert saved.status_code == 200
    assert saved.json()["whatsapp_phone_id"] == "555"
    assert saved.json()["whatsapp_status"] == "not_connected"
    business = client.get("/api/owner/business", headers=owner)
    assert business.status_code == 200
    assert business.json()["whatsapp_phone_id"] == "555"
    assert business.json()["whatsapp_status"] == "not_connected"
    foreign = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "metadata": {"phone_number_id": "555"},
                            "messages": [
                                {
                                    "from": "59170001111",
                                    "id": "wamid.luna",
                                    "type": "text",
                                    "text": {"body": "hola"},
                                }
                            ],
                        }
                    }
                ]
            }
        ]
    }
    assert post_meta(client, foreign).status_code == 200
    after_foreign = client.get("/api/conversations").json()["conversations"]
    assert all(item["wa_number"] != "59170001111" for item in after_foreign)
    assert all(number != "59170001111" for number, _text in shop.channel.sent)
    inbox = client.get("/api/owner/messages", headers=owner)
    assert inbox.status_code == 200
    replies = [item for item in inbox.json()["messages"] if item["wa_number"] == "59170001111"]
    assert replies
    assert replies[0]["text"].strip()
    assert "Closet" not in replies[0]["text"]
    assert "Café" in replies[0]["text"]
    assert replies[0]["delivered"] is False
    pilot = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "metadata": {"phone_number_id": "100"},
                            "messages": [
                                {
                                    "from": "59170002222",
                                    "id": "wamid.pilot",
                                    "type": "text",
                                    "text": {"body": "hola"},
                                }
                            ],
                        }
                    }
                ]
            }
        ]
    }
    assert post_meta(client, pilot).status_code == 200
    after_pilot = client.get("/api/conversations").json()["conversations"]
    assert any(item["wa_number"] == "59170002222" for item in after_pilot)


def test_reserved_reply_uses_the_owner_token_not_the_pilot(monkeypatch) -> None:
    from factory_os.agents.reserved_shop import clear_reserved_shops
    from factory_os.domain.business_owners import clear_business_owners

    clear_operator_registry()
    clear_invites()
    clear_signup_limits()
    clear_business_owners()
    clear_reserved_shops()
    shop = make_shop()
    client = owner_client(
        shop,
        api_settings(
            public_signup_enabled=True,
            meta_whatsapp_phone_number_id="100",
            meta_whatsapp_access_token="pilot-meta-token",
        ),
    )
    code = client.post("/api/operator/invites").json()["code"]
    created = client.post(
        "/api/public/signup",
        json={"name": "Cafe Luna", "industry": "cafe", "invite": code},
    )
    email = created.json()["owner_email"]
    secret = created.json()["owner_secret"]
    session = client.post("/api/owner/login", json={"email": email, "secret": secret}).json()["session"]
    owner = {"Authorization": f"Bearer {session}"}
    rejected = client.post(
        "/api/owner/whatsapp",
        json={"phone_number_id": "555", "access_token": "pilot-meta-token"},
        headers=owner,
    )
    assert rejected.status_code == 409
    assert rejected.json()["detail"] == "pilot_token_reserved"
    saved = client.post(
        "/api/owner/whatsapp",
        json={"phone_number_id": "555", "access_token": "owner-meta-token"},
        headers=owner,
    )
    assert saved.status_code == 200
    assert saved.json()["whatsapp_token_set"] is True
    assert "owner-meta-token" not in saved.text
    sent: list[tuple[str, str, str, str]] = []

    def capture(access_token: str, phone_number_id: str, wa_number: str, text: str) -> None:
        sent.append((access_token, phone_number_id, wa_number, text))

    monkeypatch.setattr("factory_os.agents.reserved_shop.deliver_reserved", capture)
    foreign = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "metadata": {"phone_number_id": "555"},
                            "messages": [
                                {
                                    "from": "59170003333",
                                    "id": "wamid.meta",
                                    "type": "text",
                                    "text": {"body": "hola"},
                                }
                            ],
                        }
                    }
                ]
            }
        ]
    }
    assert post_meta(client, foreign).status_code == 200
    assert len(sent) == 1
    token, phone_id, wa_number, text = sent[0]
    assert token == "owner-meta-token"
    assert token != "pilot-meta-token"
    assert phone_id == "555"
    assert wa_number == "59170003333"
    assert "Café" in text
    assert all(number != "59170003333" for number, _text in shop.channel.sent)

    def explode(access_token: str, phone_number_id: str, wa_number: str, text: str) -> None:
        raise RuntimeError("meta down")

    monkeypatch.setattr("factory_os.agents.reserved_shop.deliver_reserved", explode)
    failed = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "metadata": {"phone_number_id": "555"},
                            "messages": [
                                {
                                    "from": "59170004444",
                                    "id": "wamid.meta-down",
                                    "type": "text",
                                    "text": {"body": "hola"},
                                }
                            ],
                        }
                    }
                ]
            }
        ]
    }
    assert post_meta(client, failed).status_code == 200
    inbox = client.get("/api/owner/messages", headers=owner)
    assert any(item["wa_number"] == "59170004444" for item in inbox.json()["messages"])
    assert all(number != "59170004444" for number, _text in shop.channel.sent)


def test_own_token_marks_the_business_ready_and_leaves_the_pilot_connected() -> None:
    from factory_os.domain.business_owners import clear_business_owners
    from factory_os.domain.models import PILOT_TENANT_ID
    from factory_os.domain.provision import provision_business

    clear_operator_registry()
    clear_invites()
    clear_signup_limits()
    clear_business_owners()
    client = owner_client(
        make_shop(),
        api_settings(
            public_signup_enabled=True,
            meta_whatsapp_phone_number_id="100",
            meta_whatsapp_access_token="pilot-meta-token",
        ),
    )
    provision_business(name="Pilot", industry="cafe", tenant_id=PILOT_TENANT_ID)
    code = client.post("/api/operator/invites").json()["code"]
    created = client.post(
        "/api/public/signup",
        json={"name": "Cafe Luna", "industry": "cafe", "invite": code},
    )
    session = client.post(
        "/api/owner/login",
        json={"email": created.json()["owner_email"], "secret": created.json()["owner_secret"]},
    ).json()["session"]
    owner = {"Authorization": f"Bearer {session}"}
    saved = client.post(
        "/api/owner/whatsapp",
        json={"phone_number_id": "555", "access_token": "owner-meta-token"},
        headers=owner,
    )
    assert saved.status_code == 200
    assert saved.json()["whatsapp_status"] == "own_number"
    business = client.get("/api/owner/business", headers=owner)
    assert business.json()["whatsapp_status"] == "own_number"
    rows = {row["name"]: row for row in client.get("/api/operator/businesses").json()["businesses"]}
    assert rows["Cafe Luna"]["whatsapp_status"] == "own_number"
    assert rows["Pilot"]["whatsapp_status"] == "connected"


def test_reserved_reply_records_whether_it_left(monkeypatch) -> None:
    from factory_os.agents.reserved_shop import clear_reserved_shops
    from factory_os.domain.business_owners import clear_business_owners

    clear_operator_registry()
    clear_invites()
    clear_signup_limits()
    clear_business_owners()
    clear_reserved_shops()
    shop = make_shop()
    client = owner_client(
        shop,
        api_settings(
            public_signup_enabled=True,
            meta_whatsapp_phone_number_id="100",
            meta_whatsapp_access_token="pilot-meta-token",
        ),
    )
    code = client.post("/api/operator/invites").json()["code"]
    created = client.post(
        "/api/public/signup",
        json={"name": "Cafe Luna", "industry": "cafe", "invite": code},
    )
    session = client.post(
        "/api/owner/login",
        json={"email": created.json()["owner_email"], "secret": created.json()["owner_secret"]},
    ).json()["session"]
    owner = {"Authorization": f"Bearer {session}"}

    def inbound(phone_id: str, wa_number: str, message_id: str) -> dict:
        return {
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "metadata": {"phone_number_id": phone_id},
                                "messages": [
                                    {
                                        "from": wa_number,
                                        "id": message_id,
                                        "type": "text",
                                        "text": {"body": "hola"},
                                    }
                                ],
                            }
                        }
                    ]
                }
            ]
        }

    def for_number(wa_number: str) -> list[dict]:
        messages = client.get("/api/owner/messages", headers=owner).json()["messages"]
        return [item for item in messages if item["wa_number"] == wa_number]

    saved = client.post("/api/owner/whatsapp", json={"phone_number_id": "555"}, headers=owner)
    assert saved.status_code == 200
    assert post_meta(client, inbound("555", "59170005555", "wamid.local")).status_code == 200
    stored = for_number("59170005555")
    assert stored[0]["delivered"] is False
    assert "Café" in stored[0]["text"]

    with_token = client.post(
        "/api/owner/whatsapp",
        json={"phone_number_id": "555", "access_token": "owner-meta-token"},
        headers=owner,
    )
    assert with_token.status_code == 200
    monkeypatch.setattr("factory_os.agents.reserved_shop.deliver_reserved", lambda *_args: None)
    assert post_meta(client, inbound("555", "59170006666", "wamid.sent")).status_code == 200
    assert for_number("59170005555")[0]["delivered"] is False
    assert for_number("59170006666")[0]["delivered"] is True

    def explode(*_args: object) -> None:
        raise RuntimeError("meta down")

    monkeypatch.setattr("factory_os.agents.reserved_shop.deliver_reserved", explode)
    assert post_meta(client, inbound("555", "59170007777", "wamid.down")).status_code == 200
    assert for_number("59170007777")[0]["delivered"] is False
    assert all(
        number not in {"59170005555", "59170006666", "59170007777"}
        for number, _text in shop.channel.sent
    )


def test_reloaded_phone_answers_as_its_own_industry(monkeypatch) -> None:
    from uuid import uuid4

    import psycopg

    from factory_os.agents.reserved_shop import clear_reserved_shops, reserved_messages
    from factory_os.domain.operator_registry import BusinessRecord, _PHONES

    clear_operator_registry()
    clear_reserved_shops()
    tenant_id = uuid4()
    shop = make_shop()
    client = owner_client(
        shop,
        api_settings(
            database_runtime_url="postgresql://unused",
            meta_whatsapp_phone_number_id="100",
            meta_whatsapp_access_token="pilot-meta-token",
        ),
    )

    def load(url: str | None) -> None:
        assert url == "postgresql://unused"
        _PHONES[tenant_id] = "555"

    def businesses(*, url: str | None = None) -> list[BusinessRecord]:
        if not url:
            return []
        return [BusinessRecord(tenant_id=tenant_id, name="Ropa Norte", industry="ropa", modules=())]

    def fail(_url: str):
        raise psycopg.errors.UndefinedTable("business_reserved_replies")

    monkeypatch.setattr("factory_os.domain.operator_registry.load_business_channels", load)
    monkeypatch.setattr("factory_os.domain.operator_registry.list_businesses", businesses)
    monkeypatch.setattr("factory_os.domain.postgres.connect", fail)
    foreign = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "metadata": {"phone_number_id": "555"},
                            "messages": [
                                {
                                    "from": "59170008888",
                                    "id": "wamid.ropa",
                                    "type": "text",
                                    "text": {"body": "hola"},
                                }
                            ],
                        }
                    }
                ]
            }
        ]
    }
    assert post_meta(client, foreign).status_code == 200
    replies = reserved_messages(tenant_id)
    assert replies
    assert "Closet" in str(replies[0]["text"])
    assert "Café" not in str(replies[0]["text"])
    assert all(number != "59170008888" for number, _text in shop.channel.sent)


def test_missing_channel_table_keeps_the_phone_in_memory(monkeypatch) -> None:
    import psycopg
    from uuid import uuid4

    from factory_os.domain.operator_registry import (
        assign_business_phone,
        keep_business_token,
        phone_for_tenant,
        token_for_tenant,
    )

    clear_operator_registry()

    def fail(_url: str):
        raise psycopg.errors.UndefinedTable("business_whatsapp")

    monkeypatch.setattr("factory_os.domain.postgres.connect", fail)
    tenant = uuid4()
    phone = assign_business_phone(tenant, "555", reserved_phone_id="100", url="postgresql://unused")
    keep_business_token(tenant, "owner-meta-token", url="postgresql://unused")
    assert phone == "555"
    assert phone_for_tenant(tenant) == "555"
    assert token_for_tenant(tenant) == "owner-meta-token"


def test_reserved_channel_survives_a_memory_reset_on_postgres() -> None:
    import os
    from uuid import uuid4

    import pytest

    from factory_os.domain.operator_registry import (
        assign_business_phone,
        keep_business_token,
        load_business_channels,
        phone_for_tenant,
        token_for_tenant,
    )
    from factory_os.domain.postgres import apply_migrations
    from factory_os.domain.provision import provision_business

    url = os.environ.get("FACTORY_OS_TEST_DATABASE_URL")
    if not url:
        pytest.skip("FACTORY_OS_TEST_DATABASE_URL not set")
    clear_operator_registry()
    tenant_id = uuid4()
    try:
        apply_migrations(url)
        provision_business(name="Persist Luna", industry="cafe", url=url, tenant_id=tenant_id)
        assign_business_phone(tenant_id, "555", reserved_phone_id="100", url=url)
        keep_business_token(tenant_id, "owner-meta-token", url=url)
    except Exception as exc:
        pytest.skip(f"postgres not reachable: {exc}")
    clear_operator_registry()
    assert phone_for_tenant(tenant_id) == ""
    assert token_for_tenant(tenant_id) == ""
    load_business_channels(url)
    assert phone_for_tenant(tenant_id) == "555"
    assert token_for_tenant(tenant_id) == "owner-meta-token"
    assert "owner-meta-token" not in phone_for_tenant(tenant_id)


def test_missing_reply_table_keeps_the_reply_in_memory(monkeypatch) -> None:
    import psycopg
    from uuid import uuid4

    from factory_os.agents.reserved_shop import (
        answer_reserved,
        clear_reserved_shops,
        mark_reserved_delivered,
        reserved_messages,
    )

    clear_reserved_shops()

    def fail(_url: str):
        raise psycopg.errors.UndefinedTable("business_reserved_replies")

    monkeypatch.setattr("factory_os.domain.postgres.connect", fail)
    tenant = uuid4()
    reply = answer_reserved(
        tenant,
        industry="cafe",
        wa_number="59170009999",
        text="hola",
        url="postgresql://unused",
    )
    assert "Café" in reply
    mark_reserved_delivered(tenant, url="postgresql://unused")
    messages = reserved_messages(tenant, url="postgresql://unused")
    assert messages[0]["wa_number"] == "59170009999"
    assert messages[0]["delivered"] is True


def test_reserved_reply_survives_a_memory_reset_on_postgres() -> None:
    import os
    from uuid import uuid4

    import pytest

    from factory_os.agents.reserved_shop import (
        answer_reserved,
        clear_reserved_shops,
        mark_reserved_delivered,
        reserved_messages,
    )
    from factory_os.domain.postgres import apply_migrations
    from factory_os.domain.provision import provision_business

    url = os.environ.get("FACTORY_OS_TEST_DATABASE_URL")
    if not url:
        pytest.skip("FACTORY_OS_TEST_DATABASE_URL not set")
    clear_reserved_shops()
    tenant_id = uuid4()
    try:
        apply_migrations(url)
        provision_business(name="Persist Luna", industry="cafe", url=url, tenant_id=tenant_id)
        answer_reserved(
            tenant_id,
            industry="cafe",
            wa_number="59170001111",
            text="hola",
            url=url,
        )
        mark_reserved_delivered(tenant_id, url=url)
    except Exception as exc:
        pytest.skip(f"postgres not reachable: {exc}")
    clear_reserved_shops()
    assert reserved_messages(tenant_id) == []
    messages = reserved_messages(tenant_id, url=url)
    assert len(messages) == 1
    assert messages[0]["wa_number"] == "59170001111"
    assert messages[0]["delivered"] is True
    assert "Café" in str(messages[0]["text"])
