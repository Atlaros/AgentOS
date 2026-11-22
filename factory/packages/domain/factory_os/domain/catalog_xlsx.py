from __future__ import annotations

import json
import xml.etree.ElementTree as ET
import zipfile
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import quote
from uuid import UUID

from factory_os.domain.models import PILOT_TENANT_ID
from factory_os.domain.seed import closet_seed_path, normalize

_SSML = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_NS = {"m": _SSML}
_PHOTO_EXTS = (".jpg", ".jpeg", ".png", ".webp")
_SKIP_ATTRS = frozenset({"precio_costo", "barcode", "codigo_barras", "precio_override_bs"})
_SOLD_FLAGS = frozenset({"si", "yes", "true", "1", "vendido"})


def size_code(talla: str) -> str:
    raw = "".join(ch for ch in (talla or "").strip().upper() if ch.isalnum())
    return raw or "U"


def color_initials(color: str) -> str:
    words = [word for word in normalize(color).split() if word]
    if not words:
        return "X"
    if len(words) == 1:
        letters = "".join(ch for ch in words[0] if ch.isalpha())
        return (letters[:1] or "X").upper()
    initials = "".join(word[0] for word in words if word[0].isalpha())
    return initials.upper() or "X"


def make_variant_sku(product_id: str, talla: str, color: str, used: set[str]) -> str:
    pid = (product_id or "").strip()
    base = f"{pid}-{size_code(talla)}-{color_initials(color)}"
    candidate = base
    n = 2
    while candidate in used:
        candidate = f"{base}{n}"
        n += 1
    used.add(candidate)
    return candidate


def placeholder_image(codigo: str) -> str:
    return f"https://placehold.co/600x800/eee/333?text={quote((codigo or 'item').upper())}"


def find_photo(photo_dir: Path | None, codigo: str) -> Path | None:
    if photo_dir is None or not photo_dir.is_dir():
        return None
    stem = (codigo or "").strip()
    if not stem:
        return None
    for ext in _PHOTO_EXTS:
        path = photo_dir / f"{stem}{ext}"
        if path.is_file():
            return path
    return None


def _col_index(col: str) -> int:
    n = 0
    for ch in col:
        n = n * 26 + (ord(ch.upper()) - 64)
    return n - 1


def _cell_ref(ref: str) -> tuple[str, int]:
    letters = "".join(ch for ch in ref if ch.isalpha())
    digits = "".join(ch for ch in ref if ch.isdigit())
    return letters, int(digits or 0)


def _shared_strings(zf: zipfile.ZipFile) -> list[str]:
    try:
        root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
    except KeyError:
        return []
    out: list[str] = []
    for si in root.findall("m:si", _NS):
        out.append("".join(node.text or "" for node in si.findall(".//m:t", _NS)))
    return out


def _cell_value(cell: ET.Element, strings: list[str]) -> str:
    kind = cell.get("t")
    if kind == "inlineStr":
        return "".join(node.text or "" for node in cell.findall(".//m:t", _NS))
    value = cell.find("m:v", _NS)
    if value is None or value.text is None:
        return ""
    text = value.text
    if kind == "s" and text.isdigit():
        idx = int(text)
        if 0 <= idx < len(strings):
            return strings[idx]
    return text


def _sheet_rows(zf: zipfile.ZipFile, name: str, strings: list[str]) -> list[dict[str, str]]:
    rels = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
    workbook = ET.fromstring(zf.read("xl/workbook.xml"))
    rid = None
    for sheet in workbook.findall("m:sheets/m:sheet", _NS):
        if sheet.get("name") == name:
            rid = sheet.get(
                "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
            )
            break
    if not rid:
        raise FileNotFoundError(f"sheet {name}")
    target = None
    ns = {"r": "http://schemas.openxmlformats.org/package/2006/relationships"}
    for rel in rels.findall("r:Relationship", ns):
        if rel.get("Id") == rid:
            target = rel.get("Target")
            break
    if not target:
        raise FileNotFoundError(f"sheet target {name}")
    root = ET.fromstring(zf.read("xl/" + target.lstrip("/")))
    rows: list[dict[str, str]] = []
    header: list[str] | None = None
    for row in root.findall("m:sheetData/m:row", _NS):
        cells: dict[int, str] = {}
        max_idx = -1
        for cell in row.findall("m:c", _NS):
            col, _r = _cell_ref(cell.get("r") or "")
            if not col:
                continue
            idx = _col_index(col)
            cells[idx] = _cell_value(cell, strings).strip()
            max_idx = max(max_idx, idx)
        if max_idx < 0:
            continue
        values = [cells.get(i, "") for i in range(max_idx + 1)]
        if header is None:
            if values and values[0].strip().lower() == "id_producto":
                header = [item.strip() for item in values]
            continue
        record = {}
        for idx, key in enumerate(header):
            if not key:
                continue
            record[key] = values[idx] if idx < len(values) else ""
        if any(record.values()):
            rows.append(record)
    return rows


def read_catalog_workbook(path: Path) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    with zipfile.ZipFile(path) as zf:
        strings = _shared_strings(zf)
        products = _sheet_rows(zf, "Productos", strings)
        variants = _sheet_rows(zf, "Variantes", strings)
    return products, variants


def _money(raw: str) -> Decimal:
    text = (raw or "").strip().replace(",", ".")
    try:
        return Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(f"invalid price {raw!r}") from exc


def is_sold_flag(raw: str) -> bool:
    return normalize(raw).strip() in _SOLD_FLAGS


def build_catalog_payload(
    products: list[dict[str, str]],
    variants: list[dict[str, str]],
    *,
    tenant_id: UUID = PILOT_TENANT_ID,
    photo_dir: Path | None = None,
) -> dict:
    by_id = {row["id_producto"].strip(): row for row in products if row.get("id_producto", "").strip()}
    used: set[str] = set()
    out: list[dict] = []
    missing: list[str] = []
    for variant in variants:
        pid = (variant.get("id_producto") or "").strip()
        if not pid:
            continue
        product = by_id.get(pid)
        if product is None:
            missing.append(pid)
            continue
        sku = make_variant_sku(pid, variant.get("talla") or "", variant.get("color") or "", used)
        photo = find_photo(photo_dir, pid)
        image_url = (variant.get("imagen_url") or "").split(";")[0].strip()
        if not image_url:
            image_url = placeholder_image(pid)
        attrs = {
            "category": (product.get("categoria") or "").strip() or "general",
            "subcategory": (product.get("subcategoria") or "").strip(),
            "brand": (product.get("marca") or "").strip(),
            "material": (product.get("material") or "").strip(),
            "season": (product.get("temporada") or "").strip(),
            "style": (product.get("estilo") or "").strip(),
            "talla": (variant.get("talla") or "").strip(),
            "color": (variant.get("color") or "").strip(),
            "codigo": pid,
            "codigo_referencia": (product.get("codigo_referencia") or pid).strip(),
            "image_url": image_url,
        }
        if photo is not None:
            attrs["photo_file"] = photo.name
        for key in list(attrs):
            if key in _SKIP_ATTRS or attrs[key] == "":
                attrs.pop(key, None)
        stock_raw = (variant.get("stock") or "0").strip() or "0"
        sold = is_sold_flag(product.get("vendido") or "")
        if sold:
            attrs["disabled"] = True
        out.append(
            {
                "sku": pid,
                "name": (product.get("nombre") or pid).strip(),
                "description": (product.get("descripcion") or "").strip(),
                "variant_sku": sku,
                "currency": "BOB",
                "amount": f"{_money(product.get('precio_base_bs') or '0'):.2f}",
                "available_quantity": 0 if sold else int(Decimal(stock_raw)),
                "low_stock_threshold": 1,
                "attributes": attrs,
            }
        )
    if missing:
        raise ValueError(f"variants without product: {missing[:8]}")
    return {
        "tenant_id": str(tenant_id),
        "branch_name": "La Paz",
        "currency_note": "BOB — Authentic Closet Excel catalog (id_producto is the chat code)",
        "products": out,
    }


def import_xlsx_to_json(
    xlsx: Path,
    dest: Path | None = None,
    *,
    photo_dir: Path | None = None,
) -> Path:
    products, variants = read_catalog_workbook(xlsx)
    payload = build_catalog_payload(products, variants, photo_dir=photo_dir)
    target = dest or closet_seed_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return target
