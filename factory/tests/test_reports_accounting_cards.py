"""T12 Contabilidad cards + accounting package link on Reportes → Descargas."""

from __future__ import annotations

from urllib.parse import parse_qs, urlencode, urlparse

from tests.conftest import make_shop, owner_client
from tests.test_journal_export_fase_a import _panel_client, _seed_cash_sale

ACCOUNTING_CARD_IDS = (
    "ledger_hechos",
    "journal",
    "mayor",
    "comprobacion",
    "resultado",
    "balance",
)
OPERATIVE_CARD_IDS = ("orders", "payments", "stock")
ALL_CARD_IDS = set(OPERATIVE_CARD_IDS) | set(ACCOUNTING_CARD_IDS)

# Contabilidad engines the Descargas cards must point at (via /api/... for /api/backend).
EXPECTED_PATH_PREFIX = {
    "ledger_hechos": "/api/ledger/export",
    "journal": "/api/journal/export",
    "mayor": "/api/journal/ledger",
    "comprobacion": "/api/journal/trial-balance",
    "resultado": "/api/journal/income",
    "balance": "/api/journal/balance-sheet",
}


def _seed_roles(owner) -> None:
    staff = owner.post(
        "/api/panel/users",
        json={
            "name": "Luis Staff",
            "email": "luis-accounting-cards@taller.local",
            "role": "staff",
            "secret": "staff-accounting-cards",
        },
    )
    assert staff.status_code == 200
    supervisor = owner.post(
        "/api/panel/users",
        json={
            "name": "Ana Super",
            "email": "ana-accounting-cards@taller.local",
            "role": "supervisor",
            "secret": "super-accounting-cards",
        },
    )
    assert supervisor.status_code == 200


def _path_and_query(url: str) -> tuple[str, dict[str, list[str]]]:
    parsed = urlparse(url)
    return parsed.path, parse_qs(parsed.query)


def test_catalog_includes_contabilidad_cards_with_spanish_labels_and_paths() -> None:
    shop = make_shop()
    client = owner_client(shop)
    _seed_cash_sale(client)

    catalog = client.get("/api/reports/catalog?period=month")
    assert catalog.status_code == 200
    body = catalog.json()
    cards = {card["id"]: card for card in body["reports"]}
    assert set(cards) == ALL_CARD_IDS

    for report_id in OPERATIVE_CARD_IDS:
        assert cards[report_id]["downloads"]["csv"].startswith(f"/api/reports/{report_id}")

    for report_id in ACCOUNTING_CARD_IDS:
        card = cards[report_id]
        assert card["label"], report_id
        assert card["description"], report_id
        assert "archivo" not in card["description"].lower()
        assert "archivo" not in card["label"].lower()
        assert card["row_count"] >= 0
        prefix = EXPECTED_PATH_PREFIX[report_id]
        for fmt_key in ("csv", "xlsx"):
            path, query = _path_and_query(card["downloads"][fmt_key])
            assert path == prefix, f"{report_id}.{fmt_key} → {path}"
            assert "format" in query
            assert query.get("period") == ["month"] or ("from" in query and "to" in query)

    # Cash sale in current month → meaningful Contabilidad counts (not fake zeros).
    assert cards["ledger_hechos"]["row_count"] >= 1
    assert cards["journal"]["row_count"] >= 1
    assert cards["mayor"]["row_count"] >= 1
    assert cards["comprobacion"]["row_count"] >= 1


def test_accounting_card_download_paths_hit_contabilidad_engines() -> None:
    shop = make_shop()
    client = owner_client(shop)
    _seed_cash_sale(client)

    catalog = client.get("/api/reports/catalog?period=month")
    cards = {card["id"]: card for card in catalog.json()["reports"]}

    diario = cards["journal"]["downloads"]["xlsx"]
    path, query = _path_and_query(diario)
    assert path == "/api/journal/export"
    assert query["format"] == ["xlsx"]

    response = client.get(diario)
    assert response.status_code == 200
    assert "spreadsheetml" in response.headers.get("content-type", "")

    hechos = cards["ledger_hechos"]["downloads"]["csv"]
    response = client.get(hechos)
    assert response.status_code == 200
    assert "text/csv" in response.headers.get("content-type", "")

    mayor = cards["mayor"]["downloads"]["xlsx"]
    response = client.get(mayor)
    assert response.status_code == 200


def test_staff_forbidden_on_catalog_and_accounting_package_supervisor_ok() -> None:
    shop = make_shop()
    owner = owner_client(shop)
    _seed_roles(owner)
    _seed_cash_sale(owner)

    staff = _panel_client(shop, "staff-accounting-cards")
    assert staff.get("/api/reports/catalog?period=month").status_code == 403
    assert staff.get(
        "/api/reports/accounting-package",
        params={"period": "month", "format": "xlsx"},
    ).status_code == 403

    supervisor = _panel_client(shop, "super-accounting-cards")
    catalog = supervisor.get("/api/reports/catalog?period=month")
    assert catalog.status_code == 200
    assert set(card["id"] for card in catalog.json()["reports"]) == ALL_CARD_IDS
    package = supervisor.get(
        "/api/reports/accounting-package",
        params={"period": "month", "format": "xlsx"},
    )
    assert package.status_code == 200


def test_catalog_range_maps_to_contabilidad_from_to() -> None:
    shop = make_shop()
    client = owner_client(shop)
    query = urlencode(
        {
            "period": "range",
            "date_from": "2026-11-01T00:00:00+00:00",
            "date_to": "2026-11-08T00:00:00+00:00",
        }
    )
    catalog = client.get(f"/api/reports/catalog?{query}")
    assert catalog.status_code == 200
    cards = {card["id"]: card for card in catalog.json()["reports"]}
    path, params = _path_and_query(cards["journal"]["downloads"]["xlsx"])
    assert path == "/api/journal/export"
    assert params["format"] == ["xlsx"]
    assert params["from"] == ["2026-11-01"]
    assert params["to"] == ["2026-11-07"]
    assert "period" not in params
