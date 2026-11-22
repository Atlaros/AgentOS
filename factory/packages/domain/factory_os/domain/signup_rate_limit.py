"""Cap on successful public signups from one client IP."""

from __future__ import annotations

import time

_HITS: dict[str, list[float]] = {}


def clear_signup_limits() -> None:
    _HITS.clear()


def signup_slot_open(
    ip: str,
    *,
    limit: int,
    window_s: float,
    now: float | None = None,
    url: str | None = None,
) -> bool:
    if limit < 1 or window_s <= 0:
        return False
    moment = time.time() if now is None else now
    key = _key(ip)
    recent = _recent_hits(key, moment=moment, window_s=window_s, url=url)
    _HITS[key] = recent
    return len(recent) < limit


def record_signup(ip: str, *, now: float | None = None, url: str | None = None) -> None:
    moment = time.time() if now is None else now
    key = _key(ip)
    _HITS.setdefault(key, []).append(moment)
    _persist_hit(url, key, moment)


def signup_client_ip(peer: str, forwarded_for: str | None, *, trusted_hops: int) -> str:
    """Use the TCP peer unless a configured proxy appended X-Forwarded-For."""
    if trusted_hops < 1:
        return _key(peer)
    parts = [part.strip() for part in (forwarded_for or "").split(",") if part.strip()]
    index = len(parts) - trusted_hops
    if index < 0:
        return _key(peer)
    return _key(parts[index])


def _key(ip: str) -> str:
    return (ip or "").strip() or "unknown"


def _recent_hits(
    ip: str,
    *,
    moment: float,
    window_s: float,
    url: str | None,
) -> list[float]:
    database = (url or "").strip()
    if database:
        loaded = _fetch_hits(database, ip, moment=moment, window_s=window_s)
        if loaded is not None:
            return loaded
    return [stamp for stamp in _HITS.get(ip, []) if moment - stamp < window_s]


def _fetch_hits(
    url: str,
    ip: str,
    *,
    moment: float,
    window_s: float,
) -> list[float] | None:
    from datetime import UTC, datetime, timedelta

    from factory_os.domain.postgres import connect

    try:
        conn = connect(url)
    except Exception as exc:
        if _missing_relation(exc):
            return None
        raise
    try:
        cutoff = datetime.fromtimestamp(moment, tz=UTC) - timedelta(seconds=window_s)
        rows = conn.execute(
            """
            SELECT EXTRACT(EPOCH FROM hit_at) AS hit_epoch
            FROM signup_rate_hits
            WHERE client_ip = %s AND hit_at >= %s
            ORDER BY hit_at
            """,
            (ip, cutoff),
        ).fetchall()
    except Exception as exc:
        if _missing_relation(exc):
            return None
        raise
    finally:
        conn.close()
    return [float(row["hit_epoch"]) for row in rows]


def _persist_hit(url: str | None, ip: str, moment: float) -> None:
    database = (url or "").strip()
    if not database:
        return
    from datetime import UTC, datetime

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
            INSERT INTO signup_rate_hits (client_ip, hit_at)
            VALUES (%s, %s)
            """,
            (ip, datetime.fromtimestamp(moment, tz=UTC)),
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
