"""T8 cash attachment metadata (no binaries in Postgres) — ADR-009."""

from __future__ import annotations

from pathlib import Path

from tests.conftest import make_shop, owner_client


def test_cash_movement_attachment_metadata_and_upload(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("CASH_ATTACHMENTS_DIR", str(tmp_path))
    shop = make_shop()
    client = owner_client(shop)
    client.post("/api/cash/session/open", json={"opening_float": "20"})
    posted = client.post(
        "/api/cash",
        json={
            "direction": "out",
            "amount": "5",
            "reason": "bolsas",
            "category": "gasto",
            "method": "cash",
        },
    )
    assert posted.status_code == 200
    movement_id = posted.json()["id"]

    empty = client.get(f"/api/cash/{movement_id}/attachments")
    assert empty.status_code == 200
    assert empty.json()["attachments"] == []

    upload = client.post(
        f"/api/cash/{movement_id}/attachments",
        files={"file": ("recibo.txt", b"foto de recibo", "text/plain")},
    )
    assert upload.status_code == 200
    body = upload.json()
    assert body["filename"] == "recibo.txt"
    assert body["content_type"] == "text/plain"
    assert body["size_bytes"] == len(b"foto de recibo")
    assert body["id"]
    assert "storage_key" in body
    assert tmp_path.joinpath(body["storage_key"]).is_file()

    listed = client.get(f"/api/cash/{movement_id}/attachments").json()["attachments"]
    assert len(listed) == 1
    assert listed[0]["filename"] == "recibo.txt"

    missing = client.post(
        "/api/cash/00000000-0000-0000-0000-000000000099/attachments",
        files={"file": ("x.txt", b"x", "text/plain")},
    )
    assert missing.status_code == 404
    assert missing.json()["detail"] == "movement_not_found"


def test_cash_attachment_rejects_empty_file(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("CASH_ATTACHMENTS_DIR", str(tmp_path))
    shop = make_shop()
    client = owner_client(shop)
    client.post("/api/cash/session/open", json={"opening_float": "10"})
    movement_id = client.post(
        "/api/cash",
        json={"direction": "out", "amount": "1", "reason": "x", "category": "gasto"},
    ).json()["id"]
    bad = client.post(
        f"/api/cash/{movement_id}/attachments",
        files={"file": ("vacio.txt", b"", "text/plain")},
    )
    assert bad.status_code == 400
    assert bad.json()["detail"] == "empty_file"
