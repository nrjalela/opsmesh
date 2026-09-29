"""Read-only view over ERP master and transactional data."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

from opsmesh.engine.abn import normalise_abn
from opsmesh.engine.models import GoodsReceipt, PostedInvoice, PurchaseOrder, Vendor

_ENTITY_SUFFIXES = re.compile(r"\b(pty|ltd|limited|p/l|co|company|the)\b")


def normalise_name(name: str) -> str:
    n = re.sub(r"[^a-z0-9/ ]", " ", name.lower().replace("&", " and "))
    n = _ENTITY_SUFFIXES.sub(" ", n)
    return " ".join(n.split())


@dataclass
class MasterData:
    vendors: list[Vendor]
    purchase_orders: list[PurchaseOrder]
    goods_receipts: list[GoodsReceipt]
    ledger: list[PostedInvoice]
    _by_abn: dict[str, Vendor] = field(init=False, repr=False)
    _by_po: dict[str, PurchaseOrder] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._by_abn = {normalise_abn(v.abn): v for v in self.vendors}
        self._by_po = {po.po_number: po for po in self.purchase_orders}

    # --- loading -----------------------------------------------------------
    @classmethod
    def load(cls, folder: Path) -> "MasterData":
        def read(name: str) -> list:
            return json.loads((folder / name).read_text())

        return cls(
            vendors=[Vendor.model_validate(v) for v in read("vendors.json")],
            purchase_orders=[PurchaseOrder.model_validate(p) for p in read("purchase_orders.json")],
            goods_receipts=[GoodsReceipt.model_validate(g) for g in read("goods_receipts.json")],
            ledger=[PostedInvoice.model_validate(i) for i in read("ap_ledger.json")],
        )

    # --- lookups -----------------------------------------------------------
    def vendor(self, vendor_id: str) -> Vendor | None:
        return next((v for v in self.vendors if v.vendor_id == vendor_id), None)

    def vendor_by_abn(self, abn: str) -> Vendor | None:
        return self._by_abn.get(normalise_abn(abn))

    def vendor_by_name(self, name: str) -> Vendor | None:
        target = normalise_name(name)
        return next((v for v in self.vendors if normalise_name(v.name) == target), None)

    def po(self, po_number: str | None) -> PurchaseOrder | None:
        if not po_number:
            return None
        return self._by_po.get(re.sub(r"\D", "", po_number))

    def receipts_for(self, po_number: str, line_no: int) -> list[tuple[GoodsReceipt, Decimal, str | None]]:
        out = []
        for gr in self.goods_receipts:
            if gr.po_number != po_number:
                continue
            for ln in gr.lines:
                if ln.po_line == line_no:
                    out.append((gr, ln.quantity, ln.note))
        return out

    def received_qty(self, po_number: str, line_no: int) -> Decimal:
        return sum((q for _, q, _ in self.receipts_for(po_number, line_no)), Decimal("0"))

    def invoiced_qty(self, po_number: str, line_no: int) -> Decimal:
        total = Decimal("0")
        for inv in self.ledger:
            if inv.po_number != po_number:
                continue
            total += sum((ln.quantity for ln in inv.lines if ln.po_line == line_no), Decimal("0"))
        return total

    def ledger_for_vendor(self, vendor_id: str) -> list[PostedInvoice]:
        return [i for i in self.ledger if i.vendor_id == vendor_id]

    def po_summary(self) -> dict[str, dict]:
        """Ordered / received / invoiced per PO line — handy for the UI."""
        out: dict[str, dict] = defaultdict(dict)
        for po in self.purchase_orders:
            for ln in po.lines:
                out[po.po_number][ln.line_no] = {
                    "ordered": ln.quantity,
                    "received": self.received_qty(po.po_number, ln.line_no),
                    "invoiced": self.invoiced_qty(po.po_number, ln.line_no),
                }
        return dict(out)
