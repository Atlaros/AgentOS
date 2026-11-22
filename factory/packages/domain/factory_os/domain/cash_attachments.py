"""Cash movement attachment helpers — metadata in store, bytes on disk (ADR-009 T8)."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from factory_os.domain.models import CashAttachment

MAX_ATTACHMENT_BYTES = 2 * 1024 * 1024

_UNSAFE_NAME = re.compile(r"[^\w.\-]+", re.UNICODE)


def cash_attachments_root() -> Path:
    """Directory for attachment bytes. Override with CASH_ATTACHMENTS_DIR."""
    env = (os.environ.get("CASH_ATTACHMENTS_DIR") or "").strip()
    if env:
        return Path(env)
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "db" / "migrations").is_dir():
            return parent / "data" / "cash_attachments"
    return Path.cwd() / "data" / "cash_attachments"


def safe_filename(name: str) -> str:
    base = Path(name or "").name.strip() or "file"
    cleaned = _UNSAFE_NAME.sub("_", base).strip("._") or "file"
    return cleaned[:180]


def build_storage_key(tenant_id: UUID, movement_id: UUID, filename: str) -> str:
    return f"{tenant_id}/{movement_id}/{uuid4()}_{safe_filename(filename)}"


def write_attachment_bytes(storage_key: str, data: bytes, *, root: Path | None = None) -> Path:
    base = root if root is not None else cash_attachments_root()
    path = base.joinpath(*Path(storage_key).parts)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def attachment_payload(attachment: CashAttachment) -> dict[str, Any]:
    return {
        "id": str(attachment.id),
        "movement_id": str(attachment.movement_id),
        "filename": attachment.filename,
        "content_type": attachment.content_type,
        "size_bytes": attachment.size_bytes,
        "storage_key": attachment.storage_key,
        "uploaded_by_name": attachment.uploaded_by_name or "",
        "created_at": attachment.created_at.isoformat() if attachment.created_at else None,
    }
