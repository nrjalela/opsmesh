"""The generated demo dataset is consistent with its own answer key."""

from __future__ import annotations

import json
from collections import Counter

import pypdfium2 as pdfium
import pytest

from opsmesh.config import DATA_DIR, INVOICE_DIR, MASTER_DIR, load_tolerances
from opsmesh.data.generate import Generator
from opsmesh.engine.abn import is_valid_abn
from opsmesh.engine.master import MasterData
from opsmesh.engine.matching import match_invoice
from opsmesh.engine.models import InvoiceDocument

ANSWER_KEY = json.loads((DATA_DIR / "answer_key.json").read_text())
MASTER = MasterData.load(MASTER_DIR)
SEEDED = {"price_variance", "short_shipped", "duplicate_invoice", "missing_goods_receipt", "unknown_vendor", "gst_error"}


@pytest.mark.parametrize("doc_id", sorted(ANSWER_KEY))
def test_engine_agrees_with_answer_key(doc_id):
    entry = ANSWER_KEY[doc_id]
    inv = InvoiceDocument.model_validate(entry["invoice"])
    got = [t.value for t in match_invoice(inv, MASTER, load_tolerances()).exception_types]
    assert sorted(got) == sorted(entry["expected_exceptions"]), entry["description"]


def test_batch_shape():
    assert len(ANSWER_KEY) == 40
    seen = Counter(t for e in ANSWER_KEY.values() for t in e["expected_exceptions"])
    assert set(seen) == SEEDED
    assert all(seen[t] >= 2 for t in SEEDED)
    clean = [e for e in ANSWER_KEY.values() if not e["expected_exceptions"]]
    assert len(clean) == 24


def test_vendor_master_abns_are_checksum_valid():
    assert len(MASTER.vendors) == 15
    assert all(is_valid_abn(v.abn) for v in MASTER.vendors)


def test_every_invoice_pdf_exists_and_is_marked_synthetic():
    index = json.loads((INVOICE_DIR / "index.json").read_text())
    assert [i["doc_id"] for i in index] == sorted(ANSWER_KEY)
    for item in index:
        pdf = pdfium.PdfDocument(INVOICE_DIR / item["file"])
        text = pdf[0].get_textpage().get_text_range()
        assert "SYNTHETIC DOCUMENT" in text
        assert ANSWER_KEY[item["doc_id"]]["invoice"]["invoice_number"] in text


def test_generator_is_deterministic():
    a = [b.invoice.model_dump() for b in Generator().run()]
    b = [b.invoice.model_dump() for b in Generator().run()]
    assert a == b
