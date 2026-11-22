"""Cart total for checkout. Prices and the discount are facts, never model output."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Mapping, Sequence

DISCOUNT_EACH = Decimal("5")
DISCOUNT_FROM = 3
HOLD_MINUTES_LIVE = 15
HOLD_MINUTES_OPEN = 20


@dataclass(frozen=True)
class QuotedLine:
    variant_sku: str
    name: str
    quantity: int
    unit_price: Decimal
    currency: str


@dataclass(frozen=True)
class CartQuote:
    lines: tuple[QuotedLine, ...]
    garment_count: int
    subtotal: Decimal
    discount_each: Decimal
    discount: Decimal
    total: Decimal
    currency: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "lines": [
                {
                    "variant_sku": line.variant_sku,
                    "name": line.name,
                    "quantity": line.quantity,
                    "unit_price": str(line.unit_price),
                    "currency": line.currency,
                }
                for line in self.lines
            ],
            "garment_count": self.garment_count,
            "subtotal": str(self.subtotal),
            "discount_each": str(self.discount_each),
            "discount": str(self.discount),
            "total": str(self.total),
            "currency": self.currency,
        }


def hold_minutes_for(live_code: str | None) -> int:
    """Live-code reservations expire sooner than an organic cart."""
    if (live_code or "").strip():
        return HOLD_MINUTES_LIVE
    return HOLD_MINUTES_OPEN


def _money(value: object) -> Decimal:
    return Decimal(str(value if value not in (None, "") else "0"))


def _line_from(raw: Mapping[str, Any] | Any) -> QuotedLine:
    if isinstance(raw, Mapping):
        price = raw.get("unit_price", raw.get("price"))
        return QuotedLine(
            variant_sku=str(raw.get("variant_sku") or ""),
            name=str(raw.get("name") or ""),
            quantity=max(1, int(raw.get("quantity") or 1)),
            unit_price=_money(price),
            currency=str(raw.get("currency") or "BOB"),
        )
    return QuotedLine(
        variant_sku=str(getattr(raw, "variant_sku", "") or ""),
        name=str(getattr(raw, "name", "") or ""),
        quantity=max(1, int(getattr(raw, "quantity", 1) or 1)),
        unit_price=_money(getattr(raw, "unit_price", None)),
        currency=str(getattr(raw, "currency", "") or "BOB"),
    )


def merge_lines(lines: Sequence[Mapping[str, Any] | Any]) -> tuple[QuotedLine, ...]:
    """One row per variant. Quantities add; the later price wins (catalog refresh)."""
    merged: dict[str, QuotedLine] = {}
    order: list[str] = []
    for raw in lines:
        line = _line_from(raw)
        key = line.variant_sku or line.name
        current = merged.get(key)
        if current is None:
            merged[key] = line
            order.append(key)
            continue
        merged[key] = QuotedLine(
            variant_sku=current.variant_sku or line.variant_sku,
            name=line.name or current.name,
            quantity=current.quantity + line.quantity,
            unit_price=line.unit_price,
            currency=line.currency or current.currency,
        )
    return tuple(merged[key] for key in order)


def quote_lines(lines: Sequence[Mapping[str, Any] | Any]) -> CartQuote:
    """5 BOB off each garment when the cart has 3 or more. Otherwise no discount."""
    merged = merge_lines(lines)
    count = sum(line.quantity for line in merged)
    each = DISCOUNT_EACH if count >= DISCOUNT_FROM else Decimal("0")
    discount = each * count
    subtotal = sum((line.unit_price * line.quantity for line in merged), Decimal("0"))
    total = subtotal - discount
    if total < 0:
        total = Decimal("0")
    currency = merged[0].currency if merged else "BOB"
    return CartQuote(
        lines=merged,
        garment_count=count,
        subtotal=subtotal,
        discount_each=each,
        discount=discount,
        total=total,
        currency=currency,
    )


def charge_total(lines: Sequence[Mapping[str, Any] | Any], discount: Decimal) -> Decimal:
    """Amount already stored on a reservation. Does not recompute the rule."""
    quoted = [_line_from(line) for line in lines]
    subtotal = sum((line.unit_price * line.quantity for line in quoted), Decimal("0"))
    total = subtotal - _money(discount)
    if total < 0:
        return Decimal("0")
    return total


def format_line(line: QuotedLine) -> str:
    return f"- {line.name} ×{line.quantity}: {line.unit_price} {line.currency}"


def format_checkout_copy(
    quote: CartQuote,
    *,
    hold_minutes: int,
    qr: str,
    image: bool,
    resent: bool = False,
    item_noun: str = "prenda",
) -> str:
    """Customer-facing list. The QR image itself is attached by the channel."""
    noun = (item_noun or "prenda").strip() or "prenda"
    rows = [format_line(line) for line in quote.lines]
    if quote.discount:
        rows.append(
            f"Descuento de {quote.discount_each} {quote.currency} por {noun} "
            f"({quote.garment_count}): -{quote.discount} {quote.currency}"
        )
    rows.append(f"Total a pagar: {quote.total} {quote.currency}")
    head = "Acá va de nuevo el QR para pagar" if resent else "Para pagar con QR"
    if image:
        pay = f"{head}. Te mando la imagen del código."
    else:
        pay = f"{head}: {qr}."
    rows.append(pay)
    rows.append(
        f"Tiene {hold_minutes} minutos para pagar la reserva. "
        "Cuando el banco confirme, seguimos con el envío."
    )
    return "\n".join(rows)
