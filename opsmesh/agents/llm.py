"""Thin wrapper over the Anthropic SDK: one structured call, timed and costed."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Generic, TypeVar

import anthropic
from dotenv import load_dotenv
from pydantic import BaseModel

from opsmesh.config import ROOT

load_dotenv(ROOT / ".env")

DEFAULT_MODEL = "claude-sonnet-5-5"
# USD per million tokens (input, output). Cache reads are 10% of input.
PRICING = {
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-sonnet-5": (2.00, 10.00),
    "claude-opus-5-5": (4.00, 20.00),
    "claude-haiku-4-5": (1.00, 5.00),
}
FALLBACK_BETA = "server-side-fallback-2026-07-01"

T = TypeVar("T", bound=BaseModel)


def model_name() -> str:
    return os.getenv("OPSMESH_MODEL", DEFAULT_MODEL)


def api_key_available() -> bool:
    return bool(os.getenv("ANTHROPIC_API_KEY"))


class LLMRefusal(RuntimeError):
    """The model declined; the invoice goes to a person instead."""


@dataclass
class LLMResult(Generic[T]):
    output: T
    model: str
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cost_usd: float
    duration_ms: int
    thinking_summary: str
    request_id: str | None


def _cost(model: str, usage) -> float:
    rate_in, rate_out = PRICING.get(model, PRICING[DEFAULT_MODEL])
    cached = getattr(usage, "cache_read_input_tokens", 0) or 0
    written = getattr(usage, "cache_creation_input_tokens", 0) or 0
    return (
        usage.input_tokens * rate_in
        + cached * rate_in * 0.10
        + written * rate_in * 1.25
        + usage.output_tokens * rate_out
    ) / 1_000_000


_client: anthropic.Anthropic | None = None


def client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(max_retries=3, timeout=180.0)
    return _client


def structured_call(*, system: str, content: list[dict], output_format: type[T], effort: str = "medium",
                    max_tokens: int = 16000) -> LLMResult[T]:
    """One Messages API call whose reply is parsed and validated into `output_format`.

    - Adaptive thinking with summarised display, so the step log can show *why*.
    - Server-side fallback ("default") so a rare classifier decline is retried
      on another model rather than failing the invoice.
    - The system prompt is marked cacheable; it's identical across the batch.
    """
    model = model_name()
    started = time.perf_counter()
    resp = client().beta.messages.parse(
        model=model,
        max_tokens=max_tokens,
        system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": content}],
        thinking={"type": "adaptive", "display": "summarized"},
        output_config={"effort": effort},
        output_format=output_format,
        betas=[FALLBACK_BETA],
        fallbacks="default",
    )
    duration_ms = int((time.perf_counter() - started) * 1000)

    if resp.stop_reason == "refusal":
        category = getattr(resp.stop_details, "category", None) if resp.stop_details else None
        raise LLMRefusal(f"Model declined (category: {category or 'unspecified'})")
    if resp.stop_reason == "max_tokens":
        raise RuntimeError("Model hit max_tokens before finishing the structured output")
    parsed = resp.parsed_output
    if parsed is None:
        raise RuntimeError("Model returned no parseable structured output")

    thinking = "\n".join(b.thinking for b in resp.content if b.type == "thinking" and b.thinking).strip()
    served_by = resp.model or model
    return LLMResult(
        output=parsed,
        model=served_by,
        input_tokens=resp.usage.input_tokens,
        output_tokens=resp.usage.output_tokens,
        cache_read_tokens=getattr(resp.usage, "cache_read_input_tokens", 0) or 0,
        cost_usd=round(_cost(served_by, resp.usage), 6),
        duration_ms=duration_ms,
        thinking_summary=thinking,
        request_id=getattr(resp, "_request_id", None),
    )
