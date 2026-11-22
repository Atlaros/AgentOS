from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any


@dataclass(frozen=True)
class PolicyDecision:
    effect: str  # allow | deny | require_human
    rule_name: str
    reason: str


def evaluate_policy(
    *,
    amount: Decimal,
    rules: list[dict[str, Any]],
    auto_allow_max: Decimal,
) -> PolicyDecision:
    """Evaluate enabled rules by priority ascending; first match wins.

    Default: amount <= auto_allow_max → allow; else require_human.
    """
    ordered = sorted(rules, key=lambda r: int(r.get("priority", 100)))
    for rule in ordered:
        if not rule.get("enabled", True):
            continue
        match = rule.get("match") or {}
        amount_max = match.get("amount_max")
        if amount_max is not None and amount > Decimal(str(amount_max)):
            continue
        amount_min = match.get("amount_min")
        if amount_min is not None and amount < Decimal(str(amount_min)):
            continue
        effect = str(rule["effect"])
        return PolicyDecision(effect=effect, rule_name=str(rule["name"]), reason="matched_rule")

    if amount <= auto_allow_max:
        return PolicyDecision(
            effect="allow",
            rule_name="default_auto_allow",
            reason=f"amount<={auto_allow_max}",
        )
    return PolicyDecision(
        effect="require_human",
        rule_name="default_require_human",
        reason=f"amount>{auto_allow_max}",
    )
