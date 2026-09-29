"""Paths and YAML-backed settings."""

from __future__ import annotations

from decimal import Decimal
from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
DATA_DIR = ROOT / "data"
MASTER_DIR = DATA_DIR / "master"
INVOICE_DIR = DATA_DIR / "invoices"
REPLAY_DIR = DATA_DIR / "replays"


class PriceTolerance(BaseModel):
    pct: Decimal
    abs_per_line: Decimal


class QuantityTolerance(BaseModel):
    over_receipt_pct: Decimal = Decimal("0")


class GSTConfig(BaseModel):
    rate: Decimal
    rounding: Decimal


class DuplicateConfig(BaseModel):
    window_days: int


class ArithmeticConfig(BaseModel):
    tolerance: Decimal


class Tolerances(BaseModel):
    price: PriceTolerance
    quantity: QuantityTolerance
    gst: GSTConfig
    duplicates: DuplicateConfig
    arithmetic: ArithmeticConfig


class Company(BaseModel):
    name: str
    abn: str
    address: list[str]
    ap_email: str


def _load_yaml(name: str) -> dict:
    with open(CONFIG_DIR / name) as f:
        return yaml.safe_load(f)


@lru_cache
def load_tolerances() -> Tolerances:
    return Tolerances.model_validate(_load_yaml("tolerances.yaml"))


@lru_cache
def load_company() -> Company:
    return Company.model_validate(_load_yaml("company.yaml"))
