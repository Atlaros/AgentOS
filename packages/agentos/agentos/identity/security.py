from __future__ import annotations

import hashlib
import secrets

import bcrypt

ALL_SCOPES = [
    "orgs:read",
    "wallets:read",
    "wallets:link",
    "balances:read",
    "payments:create",
    "transfers:execute",
    "approvals:decide",
    "audit:read",
    "policies:read",
]


def generate_api_key() -> tuple[str, str, str]:
    """Return (raw_key, prefix, hash). Raw key shown once."""
    raw = f"aos_{secrets.token_urlsafe(32)}"
    prefix = raw[:12]
    return raw, prefix, hash_api_key(raw)


def _key_digest(raw_key: str) -> bytes:
    # Digest before bcrypt to stay under the 72-byte bcrypt limit.
    return hashlib.sha256(raw_key.encode("utf-8")).digest()


def hash_api_key(raw_key: str) -> str:
    return bcrypt.hashpw(_key_digest(raw_key), bcrypt.gensalt()).decode("ascii")


def verify_api_key(raw_key: str, key_hash: str) -> bool:
    try:
        return bcrypt.checkpw(_key_digest(raw_key), key_hash.encode("ascii"))
    except ValueError:
        return False


def body_hash(payload: str) -> str:
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
