"""Three-way match engine: every exception type, and both sides of every limit."""

from __future__ import annotations

from datetime import date
from decimal import Decimal as D

import pytest

from opsmesh.config import load_tolerances
from opsmesh.engine.matching import ExceptionType as E
from opsmesh.engine.matching import match_invoice, normalise_invoice_number
from opsmesh.engine.models import POLine, PurchaseOrder, Vendor
from tests.builders import ABN, OTHER_VENDOR, PO, VENDOR, invoice, master, posted

UNKNOWN_ABN = "87192327523"  # checksum-valid, not in the test vendor master


@pytest.fixture
def tol():
    return load_tolerances()


def types(result) -> list[E]:
    return result.exception_types


# --- clean ------------------------------------------------------------------------

def test_clean_invoice_matches(tol):
    r = match_invoice(invoice([("RES-A", 10, None)]), master(), tol)
    assert r.is_clean
    assert r.vendor_id == "V1" and r.po_number == PO
    assert {s.check for s in r.trace} >= {"Arithmetic", "Vendor", "Duplicate", "Purchase order", "GST"}
    assert all(s.outcome != "fail" for s in r.trace)


# --- price variance ------------------------------------------------------------------

def test_price_over_percentage_limit(tol):
    r = match_invoice(invoice([("RES-A", 1, "1030.00")]), master(), tol)  # +3%, $30
    assert types(r) == [E.PRICE_VARIANCE]
    assert r.exceptions[0].details["breached"] == "percentage"
    assert r.exceptions[0].line == 1


def test_price_within_tolerance_passes(tol):
    r = match_invoice(invoice([("RES-A", 1, "1015.00")]), master(), tol)  # +1.5%, $15
    assert r.is_clean
    assert any("within tolerance" in s.detail for s in r.trace)


def test_price_exactly_at_limit_passes(tol):
    r = match_invoice(invoice([("RES-A", 1, "1020.00")]), master(), tol)  # exactly +2%
    assert r.is_clean


def test_price_over_dollar_cap_even_when_percent_is_fine(tol):
    # +1.5% is inside the % limit, but 2,000 L x $0.15 = $300 over, above the $250 cap
    r = match_invoice(invoice([("CHM-BULK", 2000, "10.15")]), master(), tol)
    assert types(r) == [E.PRICE_VARIANCE]
    assert r.exceptions[0].details["breached"] == "dollar"


def test_price_below_po_is_noted_not_blocked(tol):
    r = match_invoice(invoice([("RES-A", 10, "950.00")]), master(), tol)
    assert r.is_clean
    assert any(s.outcome == "info" and "below the PO price" in s.detail for s in r.trace)


def test_tolerances_are_configurable(tol):
    tight = tol.model_copy(update={"price": tol.price.model_copy(update={"pct": D("0.01")})})
    inv = invoice([("RES-A", 1, "1015.00")])  # +1.5%
    assert match_invoice(inv, master(), tol).is_clean
    assert types(match_invoice(inv, master(), tight)) == [E.PRICE_VARIANCE]


# --- quantity: short-shipped / missing receipt ------------------------------------------

def test_short_shipped(tol):
    r = match_invoice(invoice([("RES-A", 12, None)]), master(receipts={10: [10]}), tol)
    assert types(r) == [E.SHORT_SHIPPED]
    assert r.exceptions[0].details["short"] == "2"


def test_receiving_note_is_quoted_on_short_shipment(tol):
    m = master(receipts={10: [8]})
    m.goods_receipts[0].lines[0].note = "2 bags torn, rejected"
    r = match_invoice(invoice([("RES-A", 10, None)]), m, tol)
    assert "2 bags torn, rejected" in r.exceptions[0].message


def test_missing_goods_receipt(tol):
    r = match_invoice(invoice([("RES-B", 5, None)]), master(), tol)  # line 50 never received
    assert types(r) == [E.MISSING_GOODS_RECEIPT]
    assert "no goods receipt" in r.exceptions[0].message


def test_missing_receipt_when_everything_received_is_already_invoiced(tol):
    m = master(receipts={10: [5]}, ledger=[posted("INV-099", "5500.00", lines=[(10, 5)])])
    r = match_invoice(invoice([("RES-A", 5, None)]), m, tol)
    assert types(r) == [E.MISSING_GOODS_RECEIPT]
    assert "already been invoiced" in r.exceptions[0].message


def test_partial_receipts_are_cumulative(tol):
    m = master(receipts={10: [4, 6]}, ledger=[posted("INV-099", "4400.00", lines=[(10, 4)])])
    assert match_invoice(invoice([("RES-A", 6, None)]), m, tol).is_clean
    assert types(match_invoice(invoice([("RES-A", 7, None)]), m, tol)) == [E.SHORT_SHIPPED]


def test_same_po_line_twice_on_one_invoice_consumes_receipts(tol):
    r = match_invoice(invoice([("RES-A", 6, None), ("RES-A", 6, None)]), master(receipts={10: [10]}), tol)
    assert types(r) == [E.SHORT_SHIPPED]
    assert r.exceptions[0].line == 2


# --- services: two-way match ---------------------------------------------------------------

def test_service_line_needs_no_goods_receipt(tol):
    r = match_invoice(invoice([("SVC-HR", 8, None)]), master(receipts={}), tol)
    assert r.is_clean
    assert any("two-way match" in s.detail for s in r.trace)


def test_service_billed_beyond_po_quantity(tol):
    r = match_invoice(invoice([("SVC-HR", 12, None)]), master(), tol)
    assert types(r) == [E.OVER_PO_QUANTITY]


# --- duplicates ---------------------------------------------------------------------------

def test_exact_duplicate_short_circuits(tol):
    m = master(ledger=[posted("INV-100", "11000.00")])
    r = match_invoice(invoice([("RES-A", 10, "1100.00")]), m, tol)  # price is also wrong...
    assert types(r) == [E.DUPLICATE_INVOICE]  # ...but a duplicate stops matching
    assert r.exceptions[0].details["match"] == "exact"


def test_duplicate_with_different_number_formatting(tol):
    m = master(ledger=[posted("100", "999.00", inv_date=date(2026, 6, 1))])
    r = match_invoice(invoice([("RES-A", 10, None)], number="INV-00100"), m, tol)
    assert types(r) == [E.DUPLICATE_INVOICE]
    assert r.exceptions[0].details["match"] == "number_format"


def test_duplicate_same_amount_and_date_new_number(tol):
    m = master(ledger=[posted("INV-077", "11000.00", inv_date=date(2026, 9, 7))])
    r = match_invoice(invoice([("RES-A", 10, None)], number="INV-101"), m, tol)
    assert types(r) == [E.DUPLICATE_INVOICE]
    assert r.exceptions[0].details["match"] == "amount_and_date"


def test_same_amount_outside_window_is_not_duplicate(tol):
    m = master(ledger=[posted("INV-077", "11000.00", inv_date=date(2026, 8, 1))])
    assert match_invoice(invoice([("RES-A", 10, None)], number="INV-101"), m, tol).is_clean


def test_same_number_from_another_vendor_is_not_duplicate(tol):
    m = master(ledger=[posted("INV-100", "11000.00", vendor_id="V2")])
    assert match_invoice(invoice([("RES-A", 10, None)]), m, tol).is_clean


@pytest.mark.parametrize("raw,expected", [
    ("INV-004417", "4417"), ("inv 4417", "4417"), ("4417", "4417"), ("LIS-0003321", "3321"),
    ("HCC/00042", "42"), ("ABC", "ABC"), ("000", "0"),
])
def test_invoice_number_normalisation(raw, expected):
    assert normalise_invoice_number(raw) == expected


# --- vendor -----------------------------------------------------------------------------------

def test_unknown_vendor_stops_matching(tol):
    r = match_invoice(invoice([("RES-A", 10, "1500.00")], abn=UNKNOWN_ABN, name="New Co Pty Ltd"), master(), tol)
    assert types(r) == [E.UNKNOWN_VENDOR]
    assert r.vendor_id is None
    assert not any(s.check == "Purchase order" for s in r.trace)


def test_lookalike_vendor_with_bank_change_is_flagged(tol):
    inv = invoice([("RES-A", 10, None)], abn=UNKNOWN_ABN, name="Test Resins Pty. Ltd.",
                  remarks="Our bank details have changed, please update.")
    r = match_invoice(inv, master(), tol)
    exc = r.exceptions[0]
    assert exc.type is E.UNKNOWN_VENDOR
    assert exc.details["lookalike_vendor"] == "V1"
    assert exc.details["bank_details_change"] == "mentioned on invoice"
    assert "impersonation" in exc.message


def test_abn_failing_checksum_is_called_out(tol):
    r = match_invoice(invoice([("RES-A", 10, None)], abn="12345678901", name="Nobody"), master(), tol)
    assert r.exceptions[0].details["abn_checksum"] == "fails"


def test_inactive_vendor_is_blocked(tol):
    blocked = VENDOR.model_copy(update={"active": False})
    r = match_invoice(invoice([("RES-A", 10, None)]), master(vendors=[blocked]), tol)
    assert types(r) == [E.UNKNOWN_VENDOR]
    assert "inactive" in r.exceptions[0].message


# --- GST -------------------------------------------------------------------------------------------

def test_gst_miscalculated(tol):
    r = match_invoice(invoice([("RES-A", 10, None)], gst="1018.00"), master(), tol)  # should be 1,000.00
    assert types(r) == [E.GST_ERROR]
    assert r.exceptions[0].details["cause"] == "miscalculated"
    assert r.expected_gst == D("1000.00")


def test_gst_rounding_allowance(tol):
    assert match_invoice(invoice([("RES-A", 10, None)], gst="1000.05"), master(), tol).is_clean
    assert types(match_invoice(invoice([("RES-A", 10, None)], gst="1000.06"), master(), tol)) == [E.GST_ERROR]


def test_gst_free_line_correctly_excluded(tol):
    r = match_invoice(invoice([("RES-A", 10, None), ("FRT-INT", 1, None)]), master(), tol)
    assert r.is_clean
    assert r.taxable_amount == D("10000.00")


def test_gst_charged_on_gst_free_line(tol):
    r = match_invoice(invoice([("RES-A", 10, None), ("FRT-INT", 1, None)], gst_on_free=True), master(), tol)
    assert types(r) == [E.GST_ERROR]
    assert r.exceptions[0].details["cause"] == "gst_on_gst_free"


def test_gst_from_vendor_not_registered(tol):
    unregistered = VENDOR.model_copy(update={"gst_registered": False})
    r = match_invoice(invoice([("RES-A", 10, None)]), master(vendors=[unregistered]), tol)
    assert types(r) == [E.GST_ERROR]
    assert r.exceptions[0].details["cause"] == "vendor_not_registered"


# --- PO problems ------------------------------------------------------------------------------------

def test_no_po_number(tol):
    r = match_invoice(invoice([("RES-A", 10, None)], po=None), master(), tol)
    assert types(r) == [E.PO_NOT_FOUND]


def test_po_does_not_exist(tol):
    r = match_invoice(invoice([("RES-A", 10, None)], po="4599999999"), master(), tol)
    assert types(r) == [E.PO_NOT_FOUND]


def test_po_belongs_to_another_vendor(tol):
    other_po = PurchaseOrder(po_number="4500000002", vendor_id="V2", order_date=date(2026, 8, 1), buyer="T",
                             lines=[POLine(line_no=10, item_code="X", description="X", quantity=D(1), uom="ea",
                                           unit_price=D(1))])
    r = match_invoice(invoice([("RES-A", 10, None)], po="4500000002"), master(extra_pos=[other_po]), tol)
    assert types(r) == [E.PO_NOT_FOUND]
    assert OTHER_VENDOR.name in r.exceptions[0].message


def test_line_not_on_po(tol):
    r = match_invoice(invoice([("RES-A", 10, None), ("FUEL-LEVY", 1, "85.00")]), master(), tol)
    assert types(r) == [E.LINE_NOT_ON_PO]
    assert r.exceptions[0].line == 2


def test_line_matched_by_description_when_no_code(tol):
    inv = invoice([("RES-A", 10, None)])
    inv.lines[0].item_code = None
    inv.lines[0].description = "Resin - grade A"
    r = match_invoice(inv, master(), tol)
    assert r.is_clean
    assert r.lines[0].match_method.startswith("description")


def test_po_line_reference_wins(tol):
    inv = invoice([("RES-A", 10, None)])
    inv.lines[0].item_code, inv.lines[0].po_line = "VENDOR-SKU-9", 10
    r = match_invoice(inv, master(), tol)
    assert r.is_clean and r.lines[0].match_method == "PO line reference"


# --- arithmetic & combinations ----------------------------------------------------------------------

def test_invoice_that_does_not_add_up(tol):
    r = match_invoice(invoice([("RES-A", 10, None)], total="11100.00"), master(), tol)
    assert types(r) == [E.INVOICE_MATH]


def test_several_exceptions_reported_together(tol):
    inv = invoice([("RES-A", 12, "1100.00"), ("RES-B", 5, None)])
    r = match_invoice(inv, master(receipts={10: [10], 40: [2000]}), tol)
    assert set(types(r)) == {E.PRICE_VARIANCE, E.SHORT_SHIPPED, E.MISSING_GOODS_RECEIPT}
    assert "3 exceptions" in r.summary


def test_every_exception_type_has_label_and_owner():
    for t in E:
        assert t.label and t.owner
