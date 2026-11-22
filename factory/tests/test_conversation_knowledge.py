"""Schema, checksum, and adoption guards for conversation knowledge seeds."""

from __future__ import annotations

from factory_os.domain.conversation_knowledge import (
    ADRI_TOOL_VOCABULARY,
    RUNTIME_ANTI_PATTERNS,
    UNSUPPORTED_BITEXT_INTENTS,
    anti_pattern_layer,
    bitext_intents_for_adri,
    counts,
    exact_intent_overlap_01_03,
    knowledge_dir,
    layered_anti_patterns_by_layer,
    load_adri_patterns,
    load_anti_patterns,
    load_bitext_intents,
    load_bundle,
    load_convrec_patterns,
    load_layered_anti_patterns,
    load_manifest,
    load_playbook,
    map_recommended_action,
    pattern_action,
    playbook_validation_errors,
    unmapped_actions,
    verify_checksums,
)
from factory_os.domain.models import NextAction


def test_checksums_match_manifest() -> None:
    assert verify_checksums() == []
    manifest = load_manifest()
    assert manifest["status"] == "indexed"
    assert manifest["authority"]["business_facts"].startswith("catalog.search")
    assert len(manifest["curated"]) == 2


def test_record_counts_and_bundle_parity() -> None:
    c = counts()
    assert c["convrec_patterns"] == 18
    assert c["bitext_intents"] == 27
    assert c["adri_patterns"] == 46
    assert c["anti_patterns"] == 22
    assert c["playbook_patterns"] == 51
    assert c["bitext_supported_for_adri"] == 27 - len(UNSUPPORTED_BITEXT_INTENTS)
    assert c["anti_runtime"] == len(RUNTIME_ANTI_PATTERNS)
    assert c["anti_layered_runtime"] == 8
    assert c["anti_layered_state"] == 5
    assert c["anti_layered_eval"] == 9
    assert c["intent_overlap_01_03"] == 7
    bundle = load_bundle()
    assert bundle["counts"] == {
        "convrec_patterns": 18,
        "bitext_intents": 27,
        "adri_patterns": 46,
        "anti_patterns": 22,
    }


def test_required_pattern_fields() -> None:
    for item in load_convrec_patterns()["patterns"]:
        assert item["pattern_id"].startswith("convrec_")
        assert item["situation"]
        assert item["next_action"]
        assert item["metadata"]["intent"]
        assert item["metadata"]["domain"] == "conversation_behavior"
    for item in load_adri_patterns()["patterns"]:
        assert item["pattern_id"].startswith("adri_")
        assert item["intent"]
        assert item["recommended_next_action"]
        assert "required_knowledge" in item
        assert isinstance(item["required_knowledge"], list)
        assert item["metadata"]["intent"]
        assert item["metadata"]["domain"] in {
            "conversation_behavior",
            "sales_agent_behavior",
        }
    for item in load_anti_patterns()["anti_patterns"]:
        assert item["name"]
        assert item["rule"]
        assert anti_pattern_layer(item["name"]) in {
            "runtime",
            "state_validation",
            "quality_eval",
        }


def test_intent_overlap_is_known_seven() -> None:
    overlap = exact_intent_overlap_01_03()
    assert overlap == {
        "customer_hesitation",
        "need_change",
        "previous_product_reference",
        "product_comparison",
        "purchase_intent",
        "recommendation_rejection",
        "similar_item_request",
    }


def test_adri_and_convrec_actions_map_to_next_action() -> None:
    adri = load_adri_patterns()["patterns"]
    convrec = load_convrec_patterns()["patterns"]
    assert unmapped_actions(adri) == []
    assert unmapped_actions(convrec) == []
    mapped = {map_recommended_action(pattern_action(p)) for p in adri}
    assert NextAction.SEARCH_CATALOG in mapped
    assert NextAction.REQUEST_CONFIRMATION in mapped
    assert NextAction.ESCALATE in mapped
    free_form = {pattern_action(p) for p in adri}
    assert len(free_form) >= 40
    assert len(NextAction) == 11


def test_bitext_filters_unsupported_write_intents() -> None:
    supported = {item["intent"] for item in bitext_intents_for_adri()}
    assert "place_order" in supported
    assert "contact_human_agent" in supported
    assert "get_invoice" not in supported
    assert "create_account" not in supported
    all_intents = {item["intent"] for item in load_bitext_intents()["intents"]}
    assert UNSUPPORTED_BITEXT_INTENTS <= all_intents


def test_runtime_anti_patterns_cover_invention() -> None:
    names = {item["name"] for item in load_anti_patterns()["anti_patterns"]}
    for required in (
        "invented_product",
        "invented_price",
        "invented_stock",
        "invented_policy",
        "treating_conversation_examples_as_business_truth",
        "answering_without_consulting_catalog",
    ):
        assert required in names
        assert anti_pattern_layer(required) == "runtime"


def test_curated_playbook_is_valid() -> None:
    assert playbook_validation_errors() == []
    book = load_playbook()
    assert book["status"] == "indexed"
    assert book["counts"]["patterns"] == 51
    assert set(book["dedupe"]["overlap_intents_superseded_from_01"]) == exact_intent_overlap_01_03()
    tools_used: set[str] = set()
    for item in book["patterns"]:
        tools_used |= set(item["allowed_tools"])
        assert map_recommended_action(item["next_action"]) is not None
    assert tools_used <= ADRI_TOOL_VOCABULARY
    assert "catalog.search" in tools_used
    # Closet gates
    by_intent = {p["intent"]: p for p in book["patterns"]}
    assert by_intent["reservation_intent"]["capability"] == "shop_answer_only"
    assert by_intent["return_request"]["capability"] == "shop_answer_only"
    assert by_intent["exchange_request"]["capability"] == "shop_answer_only"
    assert by_intent["order_tracking"]["capability"] == "handoff"
    assert by_intent["payment_how_to"]["allowed_tools"] == []
    assert by_intent["order_placement_intent"]["allowed_tools"] == [
        "catalog.search",
        "cart.add",
        "order.create",
    ]


def test_layered_anti_patterns_match_source() -> None:
    raw = {item["name"] for item in load_anti_patterns()["anti_patterns"]}
    layered = load_layered_anti_patterns()
    names = {item["name"] for item in layered["anti_patterns"]}
    assert names == raw
    assert layered["counts"] == {"total": 22, "runtime": 8, "state_validation": 5, "quality_eval": 9}
    for item in layered_anti_patterns_by_layer("runtime"):
        assert item["layer"] == "runtime"
        assert anti_pattern_layer(item["name"]) == "runtime"
    for item in layered["anti_patterns"]:
        assert item["enforcement"]
        assert item["layer"] == anti_pattern_layer(item["name"])


def test_adoption_docs_present() -> None:
    root = knowledge_dir()
    assert (root / "ADOPTION.md").is_file()
    assert (root / "README.md").is_file()
    assert (root / "CURSOR_INTEGRATION_SPEC.md").is_file()
    assert (root / "05_playbook_curated.json").is_file()
    assert (root / "05_anti_patterns_layered.json").is_file()
