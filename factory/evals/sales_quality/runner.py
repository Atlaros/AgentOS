"""Run sales-quality corpus against ShopRuntime (FakeGateway / memory store)."""

from __future__ import annotations

from typing import Any

from evals.sales_quality.rules import CaseResult, CheckResult, load_corpus, score_reply, summarize
from factory_os.agents.turn import ShopRuntime
from factory_os.domain.models import PILOT_TENANT_ID
from factory_os.domain.seed import catalog_seed_path, load_catalog_json, load_pilot_catalog
from factory_os.domain.store import MemoryCommerceStore
from factory_os.domain.tenant_config import put_tenant_config
from factory_os.tools.registry import FakePaymentProvider


def make_eval_shop(*, closet: bool = False, industry: str | None = None) -> ShopRuntime:
    """Build an in-memory shop for evals. Default catalog is Closet; pass industry='cafe' for café."""
    _ = closet  # historical flag; industry wins when set
    kind = (industry or "ropa").strip().lower()
    if kind == "closet":
        kind = "ropa"
    store = MemoryCommerceStore(PILOT_TENANT_ID)
    if kind == "cafe":
        load_catalog_json(catalog_seed_path("cafe"), store)
        put_tenant_config(PILOT_TENANT_ID, industry="cafe", modules=("whatsapp", "pedido", "cobros"))
    else:
        load_pilot_catalog(store)
        put_tenant_config(PILOT_TENANT_ID, industry="ropa", modules=("whatsapp", "pedido", "cobros"))
    return ShopRuntime(store, FakePaymentProvider())


def _wa_for(case_id: str) -> str:
    # Stable unique WA per case so conversations don't collide.
    digits = "".join(ch for ch in case_id if ch.isdigit()) or "0"
    return f"5918{int(digits) % 10_000_000:07d}"


def run_case(shop: ShopRuntime, case: dict[str, Any]) -> CaseResult:
    wa = _wa_for(case["id"])
    replies: list[str] = []
    for turn in case["turns"]:
        if turn.get("role") != "customer":
            continue
        result = shop.handle_turn(shop.store.tenant_id, wa, turn["text"])
        replies.append(result.reply)
    last = replies[-1] if replies else ""
    checks = score_reply(last, case.get("expect") or {})
    return CaseResult(
        case_id=case["id"],
        failure=str(case.get("failure") or ""),
        ok=all(c.ok for c in checks),
        checks=checks,
        last_reply=last,
        replies=replies,
    )


def run_corpus(*, closet: bool = True, case_ids: set[str] | None = None) -> tuple[list[CaseResult], dict[str, Any]]:
    """Run the full corpus. Defaults to Closet seed + pay_test overlay (production-shaped)."""
    corpus = load_corpus()
    results: list[CaseResult] = []
    for case in corpus["cases"]:
        if case_ids is not None and case["id"] not in case_ids:
            continue
        shop = make_eval_shop(closet=closet)
        results.append(run_case(shop, case))
    return results, summarize(results)
