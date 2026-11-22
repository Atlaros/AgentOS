#!/usr/bin/env python3
"""DEMO ONLY: link Agent-IAv2 cafe product photos into this lab.

Creates data/media -> Agent-IAv2/data/media (symlink) and registers
media_assets + product_media for the pilot tenant. Remove when the demo ends.

Usage (from Factory Agent OS root, with .env loaded):

  .venv/bin/python scripts/link_demo_cafe_media.py
"""

from __future__ import annotations

import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = Path.home() / "Documentos/GitHub/Agent-IAv2/data/media"
PILOT = UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")


def _load_dotenv() -> None:
    env_path = ROOT / ".env"
    if not env_path.is_file():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        raw = line.strip()
        if not raw or raw.startswith("#") or "=" not in raw:
            continue
        key, _, value = raw.partition("=")
        key = key.strip()
        if not key or key in os.environ:
            continue
        os.environ[key] = value.strip().strip('"').strip("'")


def ensure_media_symlink(source: Path) -> Path:
    target = ROOT / "data" / "media"
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_symlink():
        current = target.resolve()
        if current == source.resolve():
            print(f"symlink ok: {target} -> {source}")
            return target
        target.unlink()
    elif target.exists():
        raise SystemExit(f"refusing to replace existing path: {target}")
    if not source.is_dir():
        raise SystemExit(f"source media missing: {source}")
    target.symlink_to(source, target_is_directory=True)
    print(f"symlink created: {target} -> {source}")
    return target


def main() -> int:
    sys.path.insert(0, str(ROOT / "apps" / "api"))
    for extra in (ROOT / "packages" / "domain", ROOT / "packages" / "contracts"):
        sys.path.insert(0, str(extra))

    _load_dotenv()
    source = Path(os.environ.get("DEMO_CAFE_MEDIA_SOURCE") or DEFAULT_SOURCE).expanduser()
    ensure_media_symlink(source)

    url = (os.environ.get("DATABASE_URL") or os.environ.get("DATABASE_RUNTIME_URL") or "").strip()
    if not url:
        raise SystemExit("DATABASE_URL / DATABASE_RUNTIME_URL required")

    from factory_os.domain.catalog_images import sniff_image
    from factory_os.domain.models import MediaAsset, ProductMedia
    from factory_os.domain.postgres import PostgresCommerceStore

    store = PostgresCommerceStore(url, PILOT)
    tenant_dir = source / str(PILOT)
    if not tenant_dir.is_dir():
        raise SystemExit(f"tenant media folder missing: {tenant_dir}")

    linked = 0
    skipped = 0
    missing_product = 0
    for sku_dir in sorted(p for p in tenant_dir.iterdir() if p.is_dir()):
        sku = sku_dir.name
        originals = sorted(
            p
            for p in sku_dir.iterdir()
            if p.is_file() and not p.name.endswith("_thumb.jpg") and p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}
        )
        if not originals:
            continue
        original = originals[0]
        thumb = sku_dir / f"{original.stem}_thumb.jpg"
        if not thumb.is_file():
            thumb = original
        data = original.read_bytes()
        mime = sniff_image(data) or "image/jpeg"
        storage_key = f"{PILOT}/{sku}/{original.name}"
        thumb_key = f"{PILOT}/{sku}/{thumb.name}"

        variant = store.get_variant(PILOT, sku)
        if variant is None:
            missing_product += 1
            continue
        existing = store.list_product_media(PILOT, variant.product_sku)
        if existing:
            skipped += 1
            continue

        asset = store.add_media_asset(
            PILOT,
            MediaAsset(
                id=uuid4(),
                tenant_id=PILOT,
                kind="image",
                mime=mime,
                size_bytes=len(data),
                storage_key=storage_key,
                thumb_key=thumb_key,
                origin="catalog",
                uploaded_by="demo-link-agent-ia",
                created_at=datetime.now(UTC),
            ),
        )
        store.add_product_media(
            PILOT,
            ProductMedia(
                id=uuid4(),
                tenant_id=PILOT,
                product_sku=variant.product_sku,
                asset_id=asset.id,
                is_primary=True,
                sort_order=0,
                created_at=datetime.now(UTC),
            ),
        )
        store.set_product_image_paths(PILOT, variant.product_sku, storage_key, thumb_key)
        linked += 1
        print(f"linked {sku} -> {asset.id}")

    print(
        f"done demo media: linked={linked} skipped={skipped} missing_product={missing_product}"
    )
    print("DEMO ONLY: remove data/media symlink and product_media rows after the demo.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
