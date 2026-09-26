"""Money / VAT arithmetic - the calculations printed on every document."""

from __future__ import annotations

from decimal import Decimal

import pytest

from mustacom.core.money import (Line, cents_to_money, compute_totals, format_money,
                                 money_to_cents, price_from_margin, price_with_markup,
                                 qty_to_db, db_to_qty, rate_to_db, db_to_rate,
                                 split_ttc_to_ht)


def test_centime_conversion_is_exact():
    assert money_to_cents(Decimal("1234.56")) == 123456
    assert money_to_cents("1234.565") == 123457      # half-up
    assert money_to_cents(0.1 + 0.2) == 30           # float artefact absorbed
    assert cents_to_money(123456) == Decimal("1234.56")
    assert money_to_cents(None) == 0
    assert money_to_cents("1 234,56") == 123456      # moroccan input style


def test_quantity_and_rate_scaling():
    assert qty_to_db(2.5) == 2500
    assert db_to_qty(2500) == Decimal("2.500")
    assert rate_to_db(20) == 2000
    assert db_to_rate(2000) == Decimal("20.00")


def test_format_money_moroccan_style():
    assert format_money(1234.5) == "1\u00a0234,50\u00a0DH"
    assert format_money(-50) == "-50,00\u00a0DH"
    assert format_money(1000000, with_symbol=False) == "1\u00a0000\u00a0000,00"


def test_single_line_vat():
    line = Line(qty=2, unit_price_ht=Decimal("100.00"), vat_rate=Decimal("20"))
    assert line.gross_ht == Decimal("200.00")
    assert line.vat_amount == Decimal("40.00")
    assert line.total_ttc == Decimal("240.00")


def test_line_discount_percent_and_fixed():
    line = Line(qty=1, unit_price_ht=Decimal("100.00"), vat_rate=Decimal("20"),
                discount_percent=Decimal("10"), discount_fixed=Decimal("5.00"))
    assert line.discount_amount == Decimal("15.00")
    assert line.net_ht == Decimal("85.00")
    assert line.vat_amount == Decimal("17.00")
    assert line.total_ttc == Decimal("102.00")


def test_discount_cannot_exceed_line_total():
    line = Line(qty=1, unit_price_ht=Decimal("50.00"), discount_fixed=Decimal("999"))
    assert line.discount_amount == Decimal("50.00")
    assert line.net_ht == Decimal("0.00")


def test_totals_with_mixed_vat_rates():
    lines = [
        Line(label="Papier A4", qty=2, unit_price_ht=Decimal("45.00"), vat_rate=Decimal("20")),
        Line(label="Livre exon\u00e9r\u00e9", qty=1, unit_price_ht=Decimal("100.00"),
             vat_rate=Decimal("0")),
        Line(label="Service r\u00e9duit", qty=1, unit_price_ht=Decimal("200.00"),
             vat_rate=Decimal("10")),
    ]
    totals = compute_totals(lines)
    assert totals["subtotal_ht"] == Decimal("390.00")   # 90 + 100 + 200
    assert totals["total_ht"] == Decimal("390.00")
    # 90 * 20% = 18.00 ; 200 * 10% = 20.00
    assert totals["total_vat"] == Decimal("38.00")
    assert totals["total_ttc"] == Decimal("428.00")
    assert totals["vat_breakdown"] == {"0.00": Decimal("0.00"),
                                       "10.00": Decimal("20.00"),
                                       "20.00": Decimal("18.00")}


def test_global_discount_is_prorated_and_keeps_totals_consistent():
    lines = [
        Line(qty=1, unit_price_ht=Decimal("100.00"), vat_rate=Decimal("20")),
        Line(qty=1, unit_price_ht=Decimal("300.00"), vat_rate=Decimal("20")),
    ]
    totals = compute_totals(lines, global_discount_percent=Decimal("10"))
    assert totals["global_discount"] == Decimal("40.00")
    assert totals["total_ht"] == Decimal("360.00")
    assert totals["total_vat"] == Decimal("72.00")
    assert totals["total_ttc"] == Decimal("432.00")
    assert totals["total_ttc_cents"] == 43200
    # HT + TVA must always equal TTC
    assert totals["total_ht"] + totals["total_vat"] == totals["total_ttc"]


def test_global_discount_fixed_capped_at_total():
    lines = [Line(qty=1, unit_price_ht=Decimal("10.00"))]
    totals = compute_totals(lines, global_discount_fixed=Decimal("500"))
    assert totals["global_discount"] == Decimal("10.00")
    assert totals["total_ttc"] == Decimal("0.00")


def test_split_ttc_to_ht():
    ht, vat = split_ttc_to_ht(Decimal("120.00"), Decimal("20"))
    assert ht == Decimal("100.00")
    assert vat == Decimal("20.00")


def test_margin_helpers():
    assert price_with_markup(100, 30) == Decimal("130.00")
    # a 30% margin on the selling price means cost = 70% of it
    assert price_from_margin(70, 30) == Decimal("100.00")


def test_no_penny_drift_over_many_lines():
    """1001 lines of 0.335 must not accumulate rounding error."""
    lines = [Line(qty=1, unit_price_ht=Decimal("0.335"), vat_rate=Decimal("20"))
             for _ in range(1001)]
    totals = compute_totals(lines)
    assert totals["total_ht"] + totals["total_vat"] == totals["total_ttc"]
    assert totals["total_ttc_cents"] == money_to_cents(totals["total_ttc"])
