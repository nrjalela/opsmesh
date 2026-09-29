from datetime import date

import pytest

from opsmesh.engine.abn import format_abn, is_valid_abn
from opsmesh.engine.terms import due_date


@pytest.mark.parametrize("abn", ["51 824 753 556", "51824753556", "83 914 571 673"])
def test_valid_abns(abn):
    assert is_valid_abn(abn)


@pytest.mark.parametrize("abn", ["51 824 753 557", "12345678901", "5182475355", "", None, "01824753556"])
def test_invalid_abns(abn):
    assert not is_valid_abn(abn)


def test_format_abn():
    assert format_abn("51824753556") == "51 824 753 556"


@pytest.mark.parametrize("terms,inv,due", [
    ("NET14", date(2026, 9, 10), date(2026, 9, 24)),
    ("NET30", date(2026, 9, 10), date(2026, 10, 10)),
    ("EOM30", date(2026, 9, 10), date(2026, 10, 30)),
    ("EOM30", date(2026, 2, 3), date(2026, 3, 30)),
])
def test_due_dates(terms, inv, due):
    assert due_date(inv, terms) == due
