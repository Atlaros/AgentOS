"""Media GET cache headers: private thumb cache + ETag/304 (panel auth unchanged)."""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

from factory_os.domain.media import (
    ORIGINAL_CACHE_MAX_AGE_S,
    THUMB_CACHE_MAX_AGE_S,
    media_cache_headers,
    media_etag_matches,
)
from tests.conftest import make_shop, owner_client

SKU = "h001-M-VP"
PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000a49444154789c63000100000500010d0a2db40000000049454e44ae426082"
)
ASSET = UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")


def test_media_cache_headers_thumb_is_private_long_lived() -> None:
    headers = media_cache_headers(variant="thumb", asset_id=ASSET, size_bytes=1200)
    assert headers["Cache-Control"].startswith("private,")
    assert "max-age=" in headers["Cache-Control"]
    max_age = int(headers["Cache-Control"].split("max-age=", 1)[1].split(",", 1)[0])
    assert max_age >= 86400
    assert "public" not in headers["Cache-Control"]
    assert headers["ETag"].startswith('"') and headers["ETag"].endswith('"')


def test_media_cache_headers_original_is_private_shorter_than_thumb() -> None:
    thumb = media_cache_headers(variant="thumb", asset_id=ASSET, size_bytes=1200)
    original = media_cache_headers(variant="original", asset_id=ASSET, size_bytes=1200)
    thumb_age = int(thumb["Cache-Control"].split("max-age=", 1)[1].split(",", 1)[0])
    original_age = int(original["Cache-Control"].split("max-age=", 1)[1].split(",", 1)[0])
    assert original["Cache-Control"].startswith("private,")
    assert original_age < thumb_age
    assert original["ETag"] != thumb["ETag"]


def test_media_cache_headers_full_alias_is_original() -> None:
    original = media_cache_headers(variant="original", asset_id=ASSET, size_bytes=42)
    full = media_cache_headers(variant=" full ", asset_id=ASSET, size_bytes=42)
    assert full == original
    assert full["Cache-Control"] == f"private, max-age={ORIGINAL_CACHE_MAX_AGE_S}"
    assert full["ETag"] == f'"{ASSET.hex}-original-42"'
    thumb = media_cache_headers(variant="thumb", asset_id=ASSET, size_bytes=42)
    assert thumb["Cache-Control"] == f"private, max-age={THUMB_CACHE_MAX_AGE_S}"
    assert thumb["ETag"] == f'"{ASSET.hex}-thumb-42"'


def test_media_etag_matches_strips_quotes_and_weak_validator() -> None:
    etag = '"abc-thumb-12"'
    assert media_etag_matches(etag, etag)
    assert media_etag_matches('W/"abc-thumb-12"', etag)
    assert media_etag_matches('W/"other", "abc-thumb-12"', etag)
    assert not media_etag_matches(None, etag)
    assert not media_etag_matches("  ", etag)
    assert not media_etag_matches('"other"', etag)


def test_media_cache_headers_rejects_bad_variant() -> None:
    import pytest

    with pytest.raises(ValueError, match="bad_variant"):
        media_cache_headers(variant="tiny", asset_id=ASSET, size_bytes=1)


def test_get_media_thumb_sends_cache_headers_and_supports_304(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("MEDIA_DIR", str(tmp_path))
    monkeypatch.setenv("CATALOG_IMAGES_DIR", str(tmp_path))
    shop = make_shop()
    client = owner_client(shop)

    uploaded = client.post(
        f"/api/catalog/{SKU}/image",
        files={"file": ("one.png", PNG, "image/png")},
    )
    assert uploaded.status_code == 200, uploaded.text
    asset_id = uploaded.json()["asset_id"]

    thumb = client.get(f"/api/media/{asset_id}?variant=thumb")
    assert thumb.status_code == 200
    cache = thumb.headers.get("cache-control") or ""
    assert cache.startswith("private,")
    assert "max-age=" in cache
    assert "public" not in cache
    etag = thumb.headers.get("etag")
    assert etag
    assert len(thumb.content) > 0

    cached = client.get(
        f"/api/media/{asset_id}?variant=thumb",
        headers={"If-None-Match": etag},
    )
    assert cached.status_code == 304
    assert cached.headers.get("etag") == etag
    assert (cached.headers.get("cache-control") or "").startswith("private,")
    assert cached.content in {b"", None} or len(cached.content) == 0


def test_get_media_still_requires_auth(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MEDIA_DIR", str(tmp_path))
    from fastapi.testclient import TestClient

    from factory_os.api.main import create_app
    from tests.conftest import api_settings

    shop = make_shop()
    owner = owner_client(shop)
    uploaded = owner.post(
        f"/api/catalog/{SKU}/image",
        files={"file": ("one.png", PNG, "image/png")},
    )
    assert uploaded.status_code == 200, uploaded.text
    asset_id = uploaded.json()["asset_id"]
    anon = TestClient(create_app(shop, api_settings()))
    assert anon.get(f"/api/media/{asset_id}?variant=thumb").status_code == 401
