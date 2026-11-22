"""One-time codes that allow a public signup while the flag is on."""

from __future__ import annotations

import secrets

_UNUSED: set[str] = set()
_INVITES_LOADED = False


def clear_invites() -> None:
    global _INVITES_LOADED
    _UNUSED.clear()
    _INVITES_LOADED = False


def issue_invite(*, url: str | None = None) -> str:
    code = secrets.token_urlsafe(18)
    _UNUSED.add(code)
    _persist_invite(url, code)
    return code


def consume_invite(code: str, *, url: str | None = None) -> bool:
    load_invites(url)
    key = (code or "").strip()
    if not key or key not in _UNUSED:
        return False
    _UNUSED.remove(key)
    _delete_invite(url, key)
    return True


def load_invites(url: str | None) -> None:
    """Fill unused invites from the database. A missing table leaves memory as it is."""
    global _INVITES_LOADED
    database = (url or "").strip()
    if not database or _INVITES_LOADED:
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
            "SELECT code FROM signup_invites WHERE used_at IS NULL"
        ).fetchall()
    except Exception as exc:
        if _missing_relation(exc):
            return
        raise
    finally:
        conn.close()
    for row in rows:
        code = str(row.get("code") or "").strip()
        if code:
            _UNUSED.add(code)
    _INVITES_LOADED = True


def _persist_invite(url: str | None, code: str) -> None:
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
            INSERT INTO signup_invites (code)
            VALUES (%s)
            ON CONFLICT (code) DO NOTHING
            """,
            (code,),
        )
        conn.commit()
    except Exception as exc:
        if _missing_relation(exc):
            return
        raise
    finally:
        conn.close()


def _delete_invite(url: str | None, code: str) -> None:
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
            UPDATE signup_invites
            SET used_at = now()
            WHERE code = %s AND used_at IS NULL
            """,
            (code,),
        )
        conn.commit()
    except Exception as exc:
        if _missing_relation(exc):
            return
        raise
    finally:
        conn.close()


def _missing_relation(exc: BaseException) -> bool:
    import psycopg

    return isinstance(exc, psycopg.errors.UndefinedTable)
