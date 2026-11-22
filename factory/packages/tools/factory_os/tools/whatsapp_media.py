"""Download WhatsApp Cloud API media bytes (ADR-015 Fase C)."""

from __future__ import annotations

import logging
from typing import Callable, Protocol

logger = logging.getLogger(__name__)

MediaDownloader = Callable[..., tuple[bytes, str]]


class SupportsMetaDownload(Protocol):
    def __call__(
        self, media_id: str, *, access_token: str = "", max_attempts: int = 3
    ) -> tuple[bytes, str]: ...


def download_meta_media(
    media_id: str, *, access_token: str = "", max_attempts: int = 3
) -> tuple[bytes, str]:
    """GET Graph media id → temporary URL → bytes. Returns (bytes, mime)."""
    import httpx

    mid = (media_id or "").strip()
    if not mid:
        raise ValueError("missing_media_id")
    token = (access_token or "").strip()
    if not token:
        raise ValueError("missing_access_token")

    last_exc: Exception | None = None
    for attempt in range(1, max(1, int(max_attempts)) + 1):
        try:
            meta = httpx.get(
                f"https://graph.facebook.com/v21.0/{mid}",
                headers={"Authorization": f"Bearer {token}"},
                timeout=15.0,
            )
            meta.raise_for_status()
            payload = meta.json() or {}
            url = str(payload.get("url") or "").strip()
            mime = str(payload.get("mime_type") or "").strip() or "application/octet-stream"
            if not url:
                raise RuntimeError("meta_media_missing_url")
            body = httpx.get(
                url,
                headers={"Authorization": f"Bearer {token}"},
                timeout=60.0,
            )
            body.raise_for_status()
            data = body.content or b""
            if not data:
                raise RuntimeError("meta_media_empty")
            return data, mime
        except Exception as exc:
            last_exc = exc
            logger.warning(
                "whatsapp media download failed attempt=%s media_id=%s",
                attempt,
                mid[:24],
                exc_info=False,
            )
    assert last_exc is not None
    raise last_exc
