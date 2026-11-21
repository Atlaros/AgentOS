from decimal import Decimal

from agentos.policy.engine import evaluate_policy


def test_auto_allow_below_threshold() -> None:
    decision = evaluate_policy(amount=Decimal(5), rules=[], auto_allow_max=Decimal(10))
    assert decision.effect == "allow"


def test_require_human_above_threshold() -> None:
    decision = evaluate_policy(amount=Decimal(50), rules=[], auto_allow_max=Decimal(10))
    assert decision.effect == "require_human"


def test_explicit_deny_rule() -> None:
    rules = [
        {
            "name": "deny_all",
            "effect": "deny",
            "match": {},
            "priority": 1,
            "enabled": True,
        }
    ]
    decision = evaluate_policy(amount=Decimal(1), rules=rules, auto_allow_max=Decimal(10))
    assert decision.effect == "deny"
    assert decision.rule_name == "deny_all"
