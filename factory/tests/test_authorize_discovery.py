"""Authorize discovery must not override a valid SalesDecision (ADR-003)."""

from factory_os.agents.sales import authorize_discovery
from factory_os.domain.models import NextAction, WorkingState


def test_authorize_discovery_skips_when_sales_decision() -> None:
    state = WorkingState()
    action, skill = authorize_discovery(
        NextAction.SEARCH_CATALOG,
        state,
        "quiero una blusa",
        from_sales_decision=True,
    )
    assert action is NextAction.SEARCH_CATALOG
    assert skill is None


def test_authorize_discovery_still_guards_nba_fallback() -> None:
    state = WorkingState()
    action, skill = authorize_discovery(
        NextAction.SEARCH_CATALOG,
        state,
        "quiero una blusa",
        from_sales_decision=False,
    )
    assert action is NextAction.ASK_DISCOVERY_QUESTION
    assert skill == "sales_discovery"
