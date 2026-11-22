from factory_os.domain.operator_registry import clear_operator_registry, list_businesses
from factory_os.domain.signup_invites import clear_invites
from factory_os.domain.signup_rate_limit import clear_signup_limits
from tests.conftest import api_settings, make_shop, owner_client
from factory_os.api.main import create_app
from fastapi.testclient import TestClient


def _enabled_client() -> TestClient:
    return TestClient(create_app(make_shop(), api_settings(public_signup_enabled=True)))


def test_public_signup_is_forbidden_without_flag() -> None:
    clear_operator_registry()
    client = TestClient(create_app(make_shop(), api_settings()))
    response = client.post(
        "/api/public/signup",
        json={"name": "Cafe Luna", "industry": "cafe", "invite": "anything"},
    )
    assert response.status_code == 403
    assert list_businesses() == []


def test_public_signup_is_forbidden_without_invite() -> None:
    clear_operator_registry()
    clear_invites()
    client = _enabled_client()
    response = client.post(
        "/api/public/signup",
        json={"name": "Cafe Luna", "industry": "cafe"},
    )
    assert response.status_code == 403
    assert list_businesses() == []


def test_public_signup_consumes_one_time_invite() -> None:
    clear_operator_registry()
    clear_invites()
    operator = owner_client(make_shop(), api_settings(public_signup_enabled=True))
    issued = operator.post("/api/operator/invites")
    assert issued.status_code == 200
    code = issued.json()["code"]

    public = TestClient(create_app(make_shop(), api_settings(public_signup_enabled=True)))
    first = public.post(
        "/api/public/signup",
        json={"name": "Cafe Luna", "industry": "cafe", "invite": code},
    )
    assert first.status_code == 200
    assert first.json()["name"] == "Cafe Luna"
    assert len(list_businesses()) == 1

    second = public.post(
        "/api/public/signup",
        json={"name": "Otra", "industry": "ropa", "invite": code},
    )
    assert second.status_code == 403
    assert len(list_businesses()) == 1


def test_signup_creates_an_owner_the_pilot_login_rejects() -> None:
    from factory_os.domain.business_owners import clear_business_owners, owner_matches

    clear_operator_registry()
    clear_invites()
    clear_signup_limits()
    clear_business_owners()
    operator = owner_client(make_shop(), api_settings(public_signup_enabled=True))
    code = operator.post("/api/operator/invites").json()["code"]
    public = TestClient(create_app(make_shop(), api_settings(public_signup_enabled=True)))
    created = public.post(
        "/api/public/signup",
        json={"name": "Cafe Luna", "industry": "cafe", "invite": code},
    )
    assert created.status_code == 200
    body = created.json()
    assert owner_matches(body["owner_email"], body["owner_secret"])
    login = public.post(
        "/api/panel/login",
        json={"email": body["owner_email"], "secret": body["owner_secret"]},
    )
    assert login.status_code == 401


def test_owner_session_reads_their_business_and_not_the_pilot() -> None:
    from factory_os.domain.business_owners import clear_business_owners

    clear_operator_registry()
    clear_invites()
    clear_signup_limits()
    clear_business_owners()
    operator = owner_client(make_shop(), api_settings(public_signup_enabled=True))
    first_code = operator.post("/api/operator/invites").json()["code"]
    second_code = operator.post("/api/operator/invites").json()["code"]
    public = TestClient(create_app(make_shop(), api_settings(public_signup_enabled=True)))
    luna = public.post(
        "/api/public/signup",
        json={"name": "Cafe Luna", "industry": "cafe", "invite": first_code},
    )
    otra = public.post(
        "/api/public/signup",
        json={"name": "Otra", "industry": "ropa", "invite": second_code},
    )
    assert luna.status_code == 200
    assert otra.status_code == 200
    email = luna.json()["owner_email"]
    secret = luna.json()["owner_secret"]
    denied = public.post("/api/panel/login", json={"email": email, "secret": secret})
    assert denied.status_code == 401
    opened = public.post("/api/owner/login", json={"email": email, "secret": secret})
    assert opened.status_code == 200
    session = opened.json()["session"]
    assert session != secret
    assert opened.json()["tenant_id"] == luna.json()["tenant_id"]
    headers = {"Authorization": f"Bearer {session}"}
    business = public.get("/api/owner/business", headers=headers)
    assert business.status_code == 200
    assert business.json()["name"] == "Cafe Luna"
    assert business.json()["tenant_id"] == luna.json()["tenant_id"]
    assert business.json()["name"] != otra.json()["name"]
    assert public.get("/api/owner/business").status_code == 401
    assert public.get(
        "/api/owner/business",
        headers={"Authorization": "Bearer test-owner-token"},
    ).status_code == 401
    assert public.get("/api/conversations", headers=headers).status_code == 401
    assert public.get("/api/operator/businesses", headers=headers).status_code == 401
    assert public.post(
        "/api/owner/login",
        json={"email": email, "secret": "nope"},
    ).status_code == 401


def test_owner_can_tighten_autonomy_for_their_business_only() -> None:
    from factory_os.domain.autonomy import clear_tenant_autonomy
    from factory_os.domain.business_owners import clear_business_owners

    clear_operator_registry()
    clear_invites()
    clear_signup_limits()
    clear_business_owners()
    clear_tenant_autonomy()
    operator = owner_client(make_shop(), api_settings(public_signup_enabled=True))
    first = operator.post("/api/operator/invites").json()["code"]
    second = operator.post("/api/operator/invites").json()["code"]
    public = TestClient(create_app(make_shop(), api_settings(public_signup_enabled=True)))
    luna = public.post(
        "/api/public/signup",
        json={"name": "Cafe Luna", "industry": "cafe", "invite": first},
    )
    otra = public.post(
        "/api/public/signup",
        json={"name": "Otra", "industry": "ropa", "invite": second},
    )
    assert luna.status_code == 200
    assert otra.status_code == 200
    opened = public.post(
        "/api/owner/login",
        json={"email": luna.json()["owner_email"], "secret": luna.json()["owner_secret"]},
    )
    assert opened.status_code == 200
    headers = {"Authorization": f"Bearer {opened.json()['session']}"}
    tightened = public.post(
        "/api/owner/autonomy",
        headers=headers,
        json={"action": "adjust_stock", "level": "never"},
    )
    assert tightened.status_code == 200
    stock = next(
        item for item in tightened.json()["autonomy"] if item["action"] == "adjust_stock"
    )
    assert stock["level"] == "never"
    business = public.get("/api/owner/business", headers=headers)
    assert business.status_code == 200
    listed = next(
        item for item in business.json()["autonomy"] if item["action"] == "adjust_stock"
    )
    assert listed["level"] == "never"
    denied = public.post(
        "/api/owner/autonomy",
        headers=headers,
        json={"action": "confirm_payment", "level": "within_limits"},
    )
    assert denied.status_code == 400
    assert public.post(
        "/api/owner/autonomy",
        json={"action": "adjust_stock", "level": "never"},
    ).status_code == 401


def test_owner_logout_revokes_the_session() -> None:
    from factory_os.domain.business_owners import clear_business_owners, close_owner_session

    clear_operator_registry()
    clear_invites()
    clear_signup_limits()
    clear_business_owners()
    operator = owner_client(make_shop(), api_settings(public_signup_enabled=True))
    code = operator.post("/api/operator/invites").json()["code"]
    public = TestClient(create_app(make_shop(), api_settings(public_signup_enabled=True)))
    created = public.post(
        "/api/public/signup",
        json={"name": "Cafe Luna", "industry": "cafe", "invite": code},
    )
    assert created.status_code == 200
    opened = public.post(
        "/api/owner/login",
        json={
            "email": created.json()["owner_email"],
            "secret": created.json()["owner_secret"],
        },
    )
    assert opened.status_code == 200
    session = opened.json()["session"]
    headers = {"Authorization": f"Bearer {session}"}
    assert public.get("/api/owner/business", headers=headers).status_code == 200
    closed = public.delete("/api/owner/session", headers=headers)
    assert closed.status_code == 200
    assert public.get("/api/owner/business", headers=headers).status_code == 401
    close_owner_session(session)
    assert public.get("/api/owner/business", headers=headers).status_code == 401


def test_missing_session_table_still_closes_in_memory(monkeypatch) -> None:
    import psycopg
    from uuid import uuid4

    from factory_os.domain.business_owners import (
        clear_business_owners,
        close_owner_session,
        issue_business_owner,
        open_owner_session,
        owner_for_session,
    )

    clear_business_owners()

    def fail(_url: str):
        raise psycopg.errors.UndefinedTable("owner_sessions")

    monkeypatch.setattr("factory_os.domain.postgres.connect", fail)
    tenant = uuid4()
    email, secret = issue_business_owner(tenant, name="Cafe Luna", url="postgresql://unused")
    opened = open_owner_session(email, secret, url="postgresql://unused")
    assert opened is not None
    token, _ = opened
    close_owner_session(token, url="postgresql://unused")
    assert owner_for_session(token, url="postgresql://unused") is None


def test_disabled_signup_creates_no_owner() -> None:
    from factory_os.domain.business_owners import clear_business_owners, owner_count

    clear_operator_registry()
    clear_business_owners()
    client = TestClient(create_app(make_shop(), api_settings()))
    response = client.post(
        "/api/public/signup",
        json={"name": "Cafe Luna", "industry": "cafe", "invite": "anything"},
    )
    assert response.status_code == 403
    assert owner_count() == 0


def test_public_signup_rate_limits_one_ip() -> None:
    clear_operator_registry()
    clear_invites()
    clear_signup_limits()
    settings = api_settings(
        public_signup_enabled=True,
        public_signup_max_per_window=1,
        public_signup_window_s=3600,
    )
    operator = owner_client(make_shop(), settings)
    first_code = operator.post("/api/operator/invites").json()["code"]
    second_code = operator.post("/api/operator/invites").json()["code"]

    same_ip = TestClient(
        create_app(make_shop(), settings),
        client=("203.0.113.10", 50000),
    )
    other_ip = TestClient(
        create_app(make_shop(), settings),
        client=("203.0.113.11", 50000),
    )
    first = same_ip.post(
        "/api/public/signup",
        json={"name": "Cafe Luna", "industry": "cafe", "invite": first_code},
    )
    assert first.status_code == 200

    blocked = same_ip.post(
        "/api/public/signup",
        json={"name": "Otra", "industry": "ropa", "invite": second_code},
    )
    assert blocked.status_code == 429
    assert len(list_businesses()) == 1

    moved = other_ip.post(
        "/api/public/signup",
        json={"name": "Otra", "industry": "ropa", "invite": second_code},
    )
    assert moved.status_code == 200
    assert len(list_businesses()) == 2


def test_forwarded_ip_does_not_bypass_the_signup_cap() -> None:
    clear_operator_registry()
    clear_invites()
    clear_signup_limits()
    settings = api_settings(
        public_signup_enabled=True,
        public_signup_max_per_window=1,
        public_signup_window_s=3600,
    )
    operator = owner_client(make_shop(), settings)
    first_code = operator.post("/api/operator/invites").json()["code"]
    second_code = operator.post("/api/operator/invites").json()["code"]
    client = TestClient(create_app(make_shop(), settings), client=("203.0.113.10", 50000))

    first = client.post(
        "/api/public/signup",
        headers={"x-forwarded-for": "198.51.100.8"},
        json={"name": "Cafe Luna", "industry": "cafe", "invite": first_code},
    )
    assert first.status_code == 200
    blocked = client.post(
        "/api/public/signup",
        headers={"x-forwarded-for": "198.51.100.9"},
        json={"name": "Otra", "industry": "ropa", "invite": second_code},
    )
    assert blocked.status_code == 429
    assert len(list_businesses()) == 1


def test_trusted_proxy_counts_signup_by_forwarded_ip() -> None:
    clear_operator_registry()
    clear_invites()
    clear_signup_limits()
    settings = api_settings(
        public_signup_enabled=True,
        public_signup_max_per_window=1,
        public_signup_window_s=3600,
        trusted_proxy_hops=1,
    )
    operator = owner_client(make_shop(), settings)
    first_code = operator.post("/api/operator/invites").json()["code"]
    second_code = operator.post("/api/operator/invites").json()["code"]
    tunnel = TestClient(create_app(make_shop(), settings), client=("127.0.0.1", 50000))

    first = tunnel.post(
        "/api/public/signup",
        headers={"x-forwarded-for": "198.51.100.8"},
        json={"name": "Cafe Luna", "industry": "cafe", "invite": first_code},
    )
    assert first.status_code == 200
    second = tunnel.post(
        "/api/public/signup",
        headers={"x-forwarded-for": "198.51.100.9"},
        json={"name": "Otra", "industry": "ropa", "invite": second_code},
    )
    assert second.status_code == 200
    assert len(list_businesses()) == 2


def test_public_signup_rejects_unknown_industry() -> None:
    clear_invites()
    operator = owner_client(make_shop(), api_settings(public_signup_enabled=True))
    code = operator.post("/api/operator/invites").json()["code"]
    client = _enabled_client()
    response = client.post(
        "/api/public/signup",
        json={"name": "X", "industry": "taller", "invite": code},
    )
    assert response.status_code == 400


def test_missing_owner_table_keeps_the_owner_in_memory(monkeypatch) -> None:
    import psycopg
    from uuid import uuid4

    from factory_os.domain.business_owners import (
        clear_business_owners,
        issue_business_owner,
        open_owner_session,
        owner_matches,
    )

    clear_business_owners()

    def fail(_url: str):
        raise psycopg.errors.UndefinedTable("business_owners")

    monkeypatch.setattr("factory_os.domain.postgres.connect", fail)
    tenant = uuid4()
    email, secret = issue_business_owner(tenant, name="Cafe Luna", url="postgresql://unused")
    assert owner_matches(email, secret)
    opened = open_owner_session(email, secret, url="postgresql://unused")
    assert opened is not None
    assert opened[1] == tenant


def test_owner_login_survives_a_memory_reset_on_postgres() -> None:
    import os
    from uuid import uuid4

    import pytest

    from factory_os.domain.business_owners import (
        clear_business_owners,
        issue_business_owner,
        open_owner_session,
        owner_matches,
    )
    from factory_os.domain.postgres import apply_migrations
    from factory_os.domain.provision import provision_business

    url = os.environ.get("FACTORY_OS_TEST_DATABASE_URL")
    if not url:
        pytest.skip("FACTORY_OS_TEST_DATABASE_URL not set")
    clear_business_owners()
    tenant_id = uuid4()
    try:
        apply_migrations(url)
        provision_business(name="Persist Luna", industry="cafe", url=url, tenant_id=tenant_id)
        email, secret = issue_business_owner(tenant_id, name="Persist Luna", url=url)
    except Exception as exc:
        pytest.skip(f"postgres not reachable: {exc}")
    clear_business_owners()
    assert not owner_matches(email, secret)
    opened = open_owner_session(email, secret, url=url)
    assert opened is not None
    assert opened[1] == tenant_id
    assert secret not in opened[0]


def test_missing_invite_table_keeps_the_invite_in_memory(monkeypatch) -> None:
    import psycopg

    from factory_os.domain.signup_invites import clear_invites, consume_invite, issue_invite

    clear_invites()

    def fail(_url: str):
        raise psycopg.errors.UndefinedTable("signup_invites")

    monkeypatch.setattr("factory_os.domain.postgres.connect", fail)
    code = issue_invite(url="postgresql://unused")
    assert consume_invite(code, url="postgresql://unused") is True
    assert consume_invite(code, url="postgresql://unused") is False


def test_invite_survives_a_memory_reset_on_postgres() -> None:
    import os

    import pytest

    from factory_os.domain.postgres import apply_migrations
    from factory_os.domain.signup_invites import clear_invites, consume_invite, issue_invite

    url = os.environ.get("FACTORY_OS_TEST_DATABASE_URL")
    if not url:
        pytest.skip("FACTORY_OS_TEST_DATABASE_URL not set")
    clear_invites()
    try:
        apply_migrations(url)
        code = issue_invite(url=url)
    except Exception as exc:
        pytest.skip(f"postgres not reachable: {exc}")
    clear_invites()
    assert consume_invite(code) is False
    assert consume_invite(code, url=url) is True
    assert consume_invite(code, url=url) is False


def test_missing_session_table_keeps_the_session_in_memory(monkeypatch) -> None:
    import psycopg
    from uuid import uuid4

    from factory_os.domain.business_owners import (
        clear_business_owners,
        issue_business_owner,
        open_owner_session,
        owner_for_session,
    )

    clear_business_owners()

    def fail(_url: str):
        raise psycopg.errors.UndefinedTable("owner_sessions")

    monkeypatch.setattr("factory_os.domain.postgres.connect", fail)
    tenant = uuid4()
    email, secret = issue_business_owner(tenant, name="Cafe Luna", url="postgresql://unused")
    opened = open_owner_session(email, secret, url="postgresql://unused")
    assert opened is not None
    token, _ = opened
    assert owner_for_session(token, url="postgresql://unused") is not None
    assert owner_for_session(token, url="postgresql://unused").tenant_id == tenant


def test_owner_session_survives_a_memory_reset_on_postgres() -> None:
    import os
    from uuid import uuid4

    import pytest

    from factory_os.domain.business_owners import (
        clear_business_owners,
        issue_business_owner,
        open_owner_session,
        owner_for_session,
    )
    from factory_os.domain.postgres import apply_migrations
    from factory_os.domain.provision import provision_business

    url = os.environ.get("FACTORY_OS_TEST_DATABASE_URL")
    if not url:
        pytest.skip("FACTORY_OS_TEST_DATABASE_URL not set")
    clear_business_owners()
    tenant_id = uuid4()
    try:
        apply_migrations(url)
        provision_business(name="Session Luna", industry="cafe", url=url, tenant_id=tenant_id)
        email, secret = issue_business_owner(tenant_id, name="Session Luna", url=url)
        opened = open_owner_session(email, secret, url=url)
    except Exception as exc:
        pytest.skip(f"postgres not reachable: {exc}")
    assert opened is not None
    token, _ = opened
    clear_business_owners()
    assert owner_for_session(token) is None
    owner = owner_for_session(token, url=url)
    assert owner is not None
    assert owner.tenant_id == tenant_id


def test_missing_rate_table_keeps_the_cap_in_memory(monkeypatch) -> None:
    import psycopg

    from factory_os.domain.signup_rate_limit import (
        clear_signup_limits,
        record_signup,
        signup_slot_open,
    )

    clear_signup_limits()

    def fail(_url: str):
        raise psycopg.errors.UndefinedTable("signup_rate_hits")

    monkeypatch.setattr("factory_os.domain.postgres.connect", fail)
    assert signup_slot_open("203.0.113.50", limit=1, window_s=3600, url="postgresql://unused")
    record_signup("203.0.113.50", url="postgresql://unused")
    assert not signup_slot_open("203.0.113.50", limit=1, window_s=3600, url="postgresql://unused")


def test_signup_cap_survives_a_memory_reset_on_postgres() -> None:
    import os

    import pytest

    from factory_os.domain.postgres import apply_migrations
    from factory_os.domain.signup_rate_limit import (
        clear_signup_limits,
        record_signup,
        signup_slot_open,
    )

    url = os.environ.get("FACTORY_OS_TEST_DATABASE_URL")
    if not url:
        pytest.skip("FACTORY_OS_TEST_DATABASE_URL not set")
    clear_signup_limits()
    try:
        apply_migrations(url)
        assert signup_slot_open("203.0.113.60", limit=1, window_s=3600, url=url)
        record_signup("203.0.113.60", url=url)
    except Exception as exc:
        pytest.skip(f"postgres not reachable: {exc}")
    clear_signup_limits()
    assert signup_slot_open("203.0.113.60", limit=1, window_s=3600)
    assert not signup_slot_open("203.0.113.60", limit=1, window_s=3600, url=url)
