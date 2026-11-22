"""Owner credential created with a business. Hashed. A session opens only that business."""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from uuid import UUID

from factory_os.domain.panel_access import hash_panel_secret, new_secret_salt, secret_matches

_OWNERS: dict[UUID, "BusinessOwner"] = {}
_SESSIONS: dict[str, UUID] = {}
_OWNERS_LOADED = False


@dataclass(frozen=True)
class BusinessOwner:
    tenant_id: UUID
    email: str
    secret_salt: str
    secret_hash: str


def clear_business_owners() -> None:
    global _OWNERS_LOADED
    _OWNERS.clear()
    _SESSIONS.clear()
    _OWNERS_LOADED = False


def owner_count() -> int:
    return len(_OWNERS)


def issue_business_owner(tenant_id: UUID, *, name: str, url: str | None = None) -> tuple[str, str]:
    """Return (email, secret). The secret is shown once. Only the hash is kept."""
    del name
    email = f"owner-{tenant_id.hex[:12]}@signup.local"
    secret = secrets.token_urlsafe(18)
    salt = new_secret_salt()
    owner = BusinessOwner(
        tenant_id=tenant_id,
        email=email,
        secret_salt=salt,
        secret_hash=hash_panel_secret(secret, salt),
    )
    _OWNERS[tenant_id] = owner
    _save_owner(url, owner)
    return email, secret


def owner_matches(email: str, secret: str, *, url: str | None = None) -> bool:
    return _find_owner(email, secret, url=url) is not None


def open_owner_session(email: str, secret: str, *, url: str | None = None) -> tuple[str, UUID] | None:
    """Return a session token for this business. The token is not the pilot password."""
    owner = _find_owner(email, secret, url=url)
    if owner is None:
        return None
    token = secrets.token_urlsafe(32)
    _SESSIONS[token] = owner.tenant_id
    _save_session(url, token, owner.tenant_id)
    return token, owner.tenant_id


def owner_for_session(token: str, *, url: str | None = None) -> BusinessOwner | None:
    key = (token or "").strip()
    if not key:
        return None
    tenant_id = _SESSIONS.get(key)
    if tenant_id is None:
        tenant_id = _load_session(url, key)
        if tenant_id is None:
            return None
        _SESSIONS[key] = tenant_id
    load_business_owners(url)
    return _OWNERS.get(tenant_id)


def close_owner_session(token: str, *, url: str | None = None) -> None:
    """Drop an open session from memory and, when present, from the database."""
    key = (token or "").strip()
    if not key:
        return
    _SESSIONS.pop(key, None)
    _delete_session(url, key)


def load_business_owners(url: str | None) -> None:
    """Fill the owner map from the database. A missing table leaves memory as it is."""
    global _OWNERS_LOADED
    database = (url or "").strip()
    if not database or _OWNERS_LOADED:
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
            "SELECT tenant_id, email, secret_salt, secret_hash FROM business_owners"
        ).fetchall()
    except Exception as exc:
        if _missing_relation(exc):
            return
        raise
    finally:
        conn.close()
    for row in rows:
        tenant_id = row["tenant_id"] if isinstance(row["tenant_id"], UUID) else UUID(str(row["tenant_id"]))
        _OWNERS[tenant_id] = BusinessOwner(
            tenant_id=tenant_id,
            email=str(row.get("email") or "").strip().lower(),
            secret_salt=str(row.get("secret_salt") or ""),
            secret_hash=str(row.get("secret_hash") or ""),
        )
    _OWNERS_LOADED = True


def _find_owner(email: str, secret: str, *, url: str | None = None) -> BusinessOwner | None:
    load_business_owners(url)
    key = (email or "").strip().lower()
    for owner in _OWNERS.values():
        if owner.email == key and secret_matches(secret, owner.secret_salt, owner.secret_hash):
            return owner
    return None


def _save_owner(url: str | None, owner: BusinessOwner) -> None:
    database = (url or "").strip()
    if not database:
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
            INSERT INTO business_owners (tenant_id, email, secret_salt, secret_hash)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (tenant_id) DO UPDATE
            SET email = EXCLUDED.email,
                secret_salt = EXCLUDED.secret_salt,
                secret_hash = EXCLUDED.secret_hash
            """,
            (str(owner.tenant_id), owner.email, owner.secret_salt, owner.secret_hash),
        )
        conn.commit()
    except Exception as exc:
        if _missing_relation(exc):
            return
        raise
    finally:
        conn.close()


def _save_session(url: str | None, token: str, tenant_id: UUID) -> None:
    database = (url or "").strip()
    if not database:
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
            INSERT INTO owner_sessions (token, tenant_id)
            VALUES (%s, %s)
            ON CONFLICT (token) DO UPDATE
            SET tenant_id = EXCLUDED.tenant_id
            """,
            (token, str(tenant_id)),
        )
        conn.commit()
    except Exception as exc:
        if _missing_relation(exc):
            return
        raise
    finally:
        conn.close()


def _delete_session(url: str | None, token: str) -> None:
    database = (url or "").strip()
    if not database:
        return
    from factory_os.domain.postgres import connect

    try:
        conn = connect(database)
    except Exception as exc:
        if _missing_relation(exc):
            return
        raise
    try:
        conn.execute("DELETE FROM owner_sessions WHERE token = %s", (token,))
        conn.commit()
    except Exception as exc:
        if _missing_relation(exc):
            return
        raise
    finally:
        conn.close()


def _load_session(url: str | None, token: str) -> UUID | None:
    database = (url or "").strip()
    if not database:
        return None
    from factory_os.domain.postgres import connect

    try:
        conn = connect(database)
    except Exception as exc:
        if _missing_relation(exc):
            return None
        raise
    try:
        row = conn.execute(
            "SELECT tenant_id FROM owner_sessions WHERE token = %s",
            (token,),
        ).fetchone()
    except Exception as exc:
        if _missing_relation(exc):
            return None
        raise
    finally:
        conn.close()
    if row is None:
        return None
    value = row["tenant_id"]
    return value if isinstance(value, UUID) else UUID(str(value))


def _missing_relation(exc: BaseException) -> bool:
    import psycopg

    return isinstance(exc, psycopg.errors.UndefinedTable)
