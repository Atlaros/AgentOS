"""Versioned conversation-behavior knowledge (not business facts).

Business facts stay in catalog.search / shop_knowledge.
These files teach *how* to sell; they never invent price, stock, or policy.
Curated playbook (05_*) is indexed in ``conversation_playbook`` (pgvector) via
``factory_os.domain.playbook`` — optional READ hints for SalesDecision.
"""

from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from factory_os.contracts.skills import ADRI_SKILLS
from factory_os.domain.models import NextAction

# Bitext intents that Adri cannot execute as WRITE today.
UNSUPPORTED_BITEXT_INTENTS = frozenset(
    {
        "get_invoice",
        "check_invoice",
        "newsletter_subscription",
        "create_account",
        "delete_account",
        "edit_account",
        "switch_account",
        "recover_password",
        "registration_problems",
        "get_refund",
        "track_refund",
        "change_order",
        "check_cancellation_fee",
        "review",
    }
)

# Anti-patterns that must be enforced by runtime / BBE / grounding (not RAG).
RUNTIME_ANTI_PATTERNS = frozenset(
    {
        "invented_product",
        "invented_price",
        "invented_stock",
        "invented_feature",
        "invented_policy",
        "answering_without_consulting_catalog",
        "treating_conversation_examples_as_business_truth",
        "ignoring_explicit_escalation_request",
    }
)

# Prefer working-state checks before / after a turn.
STATE_ANTI_PATTERNS = frozenset(
    {
        "ignoring_customer_constraints",
        "repeating_rejected_recommendation",
        "losing_context",
        "repeating_answered_questions",
        "upselling_after_purchase_intent",
    }
)

ADRI_TOOL_VOCABULARY = frozenset({"catalog.search", "cart.add", "cart.remove", "order.create"})
ADRI_SKILL_VOCABULARY = frozenset(skill.name for skill in ADRI_SKILLS)
PLAYBOOK_CAPABILITIES = frozenset({"adri", "shop_answer_only", "handoff", "escalate"})
KNOWLEDGE_SOURCES = frozenset({"catalog", "shop_knowledge", "working_state"})

# Map free-form recommended_next_action / next_action → runtime NextAction.
# Longer / more specific hints first.
_ACTION_HINTS: tuple[tuple[str, NextAction], ...] = (
    ("escalate", NextAction.ESCALATE),
    ("log_complaint", NextAction.ESCALATE),
    ("diagnose_order", NextAction.ESCALATE),
    ("lookup_order", NextAction.HANDOFF),
    ("check_return", NextAction.HANDOFF),
    ("check_exchange", NextAction.HANDOFF),
    ("collect_required_order", NextAction.CREATE_ORDER),
    ("collect_and_confirm", NextAction.CREATE_ORDER),
    ("trigger_conversion", NextAction.REQUEST_CONFIRMATION),
    ("trigger_reservation", NextAction.REQUEST_CONFIRMATION),
    ("advance_towards_conversion", NextAction.REQUEST_CONFIRMATION),
    ("compare_", NextAction.COMPARE),
    ("present_structured_comparison", NextAction.COMPARE),
    ("offer_simplified", NextAction.HANDLE_OBJECTION),
    ("ask_", NextAction.ASK_DISCOVERY_QUESTION),
    ("clarifying", NextAction.ASK_DISCOVERY_QUESTION),
    ("translate_need", NextAction.ASK_DISCOVERY_QUESTION),
    ("query_catalog", NextAction.SEARCH_CATALOG),
    ("search_catalog", NextAction.SEARCH_CATALOG),
    ("search_again", NextAction.SEARCH_CATALOG),
    ("semantic_search", NextAction.SEARCH_CATALOG),
    ("refine_search", NextAction.SEARCH_CATALOG),
    ("refine_current_search", NextAction.SEARCH_CATALOG),
    ("start_new_search", NextAction.SEARCH_CATALOG),
    ("apply_attribute_filter", NextAction.SEARCH_CATALOG),
    ("adjust_search", NextAction.SEARCH_CATALOG),
    ("check_size", NextAction.SEARCH_CATALOG),
    ("check_stock", NextAction.SEARCH_CATALOG),
    ("check_availability", NextAction.SEARCH_CATALOG),
    ("retrieve_similar", NextAction.RECOMMEND),
    ("retrieve_alternatives", NextAction.RECOMMEND),
    ("retrieve_variants", NextAction.RECOMMEND),
    ("retrieve_color", NextAction.RECOMMEND),
    ("retrieve_size", NextAction.RECOMMEND),
    ("retrieve_product", NextAction.RECOMMEND),
    ("lookup_product", NextAction.RECOMMEND),
    ("present_limited", NextAction.RECOMMEND),
    ("retrieve_payment", NextAction.ANSWER),
    ("retrieve_shipping", NextAction.ANSWER),
    ("retrieve_price", NextAction.ANSWER),
    ("retrieve_faq", NextAction.ANSWER),
    ("answer_", NextAction.ANSWER),
    ("await_customer", NextAction.ANSWER),
    ("resolve_reference", NextAction.ANSWER),
    ("carry_conversation", NextAction.ANSWER),
    ("end_turn", NextAction.ANSWER),
)


def knowledge_dir() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        path = parent / "db" / "seeds" / "conversation_knowledge"
        if (path / "manifest.json").exists():
            return path
    raise FileNotFoundError("db/seeds/conversation_knowledge/manifest.json")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@lru_cache(maxsize=1)
def load_manifest() -> dict[str, Any]:
    return json.loads((knowledge_dir() / "manifest.json").read_text(encoding="utf-8"))


def _load_json(name: str) -> dict[str, Any]:
    return json.loads((knowledge_dir() / name).read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def load_convrec_patterns() -> dict[str, Any]:
    return _load_json("01_convrec_patterns.json")


@lru_cache(maxsize=1)
def load_bitext_intents() -> dict[str, Any]:
    return _load_json("02_bitext_intent_taxonomy.json")


@lru_cache(maxsize=1)
def load_adri_patterns() -> dict[str, Any]:
    return _load_json("03_adri_business_patterns.json")


@lru_cache(maxsize=1)
def load_anti_patterns() -> dict[str, Any]:
    return _load_json("04_anti_patterns.json")


@lru_cache(maxsize=1)
def load_bundle() -> dict[str, Any]:
    return _load_json("conversation_knowledge_bundle.json")


@lru_cache(maxsize=1)
def load_playbook() -> dict[str, Any]:
    return _load_json("05_playbook_curated.json")


@lru_cache(maxsize=1)
def load_layered_anti_patterns() -> dict[str, Any]:
    return _load_json("05_anti_patterns_layered.json")


def verify_checksums() -> list[str]:
    """Return list of mismatch messages (empty = ok)."""
    errors: list[str] = []
    root = knowledge_dir()
    manifest = load_manifest()
    for item in manifest["components"]:
        path = root / item["file"]
        got = _sha256(path)
        if got != item["sha256"]:
            errors.append(f"{item['file']}: expected {item['sha256']}, got {got}")
    for item in manifest.get("curated", []):
        path = root / item["file"]
        got = _sha256(path)
        if got != item["sha256"]:
            errors.append(f"{item['file']}: expected {item['sha256']}, got {got}")
    bundle = manifest["bundle"]
    got_bundle = _sha256(root / bundle["file"])
    if got_bundle != bundle["sha256"]:
        errors.append(f"{bundle['file']}: expected {bundle['sha256']}, got {got_bundle}")
    return errors


def map_recommended_action(name: str | None) -> NextAction | None:
    """Map a free-form pattern action to the runtime NextAction vocabulary."""
    if not name:
        return None
    # Curated playbook already uses NextAction values.
    try:
        return NextAction(name.strip().lower())
    except ValueError:
        pass
    lowered = name.strip().lower()
    for hint, action in _ACTION_HINTS:
        if hint in lowered:
            return action
    return None


def anti_pattern_layer(name: str) -> str:
    if name in RUNTIME_ANTI_PATTERNS:
        return "runtime"
    if name in STATE_ANTI_PATTERNS:
        return "state_validation"
    return "quality_eval"


def runtime_anti_patterns() -> list[dict[str, Any]]:
    return [
        item
        for item in load_anti_patterns()["anti_patterns"]
        if anti_pattern_layer(item["name"]) == "runtime"
    ]


def layered_anti_patterns_by_layer(layer: str) -> list[dict[str, Any]]:
    return [item for item in load_layered_anti_patterns()["anti_patterns"] if item["layer"] == layer]


def bitext_intents_for_adri(*, include_unsupported: bool = False) -> list[dict[str, Any]]:
    intents = load_bitext_intents()["intents"]
    if include_unsupported:
        return list(intents)
    return [item for item in intents if item["intent"] not in UNSUPPORTED_BITEXT_INTENTS]


def exact_intent_overlap_01_03() -> set[str]:
    a = {item["metadata"]["intent"] for item in load_convrec_patterns()["patterns"]}
    b = {item["metadata"]["intent"] for item in load_adri_patterns()["patterns"]}
    return a & b


def pattern_action(item: dict[str, Any]) -> str | None:
    """Free-form action string from either ConvRec or Adri pattern records."""
    return item.get("recommended_next_action") or item.get("next_action")


def unmapped_actions(patterns: list[dict[str, Any]]) -> list[str]:
    missing: list[str] = []
    for item in patterns:
        name = pattern_action(item)
        if name and map_recommended_action(name) is None:
            missing.append(name)
    return sorted(set(missing))


def playbook_validation_errors() -> list[str]:
    """Structural + capability checks for the curated playbook."""
    errors: list[str] = []
    book = load_playbook()
    patterns = book["patterns"]
    intents = [item["intent"] for item in patterns]
    if len(intents) != len(set(intents)):
        errors.append("duplicate intents in curated playbook")

    adri_intents = {item["metadata"]["intent"] for item in load_adri_patterns()["patterns"]}
    missing_adri = sorted(adri_intents - set(intents))
    if missing_adri:
        errors.append(f"playbook missing Adri intents: {missing_adri}")

    overlap = exact_intent_overlap_01_03()
    for item in patterns:
        if item["intent"] in overlap and not item.get("supersedes"):
            errors.append(f"{item['pattern_id']} overlap intent lacks supersedes")
        tools = set(item.get("allowed_tools") or [])
        if not tools <= ADRI_TOOL_VOCABULARY:
            errors.append(f"{item['pattern_id']} tools outside Adri: {tools - ADRI_TOOL_VOCABULARY}")
        if item.get("skill") not in ADRI_SKILL_VOCABULARY:
            errors.append(f"{item['pattern_id']} unknown skill {item.get('skill')}")
        if item.get("capability") not in PLAYBOOK_CAPABILITIES:
            errors.append(f"{item['pattern_id']} bad capability {item.get('capability')}")
        sources = set(item.get("knowledge_sources") or [])
        if not sources <= KNOWLEDGE_SOURCES:
            errors.append(f"{item['pattern_id']} bad knowledge_sources {sources - KNOWLEDGE_SOURCES}")
        action = map_recommended_action(item.get("next_action"))
        if action is None:
            errors.append(f"{item['pattern_id']} unmapped next_action {item.get('next_action')}")
        if not item.get("example_is_not_fact", False):
            errors.append(f"{item['pattern_id']} must mark example_is_not_fact")
        # Closet: post-sale writes Adri cannot do alone.
        if item["capability"] == "shop_answer_only" and tools:
            errors.append(f"{item['pattern_id']} shop_answer_only must have empty tools")
        if item["capability"] in {"handoff", "escalate"} and tools & {"cart.add", "order.create"}:
            errors.append(f"{item['pattern_id']} handoff/escalate cannot WRITE sales tools")
    return errors


def counts() -> dict[str, int]:
    layered = load_layered_anti_patterns()["counts"]
    return {
        "convrec_patterns": len(load_convrec_patterns()["patterns"]),
        "bitext_intents": len(load_bitext_intents()["intents"]),
        "adri_patterns": len(load_adri_patterns()["patterns"]),
        "anti_patterns": len(load_anti_patterns()["anti_patterns"]),
        "playbook_patterns": len(load_playbook()["patterns"]),
        "bitext_supported_for_adri": len(bitext_intents_for_adri()),
        "anti_runtime": len(runtime_anti_patterns()),
        "anti_layered_runtime": layered["runtime"],
        "anti_layered_state": layered["state_validation"],
        "anti_layered_eval": layered["quality_eval"],
        "intent_overlap_01_03": len(exact_intent_overlap_01_03()),
    }
