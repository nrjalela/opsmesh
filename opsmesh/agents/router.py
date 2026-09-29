"""Approval router: plain rules over amount, exceptions and extraction confidence."""

from __future__ import annotations

from decimal import Decimal
from functools import lru_cache
from typing import Literal

import yaml
from pydantic import BaseModel

from opsmesh.config import CONFIG_DIR
from opsmesh.engine.matching import ExceptionType, MatchResult
from opsmesh.engine.money import aud


class AmountTier(BaseModel):
    up_to: Decimal | None
    approver: str


class ApprovalRules(BaseModel):
    roles: list[str]
    auto_post_limit: Decimal
    amount_tiers: list[AmountTier]
    exception_approvers: dict[str, str]
    escalate_held_above: Decimal
    min_field_confidence: float

    def rank(self, role: str) -> int:
        return self.roles.index(role)


@lru_cache
def load_rules() -> ApprovalRules:
    with open(CONFIG_DIR / "approval_rules.yaml") as f:
        return ApprovalRules.model_validate(yaml.safe_load(f))


Recommendation = Literal["approve", "reject", "resolve_first"]


class RouteDecision(BaseModel):
    action: Literal["auto_post", "needs_approval"]
    approver: str | None = None
    reasons: list[str]
    recommendation: Recommendation | None = None


def route_invoice(
    match: MatchResult | None,
    total: Decimal | None,
    low_confidence: list[str],
    missing: list[str],
    errors: list[str],
    rules: ApprovalRules | None = None,
) -> RouteDecision:
    rules = rules or load_rules()
    candidates: list[str] = []
    reasons: list[str] = []
    base = rules.roles[0]

    for err in errors:
        reasons.append(f"Automation couldn't finish: {err}")
        candidates.append(base)
    if missing:
        reasons.append("Couldn't read " + ", ".join(missing) + " from the PDF. Key it in by hand.")
        candidates.append(base)
    if low_confidence:
        shown = ", ".join(low_confidence[:4]) + (" and more" if len(low_confidence) > 4 else "")
        reasons.append(f"Low-confidence extraction ({shown}). Check against the PDF.")
        candidates.append(base)

    held = bool(match and match.exceptions)
    if match is not None:
        for t in match.exception_types:
            role = rules.exception_approvers.get(t.value, base)
            reasons.append(f"{t.label} (reviewer: {role}).")
            candidates.append(role)

    if total is not None and match is not None and not held and not candidates:
        if total <= rules.auto_post_limit:
            return RouteDecision(
                action="auto_post",
                reasons=[f"Clean three-way match and {aud(total)} is within the {aud(rules.auto_post_limit)} auto-post limit."],
            )
        for tier in rules.amount_tiers:
            if tier.up_to is None or total <= tier.up_to:
                reasons.append(f"Clean match, but {aud(total)} is over the {aud(rules.auto_post_limit)} auto-post limit.")
                candidates.append(tier.approver)
                break

    if held and total is not None and total > rules.escalate_held_above:
        reasons.append(f"Held invoice over {aud(rules.escalate_held_above)}: Finance Manager sign-off.")
        candidates.append(rules.roles[-1])

    approver = max(candidates, key=rules.rank) if candidates else base
    types = set(match.exception_types) if match else set()
    if ExceptionType.DUPLICATE_INVOICE in types:
        rec: Recommendation = "reject"
    elif held or missing or errors or low_confidence:
        rec = "resolve_first"
    else:
        rec = "approve"
    return RouteDecision(action="needs_approval", approver=approver, reasons=reasons, recommendation=rec)
