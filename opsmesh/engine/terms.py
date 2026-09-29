from __future__ import annotations

import calendar
from datetime import date, timedelta

TERMS_TEXT = {
    "NET14": "14 days from invoice date",
    "NET30": "30 days from invoice date",
    "EOM30": "30 days from end of month",
}


def due_date(invoice_date: date, terms: str) -> date:
    if terms == "NET14":
        return invoice_date + timedelta(days=14)
    if terms == "NET30":
        return invoice_date + timedelta(days=30)
    if terms == "EOM30":
        last = calendar.monthrange(invoice_date.year, invoice_date.month)[1]
        return date(invoice_date.year, invoice_date.month, last) + timedelta(days=30)
    raise ValueError(f"Unknown payment terms {terms!r}")
