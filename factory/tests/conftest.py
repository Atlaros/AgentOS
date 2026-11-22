import hashlib
import hmac
import json
from typing import Any

from fastapi.testclient import TestClient

from factory_os.agents.turn import ShopRuntime
from factory_os.api.main import Settings, create_app
from factory_os.domain.models import PILOT_TENANT_ID
from factory_os.domain.seed import load_pilot_catalog
from factory_os.domain.store import MemoryCommerceStore
from factory_os.tools.registry import FakePaymentProvider

OWNER_TOKEN = "test-owner-token"
META_SECRET = "test-meta-secret"


def make_shop() -> ShopRuntime:
    store = MemoryCommerceStore(PILOT_TENANT_ID)
    load_pilot_catalog(store)
    return ShopRuntime(store, FakePaymentProvider())


def api_settings(**overrides: Any) -> Settings:
    """API settings for tests; the developer's `.env` must not leak in."""
    values: dict[str, Any] = {
        "app_env": "test",
        "owner_dashboard_token": OWNER_TOKEN,
        "meta_whatsapp_app_secret": META_SECRET,
        "database_url": "",
        "database_runtime_url": "",
        "redis_url": "",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def owner_client(shop: ShopRuntime, settings: Settings | None = None, **app_kwargs: Any) -> TestClient:
    client = TestClient(create_app(shop, settings or api_settings(), **app_kwargs))
    client.headers["Authorization"] = f"Bearer {OWNER_TOKEN}"
    return client


def post_meta(client: TestClient, payload: dict[str, Any], secret: str = META_SECRET):
    raw = json.dumps(payload).encode()
    signature = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    return client.post(
        "/webhooks/whatsapp",
        content=raw,
        headers={"content-type": "application/json", "x-hub-signature-256": f"sha256={signature}"},
    )
