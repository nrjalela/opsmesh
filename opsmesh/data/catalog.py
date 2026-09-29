"""Synthetic vendor master and item catalogue for Corio Packaging.

Every name, ABN, address and email here is SYNTHETIC. ABNs are generated to
pass the ATO checksum, so one could coincide with a real business by chance.
Email domains use the reserved `.example` TLD.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal as D


@dataclass(frozen=True)
class Item:
    code: str
    description: str
    uom: str
    price: D
    tax_code: str = "GST"
    line_type: str = "goods"


@dataclass(frozen=True)
class VendorSpec:
    vendor_id: str
    name: str
    category: str
    terms: str
    template: str  # PDF layout the vendor's billing system produces
    number_format: str  # invoice-number style, {n} = running number
    address: tuple[str, ...]
    email: str
    colour: str
    items: tuple[Item, ...]


VENDORS: tuple[VendorSpec, ...] = (
    VendorSpec(
        "V1001", "Barwon Polymers Pty Ltd", "Resin", "EOM30", "classic", "BP-{n:05d}",
        ("7 Resin Court", "Lara VIC 3212"), "accounts@barwonpolymers.example", "#1f4e79",
        (
            Item("RES-PET-BTL", "PET bottle-grade resin", "t", D("1780.00")),
            Item("RES-HDPE-BM", "HDPE blow-moulding resin", "t", D("1965.00")),
            Item("RES-PP-HOMO", "PP homopolymer resin", "t", D("1690.00")),
        ),
    ),
    VendorSpec(
        "V1002", "Surf Coast Corrugated Pty Ltd", "Corrugated", "EOM30", "modern", "INV-{n:06d}",
        ("22 Fluting Way", "Breakwater VIC 3219"), "ar@surfcoastcorrugated.example", "#8a5a2b",
        (
            Item("CTN-RSC-400", "RSC carton 400x300x250 C-flute", "ea", D("1.12")),
            Item("CTN-DIV-12", "12-cell carton divider", "ea", D("0.38")),
            Item("SHT-BC-1200", "B/C double-wall sheet 1200x1000", "ea", D("2.95")),
        ),
    ),
    VendorSpec(
        "V1003", "Bellarine Inks & Coatings Pty Ltd", "Inks", "NET30", "classic", "BIC-{n:05d}",
        ("3 Pigment Street", "Moolap VIC 3224"), "invoices@bellarineinks.example", "#6b2f6b",
        (
            Item("INK-FLX-CY", "Flexo process ink - cyan", "kg", D("12.35")),
            Item("INK-FLX-MG", "Flexo process ink - magenta", "kg", D("12.35")),
            Item("INK-FLX-YL", "Flexo process ink - yellow", "kg", D("11.80")),
            Item("INK-FLX-BK", "Flexo process ink - black", "kg", D("10.90")),
            Item("VAR-OPV-W", "Water-based overprint varnish", "kg", D("8.60")),
        ),
    ),
    VendorSpec(
        "V1004", "Corio Bay Freight Pty Ltd", "Freight", "NET14", "services", "CBF-{n:04d}",
        ("110 Wharf Access Road", "Corio VIC 3214"), "billing@coriobayfreight.example", "#0f5c5c",
        (
            Item("FRT-LOCAL", "Local cartage - Corio to Laverton North, B-double", "trip", D("1150.00"), line_type="service"),
            Item("FRT-INTL-SEA", "International sea freight - Ningbo to Melbourne, 20ft", "ctr", D("2480.00"), tax_code="FRE", line_type="service"),
            Item("FRT-WHARF", "Wharf cartage and container handling", "ea", D("385.00"), line_type="service"),
        ),
    ),
    VendorSpec(
        "V1005", "Otway Adhesives Pty Ltd", "Adhesives", "NET30", "modern", "OA-{n:05d}",
        ("5 Tack Place", "North Geelong VIC 3215"), "accounts@otwayadhesives.example", "#a0522d",
        (
            Item("ADH-HM-EVA", "Hot-melt adhesive EVA, 20 kg bag", "bag", D("96.00")),
            Item("ADH-PVA-CS", "PVA case-seal adhesive, 1000 L IBC", "ea", D("2340.00")),
        ),
    ),
    VendorSpec(
        "V1006", "Norlane Stretch Films Pty Ltd", "Films", "EOM30", "compact", "NSF{n:06d}",
        ("41 Cling Road", "Norlane VIC 3214"), "ar@norlanefilms.example", "#333333",
        (
            Item("FLM-STR-23", "Machine stretch film 23um x 500mm", "roll", D("38.50")),
            Item("FLM-STR-17H", "Hand stretch film 17um x 450mm", "roll", D("21.90")),
        ),
    ),
    VendorSpec(
        "V1007", "Moorabool Pallets Pty Ltd", "Pallets", "NET30", "compact", "MP-{n:04d}",
        ("9 Bearer Lane", "Batesford VIC 3213"), "office@mooraboolpallets.example", "#333333",
        (
            Item("PAL-AUS-STD", "Timber pallet 1165x1165 standard", "ea", D("24.00")),
            Item("PAL-EXP-HT", "Heat-treated export pallet 1200x1000", "ea", D("31.50")),
        ),
    ),
    VendorSpec(
        "V1008", "Limeburners Industrial Supplies Pty Ltd", "MRO", "NET30", "classic", "LIS-{n:07d}",
        ("16 Spanner Street", "Geelong East VIC 3219"), "accounts@limeburnersindustrial.example", "#2e5e2e",
        (
            Item("MRO-BRG-6205", "Deep groove bearing 6205-2RS", "ea", D("14.80")),
            Item("MRO-VBELT-B52", "V-belt B52", "ea", D("22.40")),
            Item("MRO-GRS-LI2", "Lithium grease EP2, 450 g", "ea", D("9.75")),
            Item("MRO-GLV-NIT", "Nitrile gloves, box of 100", "box", D("11.20")),
        ),
    ),
    VendorSpec(
        "V1009", "Point Henry Labels Pty Ltd", "Labels", "NET30", "modern", "PHL-{n:05d}",
        ("2 Die-Cut Drive", "Moolap VIC 3224"), "billing@pointhenrylabels.example", "#b03a2e",
        (
            Item("LBL-PS-100150", "PS label 100x150, per 1000", "1000", D("21.00")),
            Item("LBL-SHIP-A6", "Shipping label A6, per 1000", "1000", D("18.40")),
        ),
    ),
    VendorSpec(
        "V1010", "Anakie Engineering Services Pty Ltd", "Maintenance", "NET30", "services", "AES-{n:04d}",
        ("58 Lathe Road", "Lara VIC 3212"), "admin@anakieengineering.example", "#44546a",
        (
            Item("SVC-PM-L3", "Preventive maintenance - Line 3 blow moulder", "hr", D("135.00"), line_type="service"),
            Item("SVC-CALLOUT", "Emergency call-out fee", "ea", D("280.00"), line_type="service"),
        ),
    ),
    VendorSpec(
        "V1011", "Hovells Creek Chemicals Pty Ltd", "Chemicals", "NET30", "compact", "HCC/{n:05d}",
        ("12 Reagent Road", "Lara VIC 3212"), "accounts@hovellscreekchem.example", "#333333",
        (
            Item("CHM-NAOH-30", "Caustic soda 30% bulk", "L", D("1.425")),
            Item("CHM-ACID-CIP", "Acid CIP detergent, 200 L drum", "drum", D("412.00")),
            Item("CHM-SAN-PAA", "Peracetic acid sanitiser, 20 L", "ea", D("96.50")),
        ),
    ),
    VendorSpec(
        "V1012", "Barrabool Tooling Pty Ltd", "Tooling", "NET30", "classic", "BT-{n:04d}",
        ("30 Cavity Crescent", "Waurn Ponds VIC 3216"), "finance@barrabooltooling.example", "#5b3a29",
        (
            Item("TOOL-MLD-PF28", "8-cavity preform mould, 28 mm neck", "set", D("118000.00")),
            Item("TOOL-SPR-KIT", "Mould spares kit", "ea", D("3450.00")),
        ),
    ),
    VendorSpec(
        "V1013", "Leopold Electrical Contractors Pty Ltd", "Electrical", "NET14", "services", "LEC-{n:04d}",
        ("7 Circuit Place", "Leopold VIC 3224"), "accounts@leopoldelectrical.example", "#7a6a00",
        (
            Item("ELEC-LAB", "Electrician labour", "hr", D("118.00"), line_type="service"),
            Item("ELEC-SWBD", "Switchboard upgrade - Building B, fixed price", "ea", D("9850.00"), line_type="service"),
        ),
    ),
    VendorSpec(
        "V1014", "Portarlington Packaging Films Pty Ltd", "Films", "EOM30", "modern", "PPF-{n:05d}",
        ("19 Extrusion Avenue", "Portarlington VIC 3223"), "ar@portarlingtonfilms.example", "#2c5f8a",
        (
            Item("FLM-BOPP-20", "BOPP film 20um x 1000mm, 6000 m roll", "roll", D("265.00")),
            Item("FLM-CPP-30", "CPP sealant film 30um x 1000mm", "roll", D("288.00")),
        ),
    ),
    VendorSpec(
        "V1015", "You Yangs Gas & Welding Pty Ltd", "Gases", "NET30", "compact", "YYG{n:05d}",
        ("4 Cylinder Street", "Little River VIC 3211"), "accounts@youyangsgas.example", "#333333",
        (
            Item("GAS-N2-G", "Nitrogen, G-size cylinder refill", "ea", D("64.50")),
            Item("GAS-RENT-G", "Cylinder rental, G-size (monthly)", "ea", D("12.80"), line_type="service"),
        ),
    ),
)

VENDOR_BY_ID = {v.vendor_id: v for v in VENDORS}

BUYERS = ("S. Kowalski", "M. Tran", "J. Okafor", "R. Delaney")


def item(vendor_id: str, code: str) -> Item:
    return next(i for i in VENDOR_BY_ID[vendor_id].items if i.code == code)
