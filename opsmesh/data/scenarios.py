"""The 40 invoices in the demo batch and what each one is meant to test.

Each scenario describes the business situation (what was ordered, received,
already invoiced, and what the vendor billed). The generator turns these into
POs, goods receipts, ledger history and PDFs, and writes the expected result
to the answer key.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal as D

from opsmesh.data.catalog import Item

AUTO = "auto"


@dataclass
class Ln:
    code: str
    invoiced: D | int
    ordered: D | int | None = None  # default: prev_invoiced + invoiced
    received: tuple | str = AUTO  # per-delivery quantities; () = nothing receipted
    prev_invoiced: D | int = 0
    price: D | None = None  # what the vendor billed, if not the PO price
    charge_gst: bool | None = None  # vendor charges GST on a GST-free item
    gr_note: str | None = None


@dataclass
class UnknownVendor:
    name: str
    address: tuple[str, ...]
    email: str
    template: str
    number: str
    colour: str
    items: tuple[Item, ...]
    abn: str | None = None  # filled by the generator


@dataclass
class Scenario:
    key: str
    category: str
    vendor_id: str | None
    lines: list[Ln]
    expected: tuple[str, ...]
    description: str
    gst_override: D | None = None
    ledger_number: str | None = None  # duplicates: number the original was posted under
    invoice_date: str | None = None  # ISO; default = spread across September
    remarks: str | None = None
    unknown: UnknownVendor | None = None
    po_of: str | None = None  # quote another scenario's PO instead of our own
    has_po: bool = True
    tags: list[str] = field(default_factory=list)


SCENARIOS: list[Scenario] = [
    # --- Clean: should post with no human touch ---------------------------
    Scenario("C01", "clean", "V1001", [Ln("RES-PET-BTL", 8)], (), "Resin delivery, fully receipted, PO price."),
    Scenario("C02", "clean", "V1002", [Ln("CTN-RSC-400", 4000), Ln("CTN-DIV-12", 4000)], (), "Cartons and dividers, two lines, all received."),
    Scenario("C03", "clean", "V1003", [Ln("INK-FLX-CY", 120), Ln("INK-FLX-MG", 120), Ln("INK-FLX-YL", 100), Ln("INK-FLX-BK", 80)], (), "Four-colour ink order."),
    Scenario("C04", "clean", "V1004", [Ln("FRT-LOCAL", 3, ordered=4)], (), "Local cartage. Services are two-way matched: no goods receipt needed."),
    Scenario("C05", "clean", "V1005", [Ln("ADH-HM-EVA", 40)], (), "Hot-melt adhesive, matches PO and receipt."),
    Scenario("C06", "clean", "V1006", [Ln("FLM-STR-23", 96), Ln("FLM-STR-17H", 48)], (), "Machine and hand stretch film."),
    Scenario("C07", "clean", "V1007", [Ln("PAL-AUS-STD", 240)], (), "Standard pallets, fully receipted."),
    Scenario("C08", "clean", "V1008", [Ln("MRO-BRG-6205", 40), Ln("MRO-VBELT-B52", 12), Ln("MRO-GRS-LI2", 24), Ln("MRO-GLV-NIT", 30)], (), "Four-line maintenance consumables order."),
    Scenario("C09", "clean", "V1009", [Ln("LBL-PS-100150", 180)], (), "Labels priced per thousand."),
    Scenario("C10", "clean", "V1010", [Ln("SVC-PM-L3", 38, ordered=40), Ln("SVC-CALLOUT", 1)], (), "Maintenance hours under the PO cap, plus a call-out."),
    Scenario("C11", "clean", "V1011", [Ln("CHM-ACID-CIP", 6), Ln("CHM-SAN-PAA", 12)], (), "CIP chemicals."),
    Scenario("C12", "clean", "V1013", [Ln("ELEC-LAB", 22, ordered=40)], (), "Electrician hours, part of a larger PO."),
    Scenario("C13", "clean", "V1014", [Ln("FLM-BOPP-20", 24)], (), "BOPP film rolls."),
    Scenario("C14", "clean", "V1015", [Ln("GAS-N2-G", 18), Ln("GAS-RENT-G", 20)], (), "Mixed invoice: gas refills (three-way) plus cylinder rental (two-way)."),
    Scenario("C15", "clean", "V1002", [Ln("SHT-BC-1200", 3000, ordered=5000, received=(3000,))], (), "Partial delivery: 3,000 of 5,000 sheets received and billed."),
    Scenario("C16", "clean", "V1001", [Ln("RES-HDPE-BM", 5, ordered=10, prev_invoiced=5)], (), "Second delivery on a split PO. First half was received and invoiced in August."),
    Scenario("C17", "clean", "V1006", [Ln("FLM-STR-23", 120)], (), "Stretch film, single line."),
    Scenario("C18", "clean", "V1008", [Ln("MRO-VBELT-B52", 20), Ln("MRO-GLV-NIT", 50)], (), "Belts and gloves."),
    Scenario("C19", "clean", "V1004", [Ln("FRT-INTL-SEA", 1), Ln("FRT-WHARF", 1), Ln("FRT-LOCAL", 1)], (), "Import freight with a GST-free international leg correctly shown without GST."),
    # --- Variance inside tolerance: should still post ---------------------
    Scenario("T01", "within_tolerance", "V1005", [Ln("ADH-HM-EVA", 40, price=D("97.44")), Ln("ADH-PVA-CS", 1)], (), "Adhesive billed 1.5% over PO ($57.60): inside the 2% / $250 tolerance."),
    Scenario("T02", "within_tolerance", "V1009", [Ln("LBL-SHIP-A6", 150, price=D("18.75"))], (), "Labels billed 1.9% over PO ($52.50): inside tolerance."),
    # --- Clean but high value: pauses for approval on amount alone ---------
    Scenario("H01", "high_value", "V1001", [Ln("RES-PET-BTL", 20)], (), "Clean, but $39k: needs AP supervisor sign-off."),
    Scenario("H02", "high_value", "V1012", [Ln("TOOL-MLD-PF28", 1), Ln("TOOL-SPR-KIT", 1)], (), "Clean, but $134k preform mould: needs finance manager sign-off."),
    Scenario("H03", "high_value", "V1002", [Ln("CTN-RSC-400", 18000), Ln("CTN-DIV-12", 5000)], (), "Clean, but $24k: needs AP supervisor sign-off."),
    # --- Price variance ----------------------------------------------------
    Scenario("P01", "price_variance", "V1003", [Ln("INK-FLX-CY", 150, price=D("12.90")), Ln("INK-FLX-BK", 100)], ("price_variance",), "Cyan ink billed 4.5% over PO: breaches the percentage limit."),
    Scenario("P02", "price_variance", "V1014", [Ln("FLM-BOPP-20", 30, price=D("281.00")), Ln("FLM-CPP-30", 10)], ("price_variance",), "Vendor applied a 6% price rise the PO doesn't reflect."),
    Scenario("P03", "price_variance", "V1011", [Ln("CHM-NAOH-30", 18000, price=D("1.450"))], ("price_variance",), "Only 1.75% over, but on 18,000 L that's $450: breaches the $250 dollar cap."),
    # --- Short-shipped -----------------------------------------------------
    Scenario("S01", "short_shipped", "V1007", [Ln("PAL-AUS-STD", 300, received=(280,), gr_note="20 pallets rejected at receipt: broken bearers")], ("short_shipped",), "Billed 300 pallets; 20 were rejected at the dock."),
    Scenario("S02", "short_shipped", "V1006", [Ln("FLM-STR-23", 120, received=(96,))], ("short_shipped",), "Billed 120 rolls, 96 arrived."),
    Scenario("S03", "short_shipped", "V1015", [Ln("GAS-N2-G", 12, received=(10,)), Ln("GAS-RENT-G", 12)], ("short_shipped",), "Billed 12 refills, 10 cylinders delivered. Rental line is fine."),
    # --- Duplicates --------------------------------------------------------
    Scenario("D01", "duplicate", "V1002", [Ln("CTN-RSC-400", 4400, prev_invoiced=4400, received=(4400,))], ("duplicate_invoice",),
             "Exact resend of an invoice already posted in August.", ledger_number="INV-004417", invoice_date="2026-08-14"),
    Scenario("D02", "duplicate", "V1008", [Ln("MRO-BRG-6205", 30, prev_invoiced=30, received=(30,)), Ln("MRO-GRS-LI2", 36, prev_invoiced=36, received=(36,))], ("duplicate_invoice",),
             "Same invoice as one keyed in August as '3321'; this copy says 'LIS-0003321'.", ledger_number="3321", invoice_date="2026-08-20"),
    # --- Missing goods receipt ---------------------------------------------
    Scenario("M01", "missing_gr", "V1001", [Ln("RES-PP-HOMO", 6, received=())], ("missing_goods_receipt",), "Invoice arrived before the warehouse receipted the resin."),
    Scenario("M02", "missing_gr", "V1009", [Ln("LBL-PS-100150", 120, received=())], ("missing_goods_receipt",), "Labels billed, nothing receipted."),
    Scenario("M03", "missing_gr", "V1014", [Ln("FLM-CPP-30", 18, ordered=36, prev_invoiced=18, received=(18,))], ("missing_goods_receipt",),
             "Split PO: first 18 rolls received and invoiced; this bills the next 18, which haven't been receipted."),
    # --- Unknown vendor ----------------------------------------------------
    Scenario("U01", "unknown_vendor", None, [Ln("SVC-GBX-C4", 1), Ln("SVC-CALL", 1)], ("unknown_vendor",),
             "New contractor engaged by the plant with no PO and no vendor record.", has_po=False,
             unknown=UnknownVendor(
                 "Geelong Precision Maintenance Pty Ltd", ("77 Gearbox Street", "Moolap VIC 3224"),
                 "jobs@geelongprecision.example", "services", "GPM-0142", "#3d3d3d",
                 (Item("SVC-GBX-C4", "Gearbox rebuild - conveyor 4", "ea", D("3860.00"), line_type="service"),
                  Item("SVC-CALL", "Call-out and travel", "ea", D("240.00"), line_type="service")))),
    Scenario("U02", "unknown_vendor", None, [Ln("ADH-HM-EVA", 60)], ("unknown_vendor",),
             "Looks like Otway Adhesives, quotes a real Otway PO, but the ABN differs and it asks for payment to new bank details.",
             po_of="T01", remarks="Please note our bank details have changed. Updated account details are on the attached letter. Please update your records before the next payment run.",
             unknown=UnknownVendor(
                 "Otway Adhesives Pty Ltd", ("5 Tack Place", "North Geelong VIC 3215"),
                 "accounts@otway-adhesives-au.example", "modern", "OA-{n:05d}", "#a0522d",
                 (Item("ADH-HM-EVA", "Hot-melt adhesive EVA, 20 kg bag", "bag", D("96.00")),))),
    # --- GST errors --------------------------------------------------------
    Scenario("G01", "gst_error", "V1004", [Ln("FRT-INTL-SEA", 1, charge_gst=True), Ln("FRT-WHARF", 1)], ("gst_error",),
             "GST charged on the international sea-freight leg, which is GST-free."),
    Scenario("G02", "gst_error", "V1013", [Ln("ELEC-SWBD", 1), Ln("ELEC-LAB", 24, ordered=40)], ("gst_error",),
             "GST keyed as $1,286.20 instead of $1,268.20 (transposed digits).", gst_override=D("1286.20")),
    # --- More than one problem ---------------------------------------------
    Scenario("X01", "multiple", "V1008", [Ln("MRO-BRG-6205", 60, price=D("15.90")), Ln("MRO-GRS-LI2", 48, received=(36,))], ("price_variance", "short_shipped"),
             "Bearings billed 7.4% over PO, and 48 tubes of grease billed with only 36 received."),
]
