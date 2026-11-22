"""TK4: curated playbook index — separate from catalog / shop facts."""

from __future__ import annotations

from factory_os.domain.conversation_knowledge import load_manifest, load_playbook, verify_checksums
from factory_os.domain.playbook import (
    PLAYBOOK_MAX_HITS,
    PlaybookIndex,
    format_playbook_hints,
    get_playbook_index,
    playbook_embed_blob,
    playbook_payload,
    search_playbook,
)
from tests.conftest import make_shop


def test_only_curated_playbook_is_indexed_source() -> None:
    assert verify_checksums() == []
    manifest = load_manifest()
    assert manifest["status"] == "indexed"
    curated = {item["file"]: item for item in manifest["curated"]}
    assert curated["05_playbook_curated.json"]["index_now"] is True
    assert curated["05_anti_patterns_layered.json"]["index_now"] is False
    for item in manifest["components"]:
        assert item["index_now"] is False


def test_embed_blob_excludes_example_messages() -> None:
    pattern = load_playbook()["patterns"][0]
    blob = playbook_embed_blob(pattern)
    example = str(pattern.get("example_customer_message") or "")
    assert example
    assert example not in blob
    assert "precio" not in blob.lower() or "precio" in str(pattern.get("goal") or "").lower()
    payload = playbook_payload(pattern)
    assert payload["example_is_not_fact"] is True
    assert payload["domain"] == "conversation_behavior"


def test_search_caps_at_two_hits() -> None:
    index = get_playbook_index()
    assert len(index.rows) == 51
    hits = search_playbook("busco blusas para oficina", limit=10)
    assert len(hits) <= PLAYBOOK_MAX_HITS
    assert PLAYBOOK_MAX_HITS == 2
    for hit in hits:
        assert hit.example_is_not_fact is True
        assert hit.pattern_id.startswith("pb_")


def test_greeting_price_and_return_retrieve_sensible_intents() -> None:
    get_playbook_index.cache_clear()
    greet = search_playbook("Hola, buenas tardes")
    assert greet
    assert greet[0].intent == "greeting"
    price = search_playbook("cuánto cuesta esta blusa?")
    assert price
    assert any(h.intent == "price_question" for h in price)
    returns = search_playbook("quiero devolver esta blusa")
    assert returns
    assert any(h.intent == "return_request" for h in returns)
    cheap = search_playbook("tienen algo más barato?")
    assert cheap
    assert any(h.intent == "price_question" for h in cheap)


def test_hints_never_include_examples_or_catalog_claims() -> None:
    hits = search_playbook("quiero devolver esta blusa")
    text = format_playbook_hints(hits)
    assert "playbook_hints" in text
    assert "behavior only" in text
    assert "example_customer_message" not in text
    for pattern in load_playbook()["patterns"]:
        example = str(pattern.get("example_customer_message") or "")
        if example:
            assert example not in text
    assert "AC-TEST" not in text
    assert "pago1" not in text
    lowered = text.lower()
    assert "bs " not in lowered and " bob" not in lowered


def test_playbook_index_rebuild_from_patterns() -> None:
    book = load_playbook()
    idx = PlaybookIndex()
    assert idx.build(book["patterns"][:3]) == 3
    hits = idx.search("hola", limit=2)
    assert len(hits) <= 2


def test_sales_turn_still_uses_catalog_not_playbook_for_price() -> None:
    shop = make_shop()
    result = shop.handle_turn(shop.store.tenant_id, "59170002901", "cuánto cuesta la blusa pago1")
    reply = result.reply.lower()
    assert "pago1" in reply or "prueba" in reply or "1.00" in reply or "bs" in reply
    # Playbook must not invent Closet policy as if it were catalog.
    assert "archivo" not in reply
