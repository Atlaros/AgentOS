"""WhatsApp outbound helpers: detect Baneco QR image payloads."""

from __future__ import annotations

import base64
import re
from dataclasses import dataclass

_DATA_URL = re.compile(r"^data:(image/(?:png|jpeg|jpg));base64,(.+)$", re.I | re.S)


@dataclass(frozen=True)
class DecodedImage:
    content: bytes
    mime: str
    filename: str


def looks_like_image_payload(raw: str) -> bool:
    text = (raw or "").strip()
    if not text or text.startswith("QR:"):
        return False
    if text.startswith("http://") or text.startswith("https://"):
        return True
    if _DATA_URL.match(text):
        return True
    # Baneco returns bare base64 PNG/JPEG.
    if text.startswith("iVBOR") or text.startswith("/9j/"):
        return True
    return False


def decode_qr_image(raw: str) -> DecodedImage | None:
    """Return PNG/JPEG bytes when payload is an image; None for fake text QR refs."""
    text = (raw or "").strip()
    if not text or text.startswith("QR:"):
        return None
    if text.startswith("http://") or text.startswith("https://"):
        return None  # Meta can use link; handled separately
    match = _DATA_URL.match(text)
    if match:
        mime = match.group(1).lower().replace("jpg", "jpeg")
        try:
            content = base64.b64decode(match.group(2), validate=False)
        except Exception:
            return None
        ext = "jpg" if "jpeg" in mime else "png"
        return DecodedImage(content=content, mime=mime, filename=f"qr.{ext}")
    if text.startswith("iVBOR"):
        try:
            content = base64.b64decode(text, validate=False)
        except Exception:
            return None
        return DecodedImage(content=content, mime="image/png", filename="qr.png")
    if text.startswith("/9j/"):
        try:
            content = base64.b64decode(text, validate=False)
        except Exception:
            return None
        return DecodedImage(content=content, mime="image/jpeg", filename="qr.jpg")
    return None


def image_link(raw: str) -> str | None:
    text = (raw or "").strip()
    if text.startswith("http://") or text.startswith("https://"):
        return text
    return None
