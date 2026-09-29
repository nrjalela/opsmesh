"""Generate the synthetic Corio Packaging dataset.

    python -m opsmesh.data.generate

Writes vendor master, POs, goods receipts, AP ledger history, 40 invoice PDFs
and the answer key. Seeded, so the output is identical on every run.
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal as D
from pathlib import Path

from opsmesh.config import DATA_DIR, INVOICE_DIR, MASTER_DIR, load_company, load_tolerances
from opsmesh.data.catalog import BUYERS, VENDOR_BY_ID, VENDORS, Item, VendorSpec
from opsmesh.data.pdf import PrintedInvoice, PrintedLine, render_invoice
from opsmesh.data.scenarios import AUTO, SCENARIOS, Ln, Scenario
from opsmesh.engine.abn import generate_abn
from opsmesh.engine.master import MasterData
from opsmesh.engine.matching import match_invoice
from opsmesh.engine.models import (
    GoodsReceipt, GRLine, InvoiceDocument, InvoiceLine, LedgerLine, POLine, PostedInvoice, PurchaseOrder, Vendor,
)
from opsmesh.engine.money import cents
from opsmesh.engine.terms import due_date

SEED = 20260929
GST = D("0.10")
BATCH_START = date(2026, 9, 1)
BATCH_DAYS = 25

# Templates that print these identifiers on each line
PRINTS_ITEM_CODE = {"classic", "modern", "compact"}
PRINTS_PO_LINE = {"compact"}


@dataclass
class Built:
    scenario: Scenario
    doc_id: str
    received_date: date
    invoice: InvoiceDocument
    printed: PrintedInvoice


class Generator:
    def __init__(self, seed: int = SEED):
        self.rng = random.Random(seed)
        self.company = load_company()
        self.vendors: dict[str, Vendor] = {}
        self.pos: list[PurchaseOrder] = []
        self.grs: list[GoodsReceipt] = []
        self.ledger: list[PostedInvoice] = []
        self.po_seq = 4500012001
        self.gr_seq = 5000034001
        self.doc_seq = 5105000101
        self.inv_seq: dict[str, int] = {}
        self.po_by_scenario: dict[str, PurchaseOrder] = {}

    # --- sequences -----------------------------------------------------------
    def next_po(self) -> str:
        self.po_seq += self.rng.randint(1, 4)
        return str(self.po_seq)

    def next_gr(self) -> str:
        self.gr_seq += self.rng.randint(1, 6)
        return str(self.gr_seq)

    def next_doc(self) -> str:
        self.doc_seq += self.rng.randint(1, 9)
        return str(self.doc_seq)

    def next_inv(self, spec: VendorSpec) -> str:
        self.inv_seq[spec.vendor_id] += self.rng.randint(1, 12)
        return spec.number_format.format(n=self.inv_seq[spec.vendor_id])

    # --- master data -----------------------------------------------------------
    def build_vendors(self) -> None:
        for spec in VENDORS:
            self.vendors[spec.vendor_id] = Vendor(
                vendor_id=spec.vendor_id, name=spec.name, abn=generate_abn(self.rng),
                payment_terms=spec.terms, category=spec.category, email=spec.email, address=list(spec.address),
            )
            self.inv_seq[spec.vendor_id] = self.rng.randint(1200, 9000)
        # Fixed numbers used by the duplicate scenarios sit inside each vendor's sequence
        self.inv_seq["V1002"] = 4380
        self.inv_seq["V1008"] = 3290

    def skip_fixed_numbers(self) -> None:
        """Keep new invoice numbers clear of the ones the duplicate scenarios reuse."""
        for sc in SCENARIOS:
            if sc.ledger_number and sc.vendor_id:
                fixed = int("".join(c for c in sc.ledger_number if c.isdigit()))
                self.inv_seq[sc.vendor_id] = max(self.inv_seq[sc.vendor_id], fixed) + 3

    def build_background_history(self) -> None:
        """Two closed POs per vendor from July: fully received, invoiced and posted."""
        for spec in VENDORS:
            for _ in range(2):
                inv_date = date(2026, 7, self.rng.randint(1, 28))
                picks = self.rng.sample(spec.items, k=min(len(spec.items), self.rng.randint(1, 2)))
                lines = []
                for n, it in enumerate(picks, 1):
                    q = D(self._background_qty(it))
                    lines.append(POLine(line_no=n * 10, item_code=it.code, description=it.description, quantity=q,
                                        uom=it.uom, unit_price=it.price, tax_code=it.tax_code, line_type=it.line_type))
                po = PurchaseOrder(po_number=self.next_po(), vendor_id=spec.vendor_id,
                                   order_date=inv_date - timedelta(days=self.rng.randint(15, 30)),
                                   buyer=self.rng.choice(BUYERS), lines=lines)
                self.pos.append(po)
                goods = [ln for ln in lines if ln.line_type == "goods"]
                if goods:
                    self.grs.append(GoodsReceipt(
                        gr_number=self.next_gr(), po_number=po.po_number,
                        receipt_date=inv_date - timedelta(days=self.rng.randint(1, 5)),
                        lines=[GRLine(po_line=ln.line_no, quantity=ln.quantity) for ln in goods]))
                total = self._total([(ln.quantity, ln.unit_price, ln.tax_code == "GST") for ln in lines])
                self.ledger.append(PostedInvoice(
                    document_number=self.next_doc(), vendor_id=spec.vendor_id, invoice_number=self.next_inv(spec),
                    invoice_date=inv_date, posted_date=inv_date + timedelta(days=self.rng.randint(2, 6)),
                    po_number=po.po_number, total=total,
                    lines=[LedgerLine(po_line=ln.line_no, quantity=ln.quantity) for ln in lines]))

    def _background_qty(self, it: Item) -> int:
        if it.price >= 1000:
            return self.rng.randint(1, 4)
        if it.price >= 100:
            return self.rng.randint(4, 20)
        if it.price >= 5:
            return self.rng.randint(20, 150)
        return self.rng.randint(8, 40) * 100

    @staticmethod
    def _total(rows: list[tuple[D, D, bool]]) -> D:
        sub = sum((cents(q * p) for q, p, _ in rows), D("0"))
        tax = cents(sum((cents(q * p) for q, p, t in rows if t), D("0")) * GST)
        return sub + tax

    # --- scenarios -------------------------------------------------------------
    def assign_dates(self) -> list[tuple[Scenario, date, date]]:
        order = SCENARIOS[:]
        self.rng.shuffle(order)
        out = []
        for i, sc in enumerate(order):
            received = BATCH_START + timedelta(days=round(i * BATCH_DAYS / len(order)))
            if sc.invoice_date:
                inv_date = date.fromisoformat(sc.invoice_date)
            else:
                inv_date = received - timedelta(days=self.rng.randint(0, 3))
            out.append((sc, inv_date, received))
        return out

    def build_scenario(self, sc: Scenario, inv_date: date, received: date, doc_id: str) -> Built:
        unknown = sc.unknown
        spec = VENDOR_BY_ID[sc.vendor_id] if sc.vendor_id else None
        items = {it.code: it for it in (unknown.items if unknown else spec.items)}

        # PO -------------------------------------------------------------
        po: PurchaseOrder | None = None
        if sc.has_po and sc.po_of is None:
            lines = []
            for n, ln in enumerate(sc.lines, 1):
                it = items[ln.code]
                ordered = D(ln.ordered if ln.ordered is not None else D(ln.prev_invoiced) + D(ln.invoiced))
                lines.append(POLine(line_no=n * 10, item_code=it.code, description=it.description, quantity=ordered,
                                    uom=it.uom, unit_price=it.price, tax_code=it.tax_code, line_type=it.line_type))
            po = PurchaseOrder(po_number=self.next_po(), vendor_id=sc.vendor_id,
                               order_date=inv_date - timedelta(days=self.rng.randint(18, 40)),
                               buyer=self.rng.choice(BUYERS), lines=lines)
            self.pos.append(po)
            self.po_by_scenario[sc.key] = po
            self._build_receipts(sc, po, inv_date)
            self._build_prior_invoice(sc, spec, po, inv_date)
        po_number = po.po_number if po else (self.po_by_scenario[sc.po_of].po_number if sc.po_of else None)

        # Invoice as printed ------------------------------------------------
        if unknown:
            vendor_abn = unknown.abn or generate_abn(self.rng)
            vendor_name, template, colour = unknown.name, unknown.template, unknown.colour
            vendor_address, vendor_email, terms = unknown.address, unknown.email, "NET14"
            number = unknown.number.format(n=self.inv_seq["V1005"] + 37)
        else:
            v = self.vendors[sc.vendor_id]
            vendor_name, vendor_abn, template, colour = v.name, v.abn, spec.template, spec.colour
            vendor_address, vendor_email, terms = spec.address, spec.email, spec.terms
            if sc.ledger_number:
                number = spec.number_format.format(n=int("".join(c for c in sc.ledger_number if c.isdigit())))
            else:
                number = self.next_inv(spec)

        inv_lines, printed_lines = [], []
        for n, ln in enumerate(sc.lines, 1):
            it = items[ln.code]
            unit = ln.price if ln.price is not None else it.price
            q = D(ln.invoiced)
            amount = cents(q * unit)
            gst_applicable = ln.charge_gst if ln.charge_gst is not None else it.tax_code == "GST"
            inv_lines.append(InvoiceLine(
                description=it.description,
                item_code=it.code if template in PRINTS_ITEM_CODE else None,
                po_line=n * 10 if (template in PRINTS_PO_LINE and po_number) else None,
                quantity=q, uom=it.uom, unit_price=unit, amount=amount, gst_applicable=gst_applicable,
            ))
            printed_lines.append(PrintedLine(
                code=it.code, po_line=n * 10 if po_number else None, description=it.description, qty=q, uom=it.uom,
                unit_price=unit, amount=amount, gst_applicable=gst_applicable,
                gst=cents(amount * GST) if gst_applicable else D("0.00"),
            ))
        subtotal = sum((l.amount for l in inv_lines), D("0"))
        gst = sc.gst_override if sc.gst_override is not None else cents(
            sum((l.amount for l in inv_lines if l.gst_applicable), D("0")) * GST)
        invoice = InvoiceDocument(
            vendor_name=vendor_name, vendor_abn=vendor_abn, invoice_number=number, invoice_date=inv_date,
            po_number=po_number, lines=inv_lines, subtotal=subtotal, gst_amount=gst, total=subtotal + gst,
            remarks=sc.remarks,
        )
        printed = PrintedInvoice(
            doc_id=doc_id, template=template, colour=colour, vendor_name=vendor_name, vendor_abn=vendor_abn,
            vendor_address=tuple(vendor_address), vendor_email=vendor_email, invoice_number=number,
            invoice_date=inv_date, due_date=due_date(inv_date, terms), terms=terms, po_number=po_number,
            lines=printed_lines, subtotal=subtotal, gst=gst, total=subtotal + gst, remarks=sc.remarks,
            buyer=self.company, docket=f"DD{self.rng.randint(100000, 999999)}",
        )

        if sc.ledger_number:  # the original this duplicate repeats
            self.ledger.append(PostedInvoice(
                document_number=self.next_doc(), vendor_id=sc.vendor_id, invoice_number=sc.ledger_number,
                invoice_date=inv_date, posted_date=inv_date + timedelta(days=4), po_number=po_number,
                total=invoice.total,
                lines=[LedgerLine(po_line=(i + 1) * 10, quantity=D(ln.prev_invoiced)) for i, ln in enumerate(sc.lines)],
            ))
        return Built(sc, doc_id, received, invoice, printed)

    def _build_receipts(self, sc: Scenario, po: PurchaseOrder, inv_date: date) -> None:
        deliveries: dict[int, list[GRLine]] = {}
        for n, ln in enumerate(sc.lines, 1):
            pol = po.line(n * 10)
            if pol.line_type != "goods":
                continue
            if ln.received == AUTO:
                qtys = [D(ln.prev_invoiced), D(ln.invoiced)] if ln.prev_invoiced else [D(ln.invoiced)]
            else:
                qtys = [D(q) for q in ln.received]
            for k, q in enumerate(qtys):
                note = ln.gr_note if k == len(qtys) - 1 else None
                deliveries.setdefault(k, []).append(GRLine(po_line=pol.line_no, quantity=q, note=note))
        split = any(ln.prev_invoiced for ln in sc.lines) and not sc.ledger_number
        for k, grl in sorted(deliveries.items()):
            old = split and k == 0
            when = inv_date - timedelta(days=self.rng.randint(32, 38) if old else self.rng.randint(1, 6))
            self.grs.append(GoodsReceipt(gr_number=self.next_gr(), po_number=po.po_number, receipt_date=when, lines=grl))

    def _build_prior_invoice(self, sc: Scenario, spec: VendorSpec, po: PurchaseOrder, inv_date: date) -> None:
        if sc.ledger_number or not any(ln.prev_invoiced for ln in sc.lines):
            return
        rows, lines = [], []
        for n, ln in enumerate(sc.lines, 1):
            if ln.prev_invoiced:
                pol = po.line(n * 10)
                rows.append((D(ln.prev_invoiced), pol.unit_price, pol.tax_code == "GST"))
                lines.append(LedgerLine(po_line=pol.line_no, quantity=D(ln.prev_invoiced)))
        prior_date = inv_date - timedelta(days=self.rng.randint(28, 31))
        self.ledger.append(PostedInvoice(
            document_number=self.next_doc(), vendor_id=spec.vendor_id, invoice_number=self.next_inv(spec),
            invoice_date=prior_date, posted_date=prior_date + timedelta(days=3), po_number=po.po_number,
            total=self._total(rows), lines=lines,
        ))

    # --- run -------------------------------------------------------------------
    def run(self) -> list[Built]:
        self.build_vendors()
        self.build_background_history()
        self.skip_fixed_numbers()
        dated = sorted(self.assign_dates(), key=lambda t: (t[2], t[0].key))
        # POs must exist before a scenario can quote another's PO number
        dated.sort(key=lambda t: t[0].po_of is not None)
        built = []
        for sc, inv_date, received in dated:
            built.append(self.build_scenario(sc, inv_date, received, doc_id=""))
        built.sort(key=lambda b: (b.received_date, b.scenario.key))
        for i, b in enumerate(built, 1):
            b.doc_id = b.printed.doc_id = f"OPS-{i:04d}"
        self.pos.sort(key=lambda p: p.po_number)
        self.grs.sort(key=lambda g: g.gr_number)
        self.ledger.sort(key=lambda l: l.document_number)
        return built


def _dump(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, default=str) + "\n")


def main() -> None:
    gen = Generator()
    built = gen.run()

    _dump(MASTER_DIR / "vendors.json", [v.model_dump(mode="json") for v in gen.vendors.values()])
    _dump(MASTER_DIR / "purchase_orders.json", [p.model_dump(mode="json") for p in gen.pos])
    _dump(MASTER_DIR / "goods_receipts.json", [g.model_dump(mode="json") for g in gen.grs])
    _dump(MASTER_DIR / "ap_ledger.json", [l.model_dump(mode="json") for l in gen.ledger])

    INVOICE_DIR.mkdir(parents=True, exist_ok=True)
    for old in INVOICE_DIR.glob("OPS-*.pdf"):
        old.unlink()
    index, answer_key = [], {}
    for b in built:
        render_invoice(b.printed, INVOICE_DIR / f"{b.doc_id}.pdf")
        index.append({"doc_id": b.doc_id, "file": f"{b.doc_id}.pdf", "received_date": b.received_date.isoformat()})
        answer_key[b.doc_id] = {
            "scenario": b.scenario.key,
            "category": b.scenario.category,
            "description": b.scenario.description,
            "expected_exceptions": list(b.scenario.expected),
            "invoice": b.invoice.model_dump(mode="json"),
        }
    _dump(INVOICE_DIR / "index.json", index)
    _dump(DATA_DIR / "answer_key.json", answer_key)

    # Self-check: the engine must find exactly what each scenario seeded.
    master = MasterData.load(MASTER_DIR)
    tol = load_tolerances()
    bad = []
    for b in built:
        got = [t.value for t in match_invoice(b.invoice, master, tol).exception_types]
        if sorted(got) != sorted(b.scenario.expected):
            bad.append(f"{b.doc_id} {b.scenario.key}: expected {list(b.scenario.expected)}, got {got}")
    print(f"Wrote {len(built)} invoices, {len(gen.vendors)} vendors, {len(gen.pos)} POs, "
          f"{len(gen.grs)} goods receipts, {len(gen.ledger)} ledger entries.")
    if bad:
        raise SystemExit("Engine disagrees with the answer key:\n  " + "\n  ".join(bad))
    print("Engine agrees with the answer key on all invoices.")


if __name__ == "__main__":
    main()
