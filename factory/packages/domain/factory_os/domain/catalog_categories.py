"""Category order for the counter grid. Blank category is Sin categoría."""

from __future__ import annotations

UNCATEGORIZED = "Sin categoría"


def list_category_rows(store, tenant_id) -> list[dict[str, object]]:
    store.require_tenant(tenant_id)
    order = store.category_sort_map(tenant_id)
    names: set[str] = set()
    blank = False
    for record in store.iter_variants():
        name = (record.category or "").strip()
        if not name:
            blank = True
            continue
        names.add(name)
    ranked = sorted(names, key=lambda name: (int(order.get(name, 1000)), name.casefold()))
    rows: list[dict[str, object]] = [
        {"name": name, "sort_order": int(order.get(name, 1000))} for name in ranked
    ]
    if blank:
        rows.append({"name": UNCATEGORIZED, "sort_order": None})
    return rows


def parse_category_sort(name: str, sort_order: int) -> tuple[str, int]:
    label = (name or "").strip()
    if not label or label.casefold() == UNCATEGORIZED.casefold():
        raise ValueError("bad_category")
    if len(label) > 80:
        raise ValueError("bad_category")
    if sort_order < 0 or sort_order > 10000:
        raise ValueError("bad_sort")
    return label, sort_order
