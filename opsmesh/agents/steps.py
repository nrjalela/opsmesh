"""Step log: one record per graph node, with its reasoning and timing."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

from opsmesh.engine.matching import TraceStep

StepKind = Literal["llm", "code", "human"]


class StepLog(BaseModel):
    node: str
    title: str
    kind: StepKind
    started_at: str
    duration_ms: int
    summary: str
    reasoning: str = ""
    trace: list[TraceStep] = Field(default_factory=list)
    model: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    error: str | None = None


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Timer:
    def __init__(self) -> None:
        self.started_at = now_iso()
        self._t0 = time.perf_counter()

    @property
    def ms(self) -> int:
        return int((time.perf_counter() - self._t0) * 1000)
