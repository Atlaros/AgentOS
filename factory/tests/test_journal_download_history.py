"""T9 Contabilidad: record exports in report_download_log + history list."""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import make_shop, owner_client

LEDGER_REPORT_IDS = frozenset(
    {
        "journal",
        "ledger_hechos",
        "mayor",
        "resultado",
        "balance",
        "comprobacion",
        "conciliacion",
    }
)


def _panel_client(shop, secret: str) -> TestClient:
    from factory_os.api.main import create_app
    from tests.conftest import api_settings

    client = TestClient(create_app(shop, api_settings()))
    client.headers["Authorization"] = f"Bearer {secret}"
    return client


def _seed_roles(owner: TestClient) -> None:
    staff = owner.post(
        "/api/panel/users",
        json={
            "name": "Luis Staff",
            "email": "luis-journal-hist@taller.local",
            "role": "staff",
            "secret": "staff-journal-hist",
        },
    )
    assert staff.status_code == 200
    supervisor = owner.post(
        "/api/panel/users",
        json={
            "name": "Ana Super",
            "email": "ana-journal-hist@taller.local",
            "role": "supervisor",
            "secret": "super-journal-hist",
        },
    )
    assert supervisor.status_code == 200


def _seed_cash_sale(client: TestClient, amount: str = "40") -> None:
    client.post("/api/cash/session/open", json={"opening_float": "0"})
    posted = client.post(
        "/api/cash",
        json={
            "direction": "in",
            "amount": amount,
            "reason": "venta mostrador",
            "category": "venta",
            "method": "cash",
        },
    )
    assert posted.status_code == 200


def test_contabilidad_exports_record_download_history_newest_first() -> None:
    shop = make_shop()
    client = owner_client(shop)
    _seed_cash_sale(client)

    journal = client.get("/api/journal/export", params={"format": "xlsx", "period": "month"})
    assert journal.status_code == 200

    history = client.get("/api/reports/downloads/history")
    assert history.status_code == 200
    rows = history.json()["downloads"]
    assert rows[0]["report_id"] == "journal"
    assert rows[0]["period_id"] == "month"
    assert rows[0]["format"] == "xlsx"
    assert rows[0]["actor_name"] == "Dueño"
    assert rows[0]["created_at"]
    assert rows[0]["date_from"]
    assert rows[0]["date_to"]

    hechos = client.get("/api/ledger/export", params={"format": "csv", "period": "month"})
    assert hechos.status_code == 200

    income = client.get("/api/journal/income", params={"format": "xlsx", "period": "month"})
    assert income.status_code == 200

    again = client.get("/api/reports/downloads/history").json()["downloads"]
    assert [row["report_id"] for row in again[:3]] == ["resultado", "ledger_hechos", "journal"]
    assert again[0]["format"] == "xlsx"
    assert again[1]["format"] == "csv"
    assert again[1]["period_id"] == "month"
    assert again[0]["period_id"] == "month"


def test_contabilidad_mayor_comprobacion_balance_conciliacion_logged() -> None:
    shop = make_shop()
    client = owner_client(shop)
    _seed_cash_sale(client)

    paths = (
        ("/api/journal/ledger", {"format": "xlsx", "period": "month"}, "mayor", "xlsx"),
        ("/api/journal/trial-balance", {"format": "xlsx", "period": "month"}, "comprobacion", "xlsx"),
        ("/api/journal/balance-sheet", {"format": "pdf", "period": "month"}, "balance", "pdf"),
        ("/api/journal/bank-recon", {"format": "xlsx", "period": "month"}, "conciliacion", "xlsx"),
    )
    for path, params, report_id, fmt in paths:
        response = client.get(path, params=params)
        assert response.status_code == 200, f"{path} → {response.status_code}"
        newest = client.get("/api/reports/downloads/history").json()["downloads"][0]
        assert newest["report_id"] == report_id
        assert newest["format"] == fmt
        assert newest["period_id"] == "month"
        assert newest["actor_name"] == "Dueño"

    all_ids = {
        row["report_id"]
        for row in client.get("/api/reports/downloads/history").json()["downloads"]
    }
    assert {"mayor", "comprobacion", "balance", "conciliacion"} <= all_ids
    assert all_ids <= (LEDGER_REPORT_IDS | {"orders", "payments", "stock", "package"})


def test_json_views_do_not_record_download_history() -> None:
    shop = make_shop()
    client = owner_client(shop)
    _seed_cash_sale(client)

    for path in (
        "/api/journal/ledger",
        "/api/journal/income",
        "/api/journal/balance-sheet",
        "/api/journal/trial-balance",
        "/api/journal/bank-recon",
    ):
        assert client.get(path, params={"period": "month"}).status_code == 200

    history = client.get("/api/reports/downloads/history").json()["downloads"]
    assert history == []


def test_staff_cannot_read_download_history_supervisor_sees_contabilidad() -> None:
    shop = make_shop()
    owner = owner_client(shop)
    _seed_roles(owner)
    _seed_cash_sale(owner)

    exported = owner.get("/api/journal/export", params={"format": "xlsx", "period": "month"})
    assert exported.status_code == 200

    staff = _panel_client(shop, "staff-journal-hist")
    assert staff.get("/api/reports/downloads/history").status_code == 403

    supervisor = _panel_client(shop, "super-journal-hist")
    listed = supervisor.get("/api/reports/downloads/history")
    assert listed.status_code == 200
    assert listed.json()["downloads"][0]["report_id"] == "journal"

    downloaded = supervisor.get(
        "/api/journal/income",
        params={"format": "pdf", "period": "today"},
    )
    assert downloaded.status_code == 200
    newest = supervisor.get("/api/reports/downloads/history").json()["downloads"][0]
    assert newest["report_id"] == "resultado"
    assert newest["format"] == "pdf"
    assert newest["period_id"] == "today"
    assert newest["actor_name"] == "Ana Super"


def test_reportes_history_still_works_alongside_contabilidad() -> None:
    shop = make_shop()
    client = owner_client(shop)
    _seed_cash_sale(client)

    orders = client.get("/api/reports/orders.csv?period=7d")
    assert orders.status_code == 200
    diario = client.get("/api/journal/export", params={"format": "csv", "period": "month"})
    assert diario.status_code == 200

    rows = client.get("/api/reports/downloads/history").json()["downloads"]
    assert [row["report_id"] for row in rows[:2]] == ["journal", "orders"]
    assert rows[1]["period_id"] == "7d"
    assert rows[0]["format"] == "csv"
