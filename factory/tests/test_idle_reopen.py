"""Idle reopen: gap hours → greet + ask continue vs search other."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from factory_os.contracts.employees import identity_for
from factory_os.domain.memory import DEFAULT_IDLE_HOURS, is_idle_reopen
from factory_os.domain.models import Conversation, EmployeeRole, PILOT_TENANT_ID
from factory_os.harness.context import compile_context
from factory_os.harness.model_gateway import (
    FRIENDLY_IDLE_REOPEN,
    draft_style_ok,
    grounded_draft,
)
from tests.conftest import make_shop


def test_is_idle_reopen_threshold() -> None:
    now = datetime(2026, 9, 24, 15, 0, tzinfo=UTC)
    assert is_idle_reopen(None, now=now) is False
    assert is_idle_reopen(now - timedelta(hours=3), hours=4, now=now) is False
    assert is_idle_reopen(now - timedelta(hours=4), hours=4, now=now) is True
    assert is_idle_reopen(now - timedelta(hours=5), hours=DEFAULT_IDLE_HOURS, now=now) is True


def test_draft_style_allows_greeting_on_idle_reopen() -> None:
    context = (
        "idle_reopen=true\n"
        "recent:\n"
        "  Adri: Hola, soy Adri de Closet.\n"
        "  customer: hola de nuevo"
    )
    greet = "¡Hola de nuevo! ¿Seguimos con lo anterior o buscamos otra cosa?"
    assert draft_style_ok(greet, context=context) is True
    assert grounded_draft(greet, {"hits": []}, FRIENDLY_IDLE_REOPEN, context=context) == greet


def test_draft_style_still_rejects_regreet_without_idle() -> None:
    context = (
        "recent:\n"
        "  Adri: Hola, soy Adri de Closet.\n"
        "  customer: busco blusa"
    )
    bad = "¡Hola! ¿Cómo estás? Te muestro blusas."
    assert draft_style_ok(bad, context=context) is False


def test_compile_context_marks_idle_reopen() -> None:
    identity = identity_for(EmployeeRole.SALES, PILOT_TENANT_ID)
    conv = Conversation(id=uuid4(), tenant_id=PILOT_TENANT_ID, customer_id=uuid4())
    conv.messages = [("customer", "hola"), ("Adri", "¿qué buscás?")]
    conv.turn_idle_reopen = True
    ctx = compile_context(identity, conv)
    assert "idle_reopen=true" in ctx


def test_idle_reopen_turn_preserves_memory() -> None:
    shop = make_shop()
    wa = "59193000011"
    shop.handle_turn(PILOT_TENANT_ID, wa, "hola")
    shop.handle_turn(PILOT_TENANT_ID, wa, "busco blusa negra talla M")
    customer = shop.store.get_or_create_customer(PILOT_TENANT_ID, wa)
    conv = shop.store.get_or_create_conversation(PILOT_TENANT_ID, customer)
    conv.state.size = "M"
    conv.state.color = "negro"
    conv.state.preference_provenance = {"size": "customer_explicit", "color": "customer_explicit"}
    conv.state.graph_node = "adri"
    conv.summary_text = "resumen: buscaba blusa negra"
    shop.store.save_conversation_state(conv)

    # Simulate gap without waiting real hours.
    conv.last_message_at = datetime.now(UTC) - timedelta(hours=5)
    conv.turn_idle_reopen = False
    shop.store.conversations[conv.id] = conv

    result = shop.handle_turn(PILOT_TENANT_ID, wa, "hola otra vez")
    assert result.employee == "Adri"
    reply = result.reply.lower()
    assert "hola" in reply or "¡hola" in result.reply.lower()
    assert "continu" in reply or "seguimos" in reply or "anterior" in reply
    assert "otra" in reply

    conv2 = shop.store.get_or_create_conversation(PILOT_TENANT_ID, customer)
    assert conv2.summary_text == "resumen: buscaba blusa negra"
    assert conv2.state.graph_node == "adri"
    prefs = shop.store.get_customer_preferences(PILOT_TENANT_ID, customer.id)
    assert prefs.get("size") == "M"
    assert prefs.get("color") == "negro"


def test_short_gap_does_not_reopen_greet() -> None:
    shop = make_shop()
    wa = "59193000012"
    shop.handle_turn(PILOT_TENANT_ID, wa, "hola")
    r1 = shop.handle_turn(PILOT_TENANT_ID, wa, "busco algo")
    # Immediate follow-up: no idle reopen path.
    customer = shop.store.get_or_create_customer(PILOT_TENANT_ID, wa)
    conv = shop.store.get_or_create_conversation(PILOT_TENANT_ID, customer)
    assert conv.last_message_at is not None
    assert is_idle_reopen(conv.last_message_at, hours=4) is False
    r2 = shop.handle_turn(PILOT_TENANT_ID, wa, "talla M")
    # Should not be the canned idle reopen script.
    assert FRIENDLY_IDLE_REOPEN not in r2.reply
    assert r1.reply  # smoke
