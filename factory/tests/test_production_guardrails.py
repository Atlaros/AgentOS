"""Startup fails closed when hosted/pilot settings are unsafe (v2-production-guardrails T6)."""

from __future__ import annotations

import pytest

import dotenv
from factory_os.api import main


@pytest.fixture
def isolated_env(monkeypatch: pytest.MonkeyPatch, tmp_path):
    """No `.env` from the repo: cwd without `.env` and `load_dotenv` disabled."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(dotenv, "load_dotenv", lambda *_a, **_k: False)
    for name in ("APP_ENV", "CATALOG_SEED", "DATABASE_URL", "DATABASE_RUNTIME_URL"):
        monkeypatch.setenv(name, "")
    main.get_shop.cache_clear()
    yield monkeypatch
    main.get_shop.cache_clear()


@pytest.mark.parametrize("app_env", ["", "production", "staging"])
def test_hosted_without_database_fails_closed(isolated_env, app_env: str) -> None:
    isolated_env.setenv("APP_ENV", app_env)
    isolated_env.setenv("CATALOG_SEED", "pay_test")
    with pytest.raises(RuntimeError, match="database_url_required_outside_local"):
        main.get_shop()


@pytest.mark.parametrize("runtime_url", ["", "postgresql://admin@db/x"])
def test_runtime_url_must_differ_from_admin_url(isolated_env, runtime_url: str) -> None:
    isolated_env.setenv("APP_ENV", "production")
    isolated_env.setenv("DATABASE_URL", "postgresql://admin@db/x")
    isolated_env.setenv("DATABASE_RUNTIME_URL", runtime_url)
    with pytest.raises(RuntimeError, match="separate_database_runtime_url_required"):
        main.get_shop()


@pytest.mark.parametrize("catalog_seed", ["closet", "cafe"])
def test_live_pilot_requires_database_even_locally(isolated_env, catalog_seed: str) -> None:
    isolated_env.setenv("APP_ENV", "local")
    isolated_env.setenv("CATALOG_SEED", catalog_seed)
    with pytest.raises(RuntimeError, match="database_url_required_for_closet_pilot"):
        main.get_shop()


def _patch_startup_io(monkeypatch: pytest.MonkeyPatch, calls: dict) -> None:
    from factory_os.domain.models import PILOT_TENANT_ID
    from factory_os.domain.store import MemoryCommerceStore
    from factory_os.tools.channel import MetaChannel

    def fake_open(url, tenant_id, path=None, extra_paths=None, *, runtime_url=None, sync_seed=True):
        calls["path"] = path
        calls["sync_seed"] = sync_seed
        return MemoryCommerceStore(tenant_id or PILOT_TENANT_ID)

    def fake_retain(*_args, **_kwargs) -> None:
        calls["pruned"] = True

    monkeypatch.setattr(main, "open_postgres_shop", fake_open)
    monkeypatch.setattr("factory_os.domain.postgres.retain_catalog_skus", fake_retain)
    monkeypatch.setattr("factory_os.domain.postgres.assert_rls_runtime_role", lambda _url: None)
    monkeypatch.setattr("factory_os.domain.postgres.ensure_local_rls_runtime_role", lambda *_a, **_k: None)
    monkeypatch.setattr("factory_os.harness.agent_trace.postgres_trace_sink", lambda _url: None)
    class _Gateway:
        trace_log = None

    monkeypatch.setattr(main, "_build_channel", lambda _settings: MetaChannel("token", "phone"))
    monkeypatch.setattr(main, "_gateway", lambda _settings, trace_log=None: _Gateway())

    class _Baneco:
        name = "baneco"

    monkeypatch.setattr("factory_os.tools.payments.build_payment_provider", lambda: _Baneco())


def test_production_startup_does_not_seed_or_prune_catalog(isolated_env) -> None:
    isolated_env.setenv("APP_ENV", "production")
    isolated_env.setenv("CATALOG_SEED", "cafe")
    isolated_env.setenv("DATABASE_URL", "postgresql://admin@db.example.com/cafe")
    isolated_env.setenv("DATABASE_RUNTIME_URL", "postgresql://app@db.example.com/cafe")
    calls: dict = {"pruned": False, "path": "unset", "sync_seed": "unset"}
    _patch_startup_io(isolated_env, calls)
    main.get_shop()
    assert calls["pruned"] is False
    assert calls["path"] is None
    assert calls["sync_seed"] is False


def test_local_startup_still_syncs_the_pilot_catalog(isolated_env) -> None:
    isolated_env.setenv("APP_ENV", "local")
    isolated_env.setenv("CATALOG_SEED", "cafe")
    isolated_env.setenv("DATABASE_URL", "postgresql://postgres@127.0.0.1:5434/factory_os_test")
    isolated_env.setenv(
        "DATABASE_RUNTIME_URL", "postgresql://app_runtime@127.0.0.1:5434/factory_os_test"
    )
    calls: dict = {"pruned": False, "path": None, "sync_seed": False}
    _patch_startup_io(isolated_env, calls)
    main.get_shop()
    assert calls["pruned"] is True
    assert calls["path"] is not None
    assert calls["sync_seed"] is True


def test_hosted_open_migrates_without_rewriting_catalog(monkeypatch: pytest.MonkeyPatch) -> None:
    from uuid import UUID

    from factory_os.domain import postgres

    calls: list[str] = []
    monkeypatch.setattr(postgres, "apply_migrations", lambda _url: calls.append("migrate"))
    monkeypatch.setattr(postgres, "seed_catalog", lambda *_a, **_k: calls.append("seed"))
    monkeypatch.setattr(postgres, "seed_shop_knowledge", lambda *_a, **_k: calls.append("knowledge"))
    monkeypatch.setattr(
        postgres, "seed_conversation_playbook", lambda *_a, **_k: calls.append("playbook")
    )

    class _Store:
        def mark_sold_for_confirmed_payments(self) -> None:
            calls.append("sold")

    monkeypatch.setattr(postgres, "PostgresCommerceStore", lambda *_a, **_k: _Store())
    postgres.open_postgres_shop(
        "postgresql://app@db.example.com/cafe",
        UUID("dddddddd-dddd-dddd-dddd-dddddddddddd"),
        sync_seed=False,
    )
    assert calls == ["migrate"]


def test_pilot_open_still_seeds_and_restores_sold(monkeypatch: pytest.MonkeyPatch) -> None:
    from pathlib import Path
    from uuid import UUID

    from factory_os.domain import postgres

    calls: list[str] = []
    monkeypatch.setattr(postgres, "apply_migrations", lambda _url: calls.append("migrate"))
    monkeypatch.setattr(postgres, "seed_catalog", lambda *_a, **_k: calls.append("seed"))
    monkeypatch.setattr(postgres, "seed_shop_knowledge", lambda *_a, **_k: calls.append("knowledge"))
    monkeypatch.setattr(
        postgres, "seed_conversation_playbook", lambda *_a, **_k: calls.append("playbook")
    )

    class _Store:
        def mark_sold_for_confirmed_payments(self) -> None:
            calls.append("sold")

    monkeypatch.setattr(postgres, "PostgresCommerceStore", lambda *_a, **_k: _Store())
    postgres.open_postgres_shop(
        "postgresql://postgres@127.0.0.1:5434/factory_os_test",
        UUID("dddddddd-dddd-dddd-dddd-dddddddddddd"),
        Path("catalog.json"),
    )
    assert calls == ["migrate", "seed", "knowledge", "playbook", "sold"]


def test_local_process_refuses_a_remote_database_host() -> None:
    from factory_os.domain.postgres import local_database_host_allowed

    assert local_database_host_allowed(
        "postgresql://postgres:postgres@127.0.0.1:5434/factory_os_test"
    )
    assert local_database_host_allowed(
        "postgresql://postgres:postgres@db:5432/factory_agent_os_v2"
    )
    assert not local_database_host_allowed(
        "postgresql://user:secret@db.example.com:5432/cafe"
    )
    assert not local_database_host_allowed(
        "postgresql://user:secret@aws-0-us-west-1.pooler.supabase.com:5432/postgres"
    )


def test_local_startup_does_not_open_a_remote_database(isolated_env) -> None:
    isolated_env.setenv("APP_ENV", "local")
    isolated_env.setenv("CATALOG_SEED", "cafe")
    isolated_env.setenv("DATABASE_URL", "postgresql://admin@db.example.com/cafe")
    isolated_env.setenv("DATABASE_RUNTIME_URL", "postgresql://app@db.example.com/cafe")

    def boom(*_args, **_kwargs):
        raise AssertionError("remote database was opened")

    isolated_env.setattr(main, "open_postgres_shop", boom)
    with pytest.raises(RuntimeError, match="local_remote_database_refused"):
        main.get_shop()


def test_runtime_url_without_admin_url_is_rejected_locally(isolated_env) -> None:
    isolated_env.setenv("APP_ENV", "local")
    isolated_env.setenv("CATALOG_SEED", "pay_test")
    isolated_env.setenv("DATABASE_RUNTIME_URL", "postgresql://app_runtime@db/x")
    with pytest.raises(RuntimeError, match="database_url_admin_required_for_runtime_database"):
        main.get_shop()
