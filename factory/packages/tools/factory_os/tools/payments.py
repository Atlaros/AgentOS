"""Payment adapters: Fake (pytest/pilot) and Baneco Api Market (live, env-gated).

Customer text never confirms. Only webhook/status from the adapter.
Baneco protocol: encrypt → authenticate → generateQR / statusQR / notifyPaymentQR.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, Protocol
from urllib.parse import urlencode
from uuid import uuid4

from factory_os.domain.models import PaymentStatus


@dataclass(frozen=True)
class QrIssue:
    provider_ref: str
    qr_payload: str
    expires_at: datetime | None = None


@dataclass(frozen=True)
class WebhookEvent:
    provider_reference: str
    state: PaymentStatus
    event_id: str


class PaymentProvider(Protocol):
    name: str

    def create_qr(self, order_id: str, amount: Decimal, currency: str) -> QrIssue: ...

    def status(self, provider_ref: str) -> PaymentStatus: ...

    def parse_webhook(self, raw_payload: bytes, headers: dict[str, str]) -> WebhookEvent: ...


class FakePaymentProvider:
    """Pilot stand-in. Confirmations from confirm() or signed fake webhook."""

    name = "fake"

    def __init__(self, *, webhook_secret: str = "fake-webhook-secret") -> None:
        self._issued: dict[str, tuple[Decimal, str, datetime | None]] = {}
        self._confirmed: set[str] = set()
        self.webhook_secret = webhook_secret

    def create_qr(self, order_id: str, amount: Decimal, currency: str) -> QrIssue:
        ref = f"pay-{order_id[:8]}-{uuid4().hex[:6]}"
        expires = datetime.now(UTC) + timedelta(minutes=30)
        self._issued[ref] = (amount, currency, expires)
        return QrIssue(
            provider_ref=ref,
            qr_payload=f"QR:{ref}:{amount} {currency}",
            expires_at=expires,
        )

    def status(self, provider_ref: str) -> PaymentStatus:
        if provider_ref in self._confirmed:
            return PaymentStatus.CONFIRMED
        issued = self._issued.get(provider_ref)
        if issued is None:
            return PaymentStatus.UNKNOWN
        _amount, _currency, expires = issued
        if expires and datetime.now(UTC) > expires:
            return PaymentStatus.EXPIRED
        return PaymentStatus.PENDING

    def confirm(self, provider_ref: str) -> None:
        self._confirmed.add(provider_ref)

    def parse_webhook(self, raw_payload: bytes, headers: dict[str, str]) -> WebhookEvent:
        sig = headers.get("x-fake-signature") or headers.get("X-Fake-Signature") or ""
        expected = hmac.new(self.webhook_secret.encode(), raw_payload, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected):
            raise ValueError("fake_webhook_bad_signature")
        data = json.loads(raw_payload.decode("utf-8"))
        event_id = str(data.get("event_id") or "").strip()
        ref = str(data.get("provider_reference") or data.get("provider_ref") or "").strip()
        state_raw = str(data.get("state") or "").strip().lower()
        if not event_id or not ref:
            raise ValueError("fake_webhook_incomplete")
        state = {
            "confirmed": PaymentStatus.CONFIRMED,
            "pending": PaymentStatus.PENDING,
            "expired": PaymentStatus.EXPIRED,
            "failed": PaymentStatus.FAILED,
        }.get(state_raw)
        if state is None:
            raise ValueError("fake_webhook_bad_state")
        if state is PaymentStatus.CONFIRMED:
            self.confirm(ref)
        return WebhookEvent(provider_reference=ref, state=state, event_id=event_id)


def _response_code(data: dict[str, Any]) -> int:
    raw = data.get("responseCode", data.get("response_code"))
    if raw is None:
        return -1
    try:
        return int(raw)
    except (TypeError, ValueError):
        return -1


def to_baneco_wire_currency(currency: str) -> str:
    ccy = currency.strip().upper()
    if ccy == "BOB":
        return "BOB"
    if ccy in {"USD", "USB"}:
        return "USB"
    raise ValueError("baneco_currency_unsupported")


def merchant_transaction_id(order_id: str) -> str:
    """≤30 merchant ref for generateQR."""
    raw = order_id.replace("-", "")
    return f"ac{raw[:28]}"[:30]


@dataclass
class BanecoClient:
    """Baneco Api Market: encrypt → authenticate → qrsimple. Secrets never logged."""

    base_url: str
    username: str
    password: str
    aes_key: str
    account_credit: str
    timeout_s: float = 30.0
    qr_due_hours: int = 24
    http_retry_attempts: int = 3
    _token: str | None = field(default=None, init=False, repr=False)
    http_calls: int = field(default=0, init=False)

    def _root(self) -> str:
        return self.base_url.rstrip("/")

    def encrypt(self, text: str) -> str:
        query = urlencode({"text": text, "aesKey": self.aes_key})
        url = f"{self._root()}/api/authentication/encrypt?{query}"
        return self._request_text("GET", url).strip().strip('"')

    def authenticate(self) -> str:
        cipher = self.encrypt(self.password)
        data = self._request_json(
            "POST",
            f"{self._root()}/api/authentication/authenticate",
            json_body={"userName": self.username, "password": cipher},
            auth=False,
        )
        if _response_code(data) != 0:
            raise RuntimeError("baneco_authenticate_failed")
        token = str(data.get("token") or "").strip()
        if not token:
            raise RuntimeError("baneco_token_missing")
        self._token = token
        return token

    def bearer(self) -> str:
        if self._token:
            return self._token
        return self.authenticate()

    def generate_qr(
        self,
        *,
        transaction_id: str,
        amount: Decimal,
        currency: str,
        description: str | None = None,
    ) -> dict[str, Any]:
        txn = transaction_id.strip()
        if not txn or len(txn) > 30:
            raise ValueError("baneco_transaction_id_invalid")
        wire_ccy = to_baneco_wire_currency(currency)
        account_cipher = self.encrypt(self.account_credit)
        due = (datetime.now(UTC) + timedelta(hours=max(1, self.qr_due_hours))).date()
        body: dict[str, Any] = {
            "transactionId": txn,
            "accountCredit": account_cipher,
            "currency": wire_ccy,
            "amount": float(amount.quantize(Decimal("0.01"))),
            "dueDate": due.isoformat(),
            "singleUse": True,
            "modifyAmount": False,
        }
        if description:
            body["description"] = description[:200]
        data = self._request_json(
            "POST",
            f"{self._root()}/api/qrsimple/generateQR",
            json_body=body,
            auth=True,
        )
        if _response_code(data) != 0:
            raise RuntimeError("baneco_generate_qr_failed")
        qr_id = str(data.get("qrId") or "").strip()
        qr_image = str(data.get("qrImage") or "").strip()
        if not qr_id or not qr_image:
            raise RuntimeError("baneco_generate_qr_incomplete")
        return {"qrId": qr_id, "qrImage": qr_image, "dueDate": due.isoformat(), "raw": data}

    def status_qr(self, *, qr_id: str) -> dict[str, Any]:
        data = self._request_json(
            "GET",
            f"{self._root()}/api/qrsimple/statusQR",
            json_body={"qrId": qr_id},
            auth=True,
        )
        if _response_code(data) != 0:
            raise RuntimeError("baneco_status_qr_failed")
        return data

    def _request_text(self, method: str, url: str) -> str:
        return self._send(method, url, json_body=None, auth=False).text

    def _request_json(
        self,
        method: str,
        url: str,
        *,
        json_body: dict[str, Any] | None,
        auth: bool,
    ) -> dict[str, Any]:
        response = self._send(method, url, json_body=json_body, auth=auth)
        try:
            data = response.json()
        except json.JSONDecodeError as exc:
            raise RuntimeError("baneco_invalid_json") from exc
        if not isinstance(data, dict):
            raise RuntimeError("baneco_invalid_payload")
        return data

    def _send(
        self,
        method: str,
        url: str,
        *,
        json_body: dict[str, Any] | None,
        auth: bool,
    ):
        import httpx

        headers: dict[str, str] = {"Accept": "application/json"}
        if auth:
            headers["Authorization"] = f"Bearer {self.bearer()}"
        if json_body is not None:
            headers["Content-Type"] = "application/json"
        attempts = max(1, self.http_retry_attempts)
        last_exc: Exception | None = None
        with httpx.Client(timeout=self.timeout_s) as client:
            for attempt in range(attempts):
                try:
                    self.http_calls += 1
                    response = client.request(
                        method,
                        url,
                        headers=headers,
                        content=json.dumps(json_body).encode() if json_body is not None else None,
                    )
                    if response.status_code == 401 and auth and attempt + 1 < attempts:
                        self._token = None
                        headers["Authorization"] = f"Bearer {self.authenticate()}"
                        continue
                    if response.status_code >= 500 and attempt + 1 < attempts:
                        continue
                    if response.status_code >= 400:
                        raise RuntimeError(f"baneco_http_{response.status_code}")
                    return response
                except httpx.TimeoutException as exc:
                    last_exc = exc
                    if attempt + 1 >= attempts:
                        raise RuntimeError("baneco_timeout") from exc
                except httpx.TransportError as exc:
                    last_exc = exc
                    if attempt + 1 >= attempts:
                        raise RuntimeError("baneco_transport") from exc
        raise RuntimeError("baneco_unavailable") from last_exc


class BanecoPaymentProvider:
    """Baneco QR Simple. Live when ENABLE_LIVE_PAYMENTS + BANECO_* set.

    provider_ref = qrId. Confirmation via statusQR (code 1) or notifyPaymentQR.
    """

    name = "baneco"

    def __init__(
        self,
        *,
        base_url: str,
        username: str,
        password: str,
        aes_key: str,
        account_credit: str = "",
        qr_due_hours: int = 24,
        notify_shared_secret: str = "",
        client: BanecoClient | None = None,
        generate_fn=None,
        status_fn=None,
    ) -> None:
        self.aes_key = aes_key
        self.notify_shared_secret = notify_shared_secret.strip()
        self.qr_due_hours = max(1, qr_due_hours)
        self._generate_fn = generate_fn
        self._status_fn = status_fn
        self._client = client or BanecoClient(
            base_url=base_url,
            username=username,
            password=password,
            aes_key=aes_key,
            account_credit=account_credit,
            qr_due_hours=self.qr_due_hours,
        )
        self._issued: dict[str, PaymentStatus] = {}

    def create_qr(self, order_id: str, amount: Decimal, currency: str) -> QrIssue:
        txn = merchant_transaction_id(order_id)
        if self._generate_fn is not None:
            created = self._generate_fn(txn, amount, currency)
        else:
            created = self._client.generate_qr(
                transaction_id=txn,
                amount=amount,
                currency=currency,
                description=f"order:{order_id[:36]}",
            )
        qr_id = str(created.get("qrId") or "").strip()
        qr_image = str(created.get("qrImage") or "").strip()
        if not qr_id or not qr_image:
            raise RuntimeError("baneco_create_qr_incomplete")
        expires = datetime.now(UTC) + timedelta(hours=self.qr_due_hours)
        self._issued[qr_id] = PaymentStatus.PENDING
        return QrIssue(provider_ref=qr_id, qr_payload=qr_image, expires_at=expires)

    def status(self, provider_ref: str) -> PaymentStatus:
        if self._status_fn is not None:
            data = self._status_fn(provider_ref)
        else:
            data = self._client.status_qr(qr_id=provider_ref)
        mapped = _map_status_qr(data)
        self._issued[provider_ref] = mapped
        return mapped

    def parse_webhook(self, raw_payload: bytes, headers: dict[str, str]) -> WebhookEvent:
        """Baneco notifyPaymentQR. Optional shared secret; no HMAC in bank docs."""
        if self.notify_shared_secret:
            got = (
                headers.get("x-baneco-notify-secret")
                or headers.get("X-Baneco-Notify-Secret")
                or ""
            ).strip()
            if not hmac.compare_digest(got, self.notify_shared_secret):
                raise ValueError("baneco_webhook_unauthorized")

        data = json.loads(raw_payload.decode("utf-8"))
        payment = data.get("Payment") or data.get("payment") or data
        if not isinstance(payment, dict):
            raise ValueError("baneco_webhook_incomplete")
        qr_id = str(payment.get("qrId") or data.get("qrId") or "").strip()
        txn = str(payment.get("transactionId") or data.get("transactionId") or "na").strip()
        if not qr_id:
            raise ValueError("baneco_webhook_incomplete")
        event_id = f"baneco-notify:{qr_id}:{txn}"
        # statusQR is authority. Fixture-only generate mock accepts notify as confirmed.
        if self._generate_fn is not None and self._status_fn is None:
            state = PaymentStatus.CONFIRMED
        else:
            try:
                state = self.status(qr_id)
            except Exception as exc:
                raise ValueError("baneco_webhook_status_unavailable") from exc
        self._issued[qr_id] = state
        return WebhookEvent(provider_reference=qr_id, state=state, event_id=event_id)


def _map_status_qr(data: dict[str, Any]) -> PaymentStatus:
    status_code = data.get("statusQRCode", data.get("statusQrCode"))
    try:
        code = int(status_code)
    except (TypeError, ValueError):
        code = -1
    if code == 1:
        return PaymentStatus.CONFIRMED
    if code in {0, 2}:
        return PaymentStatus.PENDING
    if code in {3, 4}:
        return PaymentStatus.EXPIRED
    return PaymentStatus.UNKNOWN


def live_payments_enabled() -> bool:
    return (os.environ.get("ENABLE_LIVE_PAYMENTS") or "").strip().lower() in {
        "1",
        "true",
        "yes",
    }


def build_payment_provider() -> FakePaymentProvider | BanecoPaymentProvider:
    """Factory: Baneco only when live flag + credentials; else fake."""
    provider = (
        os.environ.get("QR_PROVIDER")
        or os.environ.get("LIVE_QR_PROVIDER")
        or os.environ.get("BANK_TX_PROVIDER")
        or os.environ.get("LIVE_BANK_PROVIDER")
        or "fake"
    ).strip().lower()
    if provider == "baneco" and live_payments_enabled():
        base = (os.environ.get("BANECO_API_BASE_URL") or "").strip()
        user = (os.environ.get("BANECO_USERNAME") or "").strip()
        password = (os.environ.get("BANECO_PASSWORD") or "").strip()
        key = (os.environ.get("BANECO_AES_KEY") or "").strip()
        account = (os.environ.get("BANECO_ACCOUNT_CREDIT") or "").strip()
        if base and user and password and key and account:
            due_raw = (os.environ.get("BANECO_QR_DUE_HOURS") or "24").strip()
            try:
                due = int(due_raw)
            except ValueError:
                due = 24
            return BanecoPaymentProvider(
                base_url=base,
                username=user,
                password=password,
                aes_key=key,
                account_credit=account,
                qr_due_hours=due,
                notify_shared_secret=(os.environ.get("BANECO_NOTIFY_SHARED_SECRET") or "").strip(),
            )
    return FakePaymentProvider()
