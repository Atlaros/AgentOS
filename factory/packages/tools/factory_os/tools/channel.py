from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from factory_os.tools.qr_media import decode_qr_image, image_link, looks_like_image_payload


class Channel(Protocol):
    def send_text(self, wa_number: str, text: str) -> None: ...

    def notify_typing(self, wa_number: str, message_id: str | None = None) -> None: ...

    def send_image(
        self,
        wa_number: str,
        *,
        content: bytes | None = None,
        mime: str = "image/png",
        filename: str = "qr.png",
        link: str | None = None,
        caption: str = "",
    ) -> None: ...

    def send_reply_buttons(
        self,
        wa_number: str,
        body: str,
        buttons: list[tuple[str, str]],
    ) -> None: ...

    def send_location_request(self, wa_number: str, body: str) -> None: ...

    def send_document(
        self,
        wa_number: str,
        *,
        content: bytes | None = None,
        mime: str = "application/pdf",
        filename: str = "file.pdf",
        caption: str = "",
    ) -> None: ...

    def send_template(
        self,
        wa_number: str,
        *,
        name: str,
        language: str,
        body_parameters: list[str] | None = None,
    ) -> None: ...


class FakeChannel:
    """Records outbound WhatsApp. Used in tests and when META tokens are absent."""

    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []
        self.images: list[dict[str, Any]] = []
        self.documents: list[dict[str, Any]] = []
        self.buttons: list[dict[str, Any]] = []
        self.location_requests: list[dict[str, Any]] = []
        self.typing: list[tuple[str, str | None]] = []
        self.templates: list[dict[str, Any]] = []

    def send_text(self, wa_number: str, text: str) -> None:
        self.sent.append((wa_number, text))

    def notify_typing(self, wa_number: str, message_id: str | None = None) -> None:
        self.typing.append((wa_number, message_id))

    def send_image(
        self,
        wa_number: str,
        *,
        content: bytes | None = None,
        mime: str = "image/png",
        filename: str = "qr.png",
        link: str | None = None,
        caption: str = "",
    ) -> None:
        self.images.append(
            {
                "wa_number": wa_number,
                "mime": mime,
                "filename": filename,
                "link": link,
                "caption": caption,
                "size": len(content or b""),
            }
        )

    def send_document(
        self,
        wa_number: str,
        *,
        content: bytes | None = None,
        mime: str = "application/pdf",
        filename: str = "file.pdf",
        caption: str = "",
    ) -> None:
        self.documents.append(
            {
                "wa_number": wa_number,
                "mime": mime,
                "filename": filename,
                "caption": caption,
                "size": len(content or b""),
            }
        )

    def send_reply_buttons(
        self,
        wa_number: str,
        body: str,
        buttons: list[tuple[str, str]],
    ) -> None:
        self.buttons.append({"wa_number": wa_number, "body": body, "buttons": list(buttons)})
        # Also mirror body as text so inbox/tests that only watch `sent` still see it.
        self.sent.append((wa_number, body))

    def send_location_request(self, wa_number: str, body: str) -> None:
        self.location_requests.append({"wa_number": wa_number, "body": body})
        self.sent.append((wa_number, body))

    def send_template(
        self,
        wa_number: str,
        *,
        name: str,
        language: str,
        body_parameters: list[str] | None = None,
    ) -> None:
        params = list(body_parameters or [])
        self.templates.append(
            {
                "wa_number": wa_number,
                "name": name,
                "language": language,
                "body_parameters": params,
            }
        )
        summary = params[0] if params else f"template:{name}"
        self.sent.append((wa_number, f"[template {name}] {summary}"))


class MetaChannel:
    def __init__(self, access_token: str, phone_number_id: str) -> None:
        self.access_token = access_token
        self.phone_number_id = phone_number_id

    def send_text(self, wa_number: str, text: str) -> None:
        import httpx

        url = f"https://graph.facebook.com/v21.0/{self.phone_number_id}/messages"
        response = httpx.post(
            url,
            headers={"Authorization": f"Bearer {self.access_token}"},
            json={
                "messaging_product": "whatsapp",
                "to": wa_number,
                "type": "text",
                "text": {"body": text},
            },
            timeout=10.0,
        )
        response.raise_for_status()

    def notify_typing(self, wa_number: str, message_id: str | None = None) -> None:
        """Mark read + typing indicator (covers LLM latency up to ~25s)."""
        _ = wa_number
        if not message_id:
            return
        import httpx

        url = f"https://graph.facebook.com/v21.0/{self.phone_number_id}/messages"
        try:
            httpx.post(
                url,
                headers={"Authorization": f"Bearer {self.access_token}"},
                json={
                    "messaging_product": "whatsapp",
                    "status": "read",
                    "message_id": message_id,
                    "typing_indicator": {"type": "text"},
                },
                timeout=5.0,
            )
        except Exception:
            return

    def send_image(
        self,
        wa_number: str,
        *,
        content: bytes | None = None,
        mime: str = "image/png",
        filename: str = "qr.png",
        link: str | None = None,
        caption: str = "",
    ) -> None:
        import httpx

        url = f"https://graph.facebook.com/v21.0/{self.phone_number_id}/messages"
        image: dict[str, str] = {}
        if caption:
            image["caption"] = caption[:1024]
        if link:
            image["link"] = link
        elif content:
            media_id = self._upload_media(content, mime=mime, filename=filename)
            image["id"] = media_id
        else:
            return
        response = httpx.post(
            url,
            headers={"Authorization": f"Bearer {self.access_token}"},
            json={
                "messaging_product": "whatsapp",
                "to": wa_number,
                "type": "image",
                "image": image,
            },
            timeout=30.0,
        )
        response.raise_for_status()

    def send_document(
        self,
        wa_number: str,
        *,
        content: bytes | None = None,
        mime: str = "application/pdf",
        filename: str = "file.pdf",
        caption: str = "",
    ) -> None:
        import httpx

        if not content:
            return
        media_id = self._upload_media(content, mime=mime, filename=filename)
        document: dict[str, str] = {"id": media_id, "filename": filename[:240] or "file.pdf"}
        if caption:
            document["caption"] = caption[:1024]
        url = f"https://graph.facebook.com/v21.0/{self.phone_number_id}/messages"
        response = httpx.post(
            url,
            headers={"Authorization": f"Bearer {self.access_token}"},
            json={
                "messaging_product": "whatsapp",
                "to": wa_number,
                "type": "document",
                "document": document,
            },
            timeout=30.0,
        )
        response.raise_for_status()

    def send_location_request(self, wa_number: str, body: str) -> None:
        """Native WhatsApp location request (customer taps to share Maps pin)."""
        import httpx

        url = f"https://graph.facebook.com/v21.0/{self.phone_number_id}/messages"
        response = httpx.post(
            url,
            headers={"Authorization": f"Bearer {self.access_token}"},
            json={
                "messaging_product": "whatsapp",
                "to": wa_number,
                "type": "interactive",
                "interactive": {
                    "type": "location_request_message",
                    "body": {"text": (body or "Compartí tu ubicación para el envío.")[:1024]},
                    "action": {"name": "send_location"},
                },
            },
            timeout=10.0,
        )
        response.raise_for_status()

    def send_reply_buttons(
        self,
        wa_number: str,
        body: str,
        buttons: list[tuple[str, str]],
    ) -> None:
        """Up to 3 reply buttons. Each item is (id, title≤20)."""
        import httpx

        action_buttons = []
        for button_id, title in buttons[:3]:
            action_buttons.append(
                {
                    "type": "reply",
                    "reply": {"id": str(button_id)[:256], "title": str(title)[:20]},
                }
            )
        if not action_buttons:
            self.send_text(wa_number, body)
            return
        url = f"https://graph.facebook.com/v21.0/{self.phone_number_id}/messages"
        response = httpx.post(
            url,
            headers={"Authorization": f"Bearer {self.access_token}"},
            json={
                "messaging_product": "whatsapp",
                "to": wa_number,
                "type": "interactive",
                "interactive": {
                    "type": "button",
                    "body": {"text": body[:1024]},
                    "action": {"buttons": action_buttons},
                },
            },
            timeout=10.0,
        )
        response.raise_for_status()

    def send_template(
        self,
        wa_number: str,
        *,
        name: str,
        language: str,
        body_parameters: list[str] | None = None,
    ) -> None:
        import httpx

        template: dict[str, Any] = {
            "name": name,
            "language": {"code": language},
        }
        params = [str(part) for part in (body_parameters or [])]
        if params:
            template["components"] = [
                {
                    "type": "body",
                    "parameters": [{"type": "text", "text": part[:1024]} for part in params],
                }
            ]
        url = f"https://graph.facebook.com/v21.0/{self.phone_number_id}/messages"
        response = httpx.post(
            url,
            headers={"Authorization": f"Bearer {self.access_token}"},
            json={
                "messaging_product": "whatsapp",
                "to": wa_number,
                "type": "template",
                "template": template,
            },
            timeout=15.0,
        )
        response.raise_for_status()

    def _upload_media(self, content: bytes, *, mime: str, filename: str) -> str:
        import httpx

        url = f"https://graph.facebook.com/v21.0/{self.phone_number_id}/media"
        response = httpx.post(
            url,
            headers={"Authorization": f"Bearer {self.access_token}"},
            data={"messaging_product": "whatsapp", "type": mime},
            files={"file": (filename, content, mime)},
            timeout=30.0,
        )
        response.raise_for_status()
        media_id = str((response.json() or {}).get("id") or "").strip()
        if not media_id:
            raise RuntimeError("meta_media_upload_missing_id")
        return media_id


@dataclass(frozen=True)
class InboundMessage:
    wa_number: str
    text: str
    message_id: str | None = None
    media_id: str | None = None
    media_kind: str | None = None
    mime: str | None = None
    filename: str | None = None
    caption: str | None = None


# Button ids → customer text the runtime already understands.
_BUTTON_TEXT = {
    "pay_check": "ya pagué",
    "pay_resend_qr": "reenviame el qr",
    "pay_share_location": "comparto mi ubicacion",
}

_RECEIPT_DEFAULT = "te envío el comprobante de pago"
_AUDIO_DEFAULT = "te envié un audio"
_VIDEO_DEFAULT = "te envié un video"


def _media_fields(
    *,
    media_id: str | None,
    media_kind: str,
    mime: str | None,
    filename: str | None,
    caption: str | None,
) -> dict[str, str | None]:
    return {
        "media_id": (media_id or "").strip() or None,
        "media_kind": media_kind,
        "mime": (mime or "").strip() or None,
        "filename": (filename or "").strip() or None,
        "caption": (caption or "").strip() or None,
    }


def parse_inbound(payload: dict[str, Any]) -> list[InboundMessage]:
    """Return inbound texts. Accepts Meta Cloud API or a one-message fake body."""
    simple_text = payload.get("text")
    if payload.get("from") and isinstance(simple_text, str) and simple_text.strip():
        mid = str(payload.get("id") or payload.get("message_id") or "").strip() or None
        return [InboundMessage(str(payload["from"]), simple_text.strip(), mid)]

    out: list[InboundMessage] = []
    for entry in payload.get("entry") or []:
        for change in entry.get("changes") or []:
            value = change.get("value") or {}
            for msg in value.get("messages") or []:
                sender = str(msg.get("from") or "").strip()
                mid = str(msg.get("id") or "").strip() or None
                if not sender:
                    continue
                msg_type = str(msg.get("type") or "text")
                if msg_type == "text":
                    body = ((msg.get("text") or {}).get("body") or "").strip()
                    if body:
                        out.append(InboundMessage(sender, body, mid))
                    continue
                if msg_type == "interactive":
                    interactive = msg.get("interactive") or {}
                    reply = interactive.get("button_reply") or interactive.get("list_reply") or {}
                    button_id = str(reply.get("id") or "").strip()
                    title = str(reply.get("title") or "").strip()
                    mapped = _BUTTON_TEXT.get(button_id) or title
                    if mapped:
                        out.append(InboundMessage(sender, mapped, mid))
                    continue
                if msg_type == "image":
                    # Receipt photo → Cobros READ payment.status (never confirms from media).
                    image = msg.get("image") or {}
                    caption = str(image.get("caption") or "").strip()
                    body = caption if caption else _RECEIPT_DEFAULT
                    fields = _media_fields(
                        media_id=str(image.get("id") or ""),
                        media_kind="image",
                        mime=str(image.get("mime_type") or ""),
                        filename=None,
                        caption=caption or None,
                    )
                    out.append(InboundMessage(sender, body, mid, **fields))
                    continue
                if msg_type == "document":
                    doc = msg.get("document") or {}
                    filename = str(doc.get("filename") or "").strip() or None
                    caption = str(doc.get("caption") or "").strip()
                    body = caption or filename or _RECEIPT_DEFAULT
                    fields = _media_fields(
                        media_id=str(doc.get("id") or ""),
                        media_kind="document",
                        mime=str(doc.get("mime_type") or ""),
                        filename=filename,
                        caption=caption or None,
                    )
                    out.append(InboundMessage(sender, body, mid, **fields))
                    continue
                if msg_type == "audio":
                    audio = msg.get("audio") or {}
                    fields = _media_fields(
                        media_id=str(audio.get("id") or ""),
                        media_kind="audio",
                        mime=str(audio.get("mime_type") or ""),
                        filename=None,
                        caption=None,
                    )
                    out.append(InboundMessage(sender, _AUDIO_DEFAULT, mid, **fields))
                    continue
                if msg_type == "video":
                    video = msg.get("video") or {}
                    caption = str(video.get("caption") or "").strip()
                    body = caption if caption else _VIDEO_DEFAULT
                    fields = _media_fields(
                        media_id=str(video.get("id") or ""),
                        media_kind="video",
                        mime=str(video.get("mime_type") or ""),
                        filename=None,
                        caption=caption or None,
                    )
                    out.append(InboundMessage(sender, body, mid, **fields))
                    continue
                if msg_type == "location":
                    loc = msg.get("location") or {}
                    lat = loc.get("latitude")
                    lon = loc.get("longitude")
                    name = str(loc.get("name") or loc.get("address") or "").strip()
                    if lat is not None and lon is not None:
                        label = name or "ubicacion"
                        out.append(
                            InboundMessage(
                                sender,
                                f"mi ubicacion maps: {lat},{lon} ({label})",
                                mid,
                            )
                        )
    return out


def owner_alert_text(
    *,
    name: str | None,
    wa_number: str,
    reason: str,
    inbox_url: str,
    conversation_id: str,
) -> str:
    who = name or "sin nombre"
    return (
        f"Closet: Adri necesita tu ayuda.\n"
        f"Cliente: {who}\n"
        f"WhatsApp: {wa_number}\n"
        f"Motivo: {reason}\n"
        f"Abrí el chat: {inbox_url}?c={conversation_id}"
    )


def send_text_to_owners(channel: Channel, numbers: list[str], text: str) -> int:
    """Send one text to each owner number. One failure does not stop the rest."""
    sent = 0
    for number in numbers:
        target = number.strip()
        if not target:
            continue
        try:
            channel.send_text(target, text)
        except Exception:
            continue
        sent += 1
    return sent


def send_payment_qr(
    channel: Channel,
    wa_number: str,
    qr_payload: str,
    *,
    amount: str = "",
    currency: str = "BOB",
) -> bool:
    """Send QR as WhatsApp image when payload is Baneco image; return True if sent."""
    caption = f"QR para pagar {amount} {currency}".strip() if amount else "QR para pagar"
    link = image_link(qr_payload)
    if link:
        channel.send_image(wa_number, link=link, caption=caption)
        return True
    decoded = decode_qr_image(qr_payload)
    if decoded is None:
        return False
    channel.send_image(
        wa_number,
        content=decoded.content,
        mime=decoded.mime,
        filename=decoded.filename,
        caption=caption,
    )
    return True


def payment_qr_buttons() -> list[tuple[str, str]]:
    return [
        ("pay_check", "Ya transferí"),
        ("pay_resend_qr", "Reenviar QR"),
    ]


# Re-export helpers used by Cobros / tests.
__all__ = [
    "Channel",
    "FakeChannel",
    "MetaChannel",
    "InboundMessage",
    "parse_inbound",
    "owner_alert_text",
    "send_payment_qr",
    "payment_qr_buttons",
    "looks_like_image_payload",
]
