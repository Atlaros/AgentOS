"""Paso 2 — conversation summary + durable customer preferences."""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

from factory_os.contracts.employees import identity_for
from factory_os.domain.memory import (
    RECENT_WINDOW,
    SUMMARY_THRESHOLD,
    compact_messages,
    format_customer_memory,
    maybe_refresh_summary,
    prefs_from_working_state,
)
from factory_os.domain.models import Conversation, EmployeeRole, PILOT_TENANT_ID, WorkingState
from factory_os.domain.sales_decision import PreferencePatch, apply_preference_patch
from factory_os.harness.context import compile_context
from tests.conftest import make_shop


def test_compact_messages_is_deterministic() -> None:
    text = compact_messages([("customer", "busco blusas negras"), ("Adri", "¿talla?")])
    assert text.startswith("resumen:")
    assert "blusas" in text
    assert "talla" in text


def test_summary_refreshes_after_threshold() -> None:
    conv = Conversation(id=uuid4(), tenant_id=PILOT_TENANT_ID, customer_id=uuid4())
    for i in range(SUMMARY_THRESHOLD):
        conv.messages.append(("customer" if i % 2 == 0 else "Adri", f"msg {i} blusa"))
    assert maybe_refresh_summary(conv) is True
    assert conv.summary_text
    assert conv.summary_msg_count == SUMMARY_THRESHOLD - RECENT_WINDOW


def test_prefs_from_working_state_only_explicit() -> None:
    state = WorkingState(budget_max=Decimal("80"), size="M")
    state.preference_provenance = {"budget_max": "customer_explicit", "size": "inferred"}
    prefs = prefs_from_working_state(state)
    assert prefs == {"budget_max": "80"}


def test_compile_context_includes_summary_and_memory() -> None:
    shop = make_shop()
    identity = identity_for(EmployeeRole.SALES, PILOT_TENANT_ID)
    customer = shop.store.get_or_create_customer(PILOT_TENANT_ID, "59192000001")
    conv = shop.store.get_or_create_conversation(PILOT_TENANT_ID, customer)
    apply_preference_patch(
        conv.state,
        PreferencePatch(budget_max=Decimal("90"), size="M", durable=True),
    )
    shop.store.save_conversation_state(conv)
    for i in range(14):
        conv.messages.append(("customer", f"turno {i} busco algo negro"))
        conv.messages.append(("Adri", f"ok {i}"))
    maybe_refresh_summary(conv)
    text = compile_context(identity, conv, store=shop.store)
    assert "customer_memory=" in text
    assert "budget_max=90" in text
    assert "size=M" in text
    assert "conversation_summary=" in text
    assert "recent:" in text


def test_durable_prefs_survive_new_conversation_load() -> None:
    shop = make_shop()
    wa = "59192000002"
    shop.handle_turn(PILOT_TENANT_ID, wa, "hola")
    customer = shop.store.get_or_create_customer(PILOT_TENANT_ID, wa)
    conv = shop.store.get_or_create_conversation(PILOT_TENANT_ID, customer)
    apply_preference_patch(
        conv.state,
        PreferencePatch(color="negro", durable=True),
    )
    shop.store.save_conversation_state(conv)

    shop2 = make_shop()
    # Same in-memory store type but fresh — simulate prefs API on shared pattern via put.
    shop2.store.put_customer_preferences(
        PILOT_TENANT_ID, customer.id, shop.store.get_customer_preferences(PILOT_TENANT_ID, customer.id)
    )
    # Attach same customer id into shop2
    shop2.store.customers[wa] = customer
    conv2 = shop2.store.get_or_create_conversation(PILOT_TENANT_ID, customer)
    prefs = shop2.store.get_customer_preferences(PILOT_TENANT_ID, customer.id)
    assert prefs.get("color") == "negro"
    identity = identity_for(EmployeeRole.SALES, PILOT_TENANT_ID)
    ctx = compile_context(identity, conv2, store=shop2.store)
    assert "color=negro" in ctx


def test_format_customer_memory_empty() -> None:
    assert format_customer_memory() == ""
    assert "name=Ana" in format_customer_memory(name="Ana")


def test_recent_window_keeps_eighth_message() -> None:
    """Marker at index len-8 stays in recent; older falls to summary only after threshold."""
    identity = identity_for(EmployeeRole.SALES, PILOT_TENANT_ID)
    conv = Conversation(id=uuid4(), tenant_id=PILOT_TENANT_ID, customer_id=uuid4())
    # 10 messages: marker at index 2 is inside window 8, outside window 6.
    for i in range(10):
        role = "customer" if i % 2 == 0 else "Adri"
        text = f"msg-{i}"
        if i == 2:
            text = "mi talla es L PREF_MARKER_TALLA_L"
        if i == 1:
            text = "DROPPED_BY_WINDOW_8 older-edge"
        conv.messages.append((role, text))
    assert RECENT_WINDOW == 8
    ctx = compile_context(identity, conv)
    recent = ctx.split("recent:", 1)[1]
    assert "PREF_MARKER_TALLA_L" in recent
    assert "DROPPED_BY_WINDOW_8" not in recent
    recent_lines = [ln for ln in recent.splitlines() if ln.strip().startswith(("customer:", "Adri:"))]
    assert len(recent_lines) == RECENT_WINDOW


def test_compile_context_recent_window_char_budget() -> None:
    """Document ~chars for window=8 vs hypothetical window=6 on the same transcript."""
    identity = identity_for(EmployeeRole.SALES, PILOT_TENANT_ID)
    conv = Conversation(id=uuid4(), tenant_id=PILOT_TENANT_ID, customer_id=uuid4())
    for i in range(16):
        conv.messages.append(("customer" if i % 2 == 0 else "Adri", f"turno {i} detalle de prenda y talla"))
    full = compile_context(identity, conv)
    recent_block = full.split("recent:", 1)[1]
    chars_w8 = len(recent_block)
    # Same transcript sliced as if window were 6.
    lines = [f"  {role}: {text}" for role, text in conv.messages[-6:]]
    chars_w6 = len("\n" + "\n".join(lines))
    assert chars_w8 > chars_w6
    # Rough budget: window 8 should stay under ~2x a short 6-window block on this fixture.
    assert chars_w8 < chars_w6 * 2
    # Recorded for Engram/ODD checks (fixture-stable order of magnitude).
    assert 200 < chars_w8 < 2000
