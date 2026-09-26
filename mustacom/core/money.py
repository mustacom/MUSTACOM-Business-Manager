"""Money, quantity and tax arithmetic.

All monetary amounts are stored in the database as INTEGER *centimes*
(1/100 of the currency unit).  Floating point is never used for money in the
persistence layer, which removes the classic rounding bugs of POS software.

Every helper here is pure and side-effect free so it can be unit tested.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

TWOPLACES = Decimal("0.01")
ZERO = Decimal("0.00")


# ---------------------------------------------------------------------------
# conversions
# ---------------------------------------------------------------------------
def to_decimal(value) -> Decimal:
    """Convert anything sane to a Decimal without float artefacts."""
    if value is None or value == "":
        return ZERO
    if isinstance(value, Decimal):
        return value
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, str):
        cleaned = value.strip().replace(" ", "").replace("\u00a0", "").replace(",", ".")
        if not cleaned:
            return ZERO
        try:
            return Decimal(cleaned)
        except InvalidOperation:
            return ZERO
    return ZERO


def quantize(value: Decimal, places: str = "0.01") -> Decimal:
    return to_decimal(value).quantize(Decimal(places), rounding=ROUND_HALF_UP)


def money_to_cents(value) -> int:
    """1234.567 -> 123457 (centimes, half-up)."""
    return int((to_decimal(value) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def cents_to_money(cents) -> Decimal:
    return (Decimal(int(cents or 0)) / Decimal(100)).quantize(TWOPLACES)


def qty_to_db(value) -> int:
    """Quantities are stored as integers scaled by 1000 (milli-units)."""
    return int((to_decimal(value) * 1000).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def db_to_qty(value) -> Decimal:
    return (Decimal(int(value or 0)) / Decimal(1000)).quantize(Decimal("0.001"))


def rate_to_db(value) -> int:
    """Percent rates stored as integers scaled by 100 (20.00% -> 2000)."""
    return int((to_decimal(value) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def db_to_rate(value) -> Decimal:
    return (Decimal(int(value or 0)) / Decimal(100)).quantize(TWOPLACES)


# ---------------------------------------------------------------------------
# formatting
# ---------------------------------------------------------------------------
def format_money(value, symbol: str = "DH", with_symbol: bool = True) -> str:
    """Moroccan style: 12 345,67 DH (space thousands, comma decimals)."""
    amount = quantize(value)
    negative = amount < 0
    amount = abs(amount)
    integer_part, _, fraction = f"{amount:.2f}".partition(".")
    grouped = ""
    while len(integer_part) > 3:
        grouped = "\u00a0" + integer_part[-3:] + grouped
        integer_part = integer_part[:-3]
    grouped = integer_part + grouped
    text = f"{grouped},{fraction}"
    if with_symbol and symbol:
        text = f"{text}\u00a0{symbol}"
    return ("-" + text) if negative else text


def format_qty(value) -> str:
    qty = db_to_qty(value) if isinstance(value, int) and abs(value) > 999 else to_decimal(value)
    qty = qty.quantize(Decimal("0.001"))
    if qty == qty.to_integral_value():
        return str(int(qty))
    return f"{qty:.3f}".rstrip("0").rstrip(".")


def format_percent(value) -> str:
    return f"{quantize(value)} %"


# ---------------------------------------------------------------------------
# line / document totals
# ---------------------------------------------------------------------------
@dataclass
class Line:
    """A single sellable line (product or service)."""

    ref_type: str = "product"          # product | service
    ref_id: int | None = None
    code: str = ""
    label: str = ""
    unit: str = "u"
    qty: Decimal = Decimal("1")
    unit_price_ht: Decimal = Decimal("0")
    vat_rate: Decimal = Decimal("0")
    discount_percent: Decimal = Decimal("0")
    discount_fixed: Decimal = Decimal("0")
    price_includes_vat: bool = False
    extra: dict = field(default_factory=dict)

    @property
    def gross_ht(self) -> Decimal:
        """Line total before discount (HT)."""
        return quantize(self.qty * self.unit_price_ht)

    @property
    def discount_amount(self) -> Decimal:
        pct = quantize(self.gross_ht * self.discount_percent / Decimal(100))
        fixed = quantize(self.discount_fixed)
        return min(self.gross_ht, pct + fixed)

    @property
    def net_ht(self) -> Decimal:
        return quantize(self.gross_ht - self.discount_amount)

    @property
    def vat_amount(self) -> Decimal:
        return quantize(self.net_ht * self.vat_rate / Decimal(100))

    @property
    def total_ttc(self) -> Decimal:
        return quantize(self.net_ht + self.vat_amount)

    @property
    def unit_price_ttc(self) -> Decimal:
        if not self.qty:
            return Decimal("0")
        return quantize(self.total_ttc / self.qty)

    def as_dict(self) -> dict:
        return {
            "ref_type": self.ref_type,
            "ref_id": self.ref_id,
            "code": self.code,
            "label": self.label,
            "unit": self.unit,
            "qty": str(self.qty),
            "unit_price_ht": str(self.unit_price_ht),
            "vat_rate": str(self.vat_rate),
            "discount_percent": str(self.discount_percent),
            "discount_fixed": str(self.discount_fixed),
            "gross_ht": str(self.gross_ht),
            "discount_amount": str(self.discount_amount),
            "net_ht": str(self.net_ht),
            "vat_amount": str(self.vat_amount),
            "total_ttc": str(self.total_ttc),
            "total_cents": money_to_cents(self.total_ttc),
        }


def compute_totals(lines, global_discount_percent: Decimal = Decimal(0),
                   global_discount_fixed: Decimal = Decimal(0)):
    """Aggregate a set of :class:`Line` into document totals.

    The global discount is prorated across the lines by their net HT weight,
    so every line keeps a consistent discount rate (required for a correct
    VAT breakdown on the printed document).
    """
    lines = list(lines)
    subtotal = quantize(sum((ln.gross_ht for ln in lines), ZERO))
    line_discount = quantize(sum((ln.discount_amount for ln in lines), ZERO))
    net_before_global = quantize(subtotal - line_discount)

    gp = to_decimal(global_discount_percent)
    gf = to_decimal(global_discount_fixed)
    global_discount = quantize(net_before_global * gp / Decimal(100) + gf)
    if global_discount > net_before_global:
        global_discount = net_before_global

    total_ht = quantize(net_before_global - global_discount)

    # prorate
    prorated = {}
    if lines and net_before_global > 0:
        remaining = global_discount
        for index, ln in enumerate(lines[:-1]):
            share = quantize(global_discount * ln.net_ht / net_before_global)
            prorated[index] = share
            remaining -= share
        prorated[len(lines) - 1] = quantize(remaining)

    vat_by_rate: dict[str, Decimal] = {}
    for index, ln in enumerate(lines):
        effective_net = quantize(ln.net_ht - prorated.get(index, ZERO))
        vat = quantize(effective_net * ln.vat_rate / Decimal(100))
        key = f"{quantize(ln.vat_rate)}"
        vat_by_rate[key] = quantize(vat_by_rate.get(key, ZERO) + vat)

    total_vat = quantize(sum(vat_by_rate.values(), ZERO))
    total_ttc = quantize(total_ht + total_vat)

    return {
        "subtotal_ht": subtotal,
        "line_discount": line_discount,
        "global_discount": global_discount,
        "total_ht": total_ht,
        "vat_breakdown": vat_by_rate,
        "total_vat": total_vat,
        "total_ttc": total_ttc,
        "prorated_discount": prorated,
        "total_ht_cents": money_to_cents(total_ht),
        "total_vat_cents": money_to_cents(total_vat),
        "total_ttc_cents": money_to_cents(total_ttc),
        "subtotal_ht_cents": money_to_cents(subtotal),
        "discount_cents": money_to_cents(line_discount + global_discount),
    }


def totals_from_cents(total_ht_cents: int, total_vat_cents: int, total_ttc_cents: int,
                      subtotal_ht_cents: int = 0, discount_cents: int = 0) -> dict:
    """Rebuild the totals dict from stored centime columns."""
    return {
        "subtotal_ht": cents_to_money(subtotal_ht_cents),
        "total_ht": cents_to_money(total_ht_cents),
        "total_vat": cents_to_money(total_vat_cents),
        "total_ttc": cents_to_money(total_ttc_cents),
        "global_discount": cents_to_money(discount_cents),
        "total_ht_cents": total_ht_cents,
        "total_vat_cents": total_vat_cents,
        "total_ttc_cents": total_ttc_cents,
    }


def split_ttc_to_ht(ttc: Decimal, vat_rate: Decimal) -> tuple[Decimal, Decimal]:
    """Given a TTC amount and a VAT rate, return (ht, vat)."""
    ttc = to_decimal(ttc)
    rate = to_decimal(vat_rate)
    ht = quantize(ttc / (Decimal(1) + rate / Decimal(100)))
    return ht, quantize(ttc - ht)


def compute_margin(cost_cents: int, price_cents: int) -> Decimal:
    """Margin percentage of the selling price."""
    if not price_cents:
        return ZERO
    return quantize((Decimal(price_cents - cost_cents) / Decimal(price_cents)) * 100)


def price_from_margin(cost, target_margin_percent) -> Decimal:
    """Selling price HT that yields the requested margin percent."""
    cost = to_decimal(cost)
    margin = to_decimal(target_margin_percent)
    if margin >= 100:
        return cost
    return quantize(cost / (Decimal(1) - margin / Decimal(100)))


def price_with_markup(cost, markup_percent) -> Decimal:
    return quantize(to_decimal(cost) * (Decimal(1) + to_decimal(markup_percent) / Decimal(100)))
