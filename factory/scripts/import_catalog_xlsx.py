#!/usr/bin/env python3
"""Load Authentic Closet Excel into db/seeds/catalog_closet.json.

Chat lookup uses id_producto (h001). Variant SKUs are generated.
Cost, barcode and price override are not imported.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT / "packages" / "domain"))

from factory_os.domain.catalog_xlsx import import_xlsx_to_json  # noqa: E402
from factory_os.domain.seed import closet_seed_path  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "xlsx",
        nargs="?",
        default=str(Path.home() / "Documentos" / "catalogo.xlsx"),
        help="Excel workbook with Productos + Variantes sheets",
    )
    parser.add_argument(
        "--out",
        default=str(closet_seed_path()),
        help="JSON seed path (default db/seeds/catalog_closet.json)",
    )
    parser.add_argument(
        "--photos",
        default=str(ROOT / "db" / "seeds" / "catalog_photos"),
        help="Optional folder of {id_producto}.jpg|png|webp",
    )
    args = parser.parse_args()
    xlsx = Path(args.xlsx)
    if not xlsx.is_file():
        raise SystemExit(f"Excel not found: {xlsx}")
    photos = Path(args.photos)
    dest = import_xlsx_to_json(xlsx, Path(args.out), photo_dir=photos if photos.is_dir() else None)
    print(dest)


if __name__ == "__main__":
    main()
