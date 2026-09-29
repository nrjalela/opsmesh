"""Australian Business Number (ABN) helpers.

The ATO checksum: subtract 1 from the first digit, weight the 11 digits by
(10, 1, 3, 5, 7, 9, 11, 13, 15, 17, 19), and the sum must divide by 89.
"""

from __future__ import annotations

import random

WEIGHTS = (10, 1, 3, 5, 7, 9, 11, 13, 15, 17, 19)


def normalise_abn(raw: str | None) -> str:
    return "".join(ch for ch in (raw or "") if ch.isdigit())


def is_valid_abn(raw: str | None) -> bool:
    digits = normalise_abn(raw)
    if len(digits) != 11 or digits[0] == "0":
        return False
    nums = [int(d) for d in digits]
    nums[0] -= 1
    return sum(w * n for w, n in zip(WEIGHTS, nums)) % 89 == 0


def format_abn(raw: str | None) -> str:
    d = normalise_abn(raw)
    if len(d) != 11:
        return raw or ""
    return f"{d[:2]} {d[2:5]} {d[5:8]} {d[8:]}"


def generate_abn(rng: random.Random) -> str:
    """A checksum-valid ABN. Synthetic: it may coincide with a real business."""
    while True:
        candidate = str(rng.randint(10, 99)) + "".join(
            str(rng.randint(0, 9)) for _ in range(9)
        )
        if is_valid_abn(candidate):
            return candidate
