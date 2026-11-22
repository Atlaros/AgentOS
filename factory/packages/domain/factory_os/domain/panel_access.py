"""Panel humans are not digital employees. Secrets are stored hashed."""

from __future__ import annotations

import hashlib
import hmac
import secrets

PANEL_ROLES = frozenset({"owner", "supervisor", "staff"})
# Admin may be seeded as a support login; owners never assign that role.
STORED_PANEL_ROLES = PANEL_ROLES | frozenset({"admin"})
OWNER_ROLES = frozenset({"admin", "owner"})
SUPERVISOR_ROLES = frozenset({"admin", "owner", "supervisor"})
AUDIT_ROLES = frozenset({"admin", "owner", "supervisor", "staff"})
OWNER_ASSIGNABLE_ROLES = frozenset({"supervisor", "staff"})


def new_secret_salt() -> str:
    return secrets.token_hex(16)


def hash_panel_secret(secret: str, salt: str) -> str:
    digest = hashlib.scrypt(
        secret.encode("utf-8"),
        salt=salt.encode("utf-8"),
        n=2**14,
        r=8,
        p=1,
        dklen=32,
    )
    return digest.hex()


def secret_matches(secret: str, salt: str, hashed: str) -> bool:
    return hmac.compare_digest(hash_panel_secret(secret, salt), hashed)


def pin_matches(pin: str, salt: str, hashed: str) -> bool:
    """PIN uses the same scrypt construction as panel secrets."""
    return secret_matches(pin, salt, hashed)


def is_owner_role(role: str) -> bool:
    return role in OWNER_ROLES


def is_supervisor_role(role: str) -> bool:
    return role in SUPERVISOR_ROLES


def roles_assignable_by(actor_role: str) -> frozenset[str]:
    """Admin creates the owner. The owner creates supervisor and equipo."""
    if actor_role == "admin":
        return PANEL_ROLES
    if actor_role == "owner":
        return OWNER_ASSIGNABLE_ROLES
    return frozenset()


def clean_job_title(role: str, raw: str | None) -> str:
    """Equipo may carry a puesto. Other roles do not."""
    title = (raw or "").strip()
    if role != "staff":
        return ""
    if len(title) > 40:
        raise ValueError("bad_job")
    return title
