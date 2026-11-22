"""Registry of provisioned businesses for the operator console.

Without a database URL the list is process memory. With a URL it is the
tenants table, so a restart still shows the businesses.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any
from uuid import UUID

from factory_os.domain.model_usage import cost_label
from factory_os.domain.tenant_config import TenantConfig


@dataclass(frozen=True)
class BusinessRecord:
    tenant_id: UUID
    name: str
    industry: str
    modules: tuple[str, ...] = field(default_factory=tuple)
    whatsapp_status: str = "unknown"
    version: str = "draft"
    cost: str | None = None


_REGISTRY: dict[UUID, BusinessRecord] = {}
_PHONES: dict[UUID, str] = {}
_TOKENS: dict[UUID, str] = {}
_CHANNELS_LOADED = False


def clear_operator_registry() -> None:
    global _CHANNELS_LOADED
    _REGISTRY.clear()
    _PHONES.clear()
    _TOKENS.clear()
    _CHANNELS_LOADED = False


def phone_for_tenant(tenant_id: UUID) -> str:
    return _PHONES.get(tenant_id, "")


def token_is_set(tenant_id: UUID) -> bool:
    return bool(_TOKENS.get(tenant_id))


def token_for_tenant(tenant_id: UUID) -> str:
    return _TOKENS.get(tenant_id, "")


def accepted_business_token(access_token: str, *, reserved_token: str) -> str:
    """Return a token this business may keep. The live channel token is refused."""
    token = (access_token or "").strip()
    reserved = (reserved_token or "").strip()
    if token and reserved and token == reserved:
        raise ValueError("pilot_token_reserved")
    return token


def keep_business_token(tenant_id: UUID, access_token: str, *, url: str | None = None) -> None:
    token = (access_token or "").strip()
    if not token:
        return
    load_business_channels(url)
    _TOKENS[tenant_id] = token
    _save_channel(url, tenant_id)


def load_business_channels(url: str | None) -> None:
    """Fill the phone and token maps from the database. A missing table leaves memory as it is."""
    global _CHANNELS_LOADED
    database = (url or "").strip()
    if not database or _CHANNELS_LOADED:
        return
    from factory_os.domain.postgres import connect

    try:
        conn = connect(database)
    except Exception as exc:
        if _missing_relation(exc):
            return
        raise
    try:
        rows = conn.execute(
            "SELECT tenant_id, phone_number_id, access_token FROM business_whatsapp"
        ).fetchall()
    except Exception as exc:
        if _missing_relation(exc):
            return
        raise
    finally:
        conn.close()
    for row in rows:
        tenant_id = row["tenant_id"] if isinstance(row["tenant_id"], UUID) else UUID(str(row["tenant_id"]))
        phone = str(row.get("phone_number_id") or "").strip()
        token = str(row.get("access_token") or "").strip()
        if phone:
            _PHONES[tenant_id] = phone
        if token:
            _TOKENS[tenant_id] = token
    _CHANNELS_LOADED = True


def _save_channel(url: str | None, tenant_id: UUID) -> None:
    database = (url or "").strip()
    phone = _PHONES.get(tenant_id, "")
    if not database or not phone:
        return
    from factory_os.domain.postgres import connect

    try:
        conn = connect(database)
    except Exception as exc:
        if _missing_relation(exc):
            return
        raise
    try:
        conn.execute(
            """
            INSERT INTO business_whatsapp (tenant_id, phone_number_id, access_token)
            VALUES (%s, %s, %s)
            ON CONFLICT (tenant_id) DO UPDATE
            SET phone_number_id = EXCLUDED.phone_number_id,
                access_token = CASE
                    WHEN EXCLUDED.access_token = '' THEN business_whatsapp.access_token
                    ELSE EXCLUDED.access_token
                END
            """,
            (str(tenant_id), phone, _TOKENS.get(tenant_id, "")),
        )
        conn.commit()
    except Exception as exc:
        if _missing_relation(exc):
            return
        import psycopg

        if isinstance(exc, psycopg.errors.UniqueViolation):
            raise ValueError("phone_taken") from exc
        raise
    finally:
        conn.close()


def _missing_relation(exc: BaseException) -> bool:
    import psycopg

    return isinstance(exc, psycopg.errors.UndefinedTable)


def whatsapp_status_for(
    tenant_id: UUID,
    *,
    live_tenant_id: UUID | None,
    channel_configured: bool,
) -> str:
    """The live process channel is connected. A business with its own number is own_number."""
    if channel_configured and live_tenant_id is not None and tenant_id == live_tenant_id:
        return "connected"
    if phone_for_tenant(tenant_id) and token_is_set(tenant_id):
        return "own_number"
    return "not_connected"


def assign_business_phone(
    tenant_id: UUID,
    phone_number_id: str,
    *,
    reserved_phone_id: str,
    url: str | None = None,
) -> str:
    """Reserve a WhatsApp phone id for one business. The live channel id stays reserved."""
    load_business_channels(url)
    phone = (phone_number_id or "").strip()
    if not phone.isdigit():
        raise ValueError("phone_invalid")
    reserved = (reserved_phone_id or "").strip()
    if reserved and phone == reserved:
        raise ValueError("pilot_phone_reserved")
    for other, taken in _PHONES.items():
        if taken == phone and other != tenant_id:
            raise ValueError("phone_taken")
    previous = _PHONES.get(tenant_id)
    _PHONES[tenant_id] = phone
    try:
        _save_channel(url, tenant_id)
    except ValueError:
        if previous is None:
            _PHONES.pop(tenant_id, None)
        else:
            _PHONES[tenant_id] = previous
        raise
    return phone


def reserved_tenant_for_payload(payload: dict[str, Any], *, live_tenant_id: UUID) -> UUID | None:
    """Tenant that reserved this webhook phone, when it is not the live business."""
    for phone in _payload_phone_ids(payload):
        owner = next((tenant for tenant, taken in _PHONES.items() if taken == phone), None)
        if owner is not None and owner != live_tenant_id:
            return owner
    return None


def inbound_for_other_business(payload: dict[str, Any], *, live_tenant_id: UUID) -> bool:
    """True when the webhook names a phone reserved by a business that is not the live one."""
    return reserved_tenant_for_payload(payload, live_tenant_id=live_tenant_id) is not None


def _payload_phone_ids(payload: dict[str, Any]) -> list[str]:
    found: list[str] = []
    entries = payload.get("entry")
    if not isinstance(entries, list):
        return found
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        changes = entry.get("changes")
        if not isinstance(changes, list):
            continue
        for change in changes:
            if not isinstance(change, dict):
                continue
            value = change.get("value")
            if not isinstance(value, dict):
                continue
            metadata = value.get("metadata")
            if not isinstance(metadata, dict):
                continue
            phone = str(metadata.get("phone_number_id") or "").strip()
            if phone:
                found.append(phone)
    return found


def register_business(
    tenant_id: UUID,
    *,
    name: str,
    config: TenantConfig,
    whatsapp_status: str = "unknown",
    version: str = "draft",
) -> BusinessRecord:
    record = BusinessRecord(
        tenant_id=tenant_id,
        name=(name or "Business").strip() or "Business",
        industry=config.industry,
        modules=config.modules,
        whatsapp_status=whatsapp_status,
        version=version,
    )
    _REGISTRY[tenant_id] = record
    return record


def get_business(tenant_id: UUID, *, url: str | None = None) -> BusinessRecord | None:
    database = (url or "").strip()
    if database:
        for row in _list_postgres(database):
            if row.tenant_id == tenant_id:
                return row
        return None
    return _REGISTRY.get(tenant_id)


def list_businesses(*, url: str | None = None) -> list[BusinessRecord]:
    database = (url or "").strip()
    if database:
        return _list_postgres(database)
    return sorted(_REGISTRY.values(), key=lambda item: item.name.lower())


def _list_postgres(url: str) -> list[BusinessRecord]:
    from factory_os.domain.postgres import connect

    conn = connect(url)
    try:
        rows = conn.execute(
            """
            SELECT id, name, industry, enabled_modules
            FROM tenants
            ORDER BY lower(name)
            """
        ).fetchall()
    finally:
        conn.close()
    return [_record_from_row(row) for row in rows]


def _record_from_row(row: dict[str, Any]) -> BusinessRecord:
    raw_modules = row.get("enabled_modules")
    if isinstance(raw_modules, str):
        import json

        raw_modules = json.loads(raw_modules)
    modules: tuple[str, ...] = ()
    if isinstance(raw_modules, list):
        modules = tuple(str(item) for item in raw_modules if str(item).strip())
    elif isinstance(raw_modules, dict):
        modules = tuple(str(key) for key, value in raw_modules.items() if value)
    return BusinessRecord(
        tenant_id=row["id"] if isinstance(row["id"], UUID) else UUID(str(row["id"])),
        name=str(row.get("name") or "Business"),
        industry=str(row.get("industry") or "closet"),
        modules=modules,
    )


def describe_business(
    record: BusinessRecord,
    *,
    live_tenant_id: UUID | None,
    channel_configured: bool,
    published_tenant_ids: set[UUID],
    url: str | None = None,
) -> BusinessRecord:
    """The live channel is connected. Another business with its own token is own_number."""
    return BusinessRecord(
        tenant_id=record.tenant_id,
        name=record.name,
        industry=record.industry,
        modules=record.modules,
        whatsapp_status=whatsapp_status_for(
            record.tenant_id,
            live_tenant_id=live_tenant_id,
            channel_configured=channel_configured,
        ),
        version="published" if record.tenant_id in published_tenant_ids else "draft",
        cost=cost_label(record.tenant_id, url=url),
    )


def business_as_dict(record: BusinessRecord, *, url: str | None = None) -> dict[str, Any]:
    from factory_os.domain.autonomy import grants_for_tenant, template_autonomy

    payload = asdict(record)
    payload["tenant_id"] = str(record.tenant_id)
    payload["modules"] = list(record.modules)
    try:
        grants = grants_for_tenant(record.tenant_id, industry=record.industry, url=url)
    except (KeyError, ValueError):
        try:
            grants = template_autonomy(record.industry)
        except KeyError:
            grants = ()
    payload["autonomy"] = [{"action": item.action, "level": item.level} for item in grants]
    return payload
