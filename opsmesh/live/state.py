"""Durable state for live mode, kept in the `opsmesh-state` git branch.

Each Actions run starts on a blank machine, so anything that must outlive the
run is a file in that branch, and every change becomes a commit:

    checkpoints.sqlite  LangGraph checkpoints, so a held run can resume later
    ledger.json         invoices posted live (feeds the engine's duplicate check)
    hashes.json         SHA-256 of every PDF seen -> issue number
    audit.jsonl         append-only log of every event and decision
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from opsmesh.config import MASTER_DIR
from opsmesh.engine.master import MasterData
from opsmesh.engine.models import PostedInvoice

LOCAL_TZ = ZoneInfo("Australia/Sydney")  # the "day" for the daily cap is an Australian business day


def local_date(ts: datetime) -> str:
    return ts.astimezone(LOCAL_TZ).date().isoformat()


class StateStore:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    # --- paths -----------------------------------------------------------------------------
    @property
    def checkpoint_path(self) -> Path:
        return self.root / "checkpoints.sqlite"

    @property
    def _ledger(self) -> Path:
        return self.root / "ledger.json"

    @property
    def _hashes(self) -> Path:
        return self.root / "hashes.json"

    @property
    def _audit(self) -> Path:
        return self.root / "audit.jsonl"

    def connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.checkpoint_path, check_same_thread=False)

    # --- json helpers -------------------------------------------------------------------------
    def _read(self, path: Path, default):
        return json.loads(path.read_text()) if path.exists() else default

    def _write(self, path: Path, data) -> None:
        path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")

    # --- duplicate protection --------------------------------------------------------------------
    def hash_owner(self, sha256: str) -> int | None:
        return self._read(self._hashes, {}).get(sha256)

    def record_hash(self, sha256: str, issue: int) -> None:
        hashes = self._read(self._hashes, {})
        hashes.setdefault(sha256, issue)
        self._write(self._hashes, hashes)

    # --- audit ---------------------------------------------------------------------------------
    def audit(self, event: str, issue: int, now: datetime, **fields) -> dict:
        entry = {"ts": now.astimezone(timezone.utc).isoformat(timespec="seconds"),
                 "local_date": local_date(now), "event": event, "issue": issue, **fields}
        with self._audit.open("a") as f:
            f.write(json.dumps(entry, sort_keys=True) + "\n")
        return entry

    def events(self) -> list[dict]:
        if not self._audit.exists():
            return []
        return [json.loads(line) for line in self._audit.read_text().splitlines() if line.strip()]

    def processed_on(self, day: str) -> int:
        """Invoices that reached Claude on this local date (what the daily cap limits)."""
        return sum(1 for e in self.events() if e["event"] == "processed" and e["local_date"] == day)

    def has_run(self, issue: int) -> bool:
        return any(e["event"] == "processed" and e["issue"] == issue for e in self.events())

    # --- live ledger -----------------------------------------------------------------------------
    def ledger(self) -> list[PostedInvoice]:
        return [PostedInvoice.model_validate(p) for p in self._read(self._ledger, [])]

    def add_to_ledger(self, posted: PostedInvoice) -> None:
        rows = self._read(self._ledger, [])
        rows.append(posted.model_dump(mode="json"))
        self._write(self._ledger, rows)

    def master(self) -> MasterData:
        """The synthetic ERP data, with invoices posted live appended to the AP ledger."""
        base = MasterData.load(MASTER_DIR)
        return MasterData(vendors=base.vendors, purchase_orders=base.purchase_orders,
                          goods_receipts=base.goods_receipts, ledger=base.ledger + self.ledger())
