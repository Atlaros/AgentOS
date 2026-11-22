from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from factory_os.agents.accounting import handle_accounting
from factory_os.agents.analyst import handle_analyst
from factory_os.agents.catalog_admin import handle_catalog_admin
from factory_os.agents.cobros import handle_cobros
from factory_os.agents.graph import run_customer_turn
from factory_os.agents.inventory import handle_inventory
from factory_os.agents.ops import handle_ops
from factory_os.agents.postventa import handle_postventa
from factory_os.agents.sales import handle_sales
from factory_os.agents.suppliers import handle_suppliers
from factory_os.contracts.employees import identity_for, is_staff_role
from factory_os.domain.models import Conversation, Customer, EmployeeRole, PaymentStatus
from factory_os.domain.store import CommerceStore
from factory_os.domain.model_usage import record_model_tokens
from factory_os.harness.bbe import BBEViolation, SkillDenied
from factory_os.harness.policy import PolicyDenied
from factory_os.harness.model_gateway import FakeGateway, ModelGateway
from factory_os.harness.agent_trace import AgentTraceLog
from factory_os.harness.tools import ConfirmationRequired, PermissionDenied, ToolRuntime
from factory_os.tools.channel import (
    Channel,
    FakeChannel,
    owner_alert_text,
    payment_qr_buttons,
    send_payment_qr,
    send_text_to_owners,
)
from factory_os.tools.payments import FakePaymentProvider, PaymentProvider


def _customer_notice(pack) -> str:
    from factory_os.domain.knowledge import shop_label

    return f"Una persona de {shop_label(pack)} ya fue avisada y puede entrar al chat."


def _stuck_marker(pack) -> str:
    from factory_os.domain.knowledge import item_word

    return f"No encontré esa {item_word(pack)}"


CUSTOMER_NOTICE = _customer_notice(None)
STUCK_MARKER = _stuck_marker(None)


def _meter_gateway_tokens(
    gateway: ModelGateway,
    tenant_id: UUID,
    *,
    url: str | None = None,
) -> None:
    event = getattr(gateway, "last_event", None) or {}
    raw = event.get("tokens") if isinstance(event, dict) else None
    if raw is None:
        return
    try:
        tokens = int(raw)
    except (TypeError, ValueError):
        return
    record_model_tokens(tenant_id, tokens, url=url)
_HUMAN_PHRASES = (
    "quiero un humano",
    "hablar con un humano",
    "hablar con alguien",
    "persona real",
    "alguien de verdad",
    "atención humana",
    "asesor humano",
    "asesor",
    "humano",
)


@dataclass
class TurnResult:
    employee: str
    role: str
    reply: str
    conversation_id: str = ""
    needs_human: bool = False
    human_takeover: bool = False


class InboxEvents:
    def __init__(self) -> None:
        self._queues: list[asyncio.Queue[dict[str, Any]]] = []

    def subscribe(self) -> asyncio.Queue[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=64)
        self._queues.append(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[dict[str, Any]]) -> None:
        if queue in self._queues:
            self._queues.remove(queue)

    def publish(self, payload: dict[str, Any]) -> None:
        for queue in list(self._queues):
            try:
                queue.put_nowait(payload)
            except asyncio.QueueFull:
                pass


def wants_human(text: str) -> bool:
    lowered = text.lower()
    return any(phrase in lowered for phrase in _HUMAN_PHRASES)


class ShopRuntime:
    def __init__(
        self,
        store: CommerceStore,
        payments: PaymentProvider | None = None,
        channel: Channel | None = None,
        owner_numbers: list[str] | None = None,
        inbox_base_url: str = "http://localhost:8000/inbox",
        gateway: ModelGateway | None = None,
        database_url: str | None = None,
        settlement_notifier=None,
    ) -> None:
        self.store = store
        self.payments = payments or FakePaymentProvider()
        from factory_os.domain.invoicing import FakeInvoicePort

        self.invoices = FakeInvoicePort()
        self.channel: Channel = channel or FakeChannel()
        self.owner_numbers = [n.strip() for n in (owner_numbers or []) if n.strip()]
        self.inbox_base_url = inbox_base_url.rstrip("/")
        self.gateway: ModelGateway = gateway or FakeGateway()
        self.database_url = (database_url or "").strip() or None
        self.settlement_notifier = settlement_notifier
        self.trace = AgentTraceLog()
        if getattr(self.gateway, "trace_log", None) is None:
            setattr(self.gateway, "trace_log", self.trace)
        else:
            self.trace = self.gateway.trace_log  # type: ignore[assignment]
        self.events = InboxEvents()
        self.tools: ToolRuntime = None  # type: ignore[assignment]
        self._bind_tools()

    def _bind_tools(self) -> None:
        from factory_os.domain.autonomy import grants_for_tenant
        from factory_os.domain.tenant_config import get_tenant_config
        from factory_os.tools.registry import build_runtime

        self.tools = build_runtime(
            self.store, self.payments, self.invoices, channel=self.channel
        )

        def autonomy_for(tenant: UUID):
            config = get_tenant_config(tenant, url=self.database_url)
            industry = (config.industry or "cafe").strip().lower() or "cafe"
            if industry == "closet":
                industry = "ropa"
            try:
                return grants_for_tenant(tenant, industry=industry, url=self.database_url)
            except KeyError:
                return grants_for_tenant(tenant, industry="cafe", url=self.database_url)

        self.tools.autonomy_for = autonomy_for

    def handle_turn(self, tenant_id: UUID, wa_number: str, text: str) -> TurnResult:
        self.store.require_tenant(tenant_id)
        from factory_os.domain.order_hold import release_expired_unpaid_orders

        release_expired_unpaid_orders(self.store, tenant_id)
        customer = self.store.get_or_create_customer(tenant_id, wa_number)
        conversation = self.store.get_or_create_conversation(tenant_id, customer)
        from factory_os.domain.memory import is_idle_reopen

        conversation.turn_idle_reopen = is_idle_reopen(conversation.last_message_at)
        self.store.append_message(conversation, "customer", text)

        if conversation.state.human_takeover:
            self.store.save_conversation_state(conversation)
            self._publish(conversation, customer)
            return TurnResult(
                employee="Humano",
                role="human",
                reply="",
                conversation_id=str(conversation.id),
                needs_human=True,
                human_takeover=True,
            )

        if wants_human(text):
            pack = self.store.get_shop_knowledge(tenant_id)
            reply = _customer_notice(pack)
            self._mark_needs_human(conversation, customer, "El cliente pidió una persona")
            conversation.state.graph_node = "human_pause"
            self.store.append_message(conversation, "Closet", reply)
            self.store.save_conversation_state(conversation)
            self._publish(conversation, customer)
            return TurnResult(
                employee="Closet",
                role="human_requested",
                reply=reply,
                conversation_id=str(conversation.id),
                needs_human=True,
                human_takeover=False,
            )

        self.trace.begin_turn(
            conversation_id=conversation.id,
            employee="orchestrator",
            role="orchestrator",
        )
        try:
            role, reply = run_customer_turn(
                store=self.store,
                tools=self.tools,
                gateway=self.gateway,
                conversation=conversation,
                customer=customer,
                tenant_id=tenant_id,
                wa_number=wa_number,
                text=text,
                trace=self.trace,
                database_url=self.database_url,
            )
            identity = identity_for(role, tenant_id)
            self.trace.begin_turn(
                conversation_id=conversation.id,
                employee=identity.employee_name,
                role=identity.role.value,
            )
        except PermissionDenied as exc:
            role = conversation.state.last_employee or EmployeeRole.SALES
            identity = identity_for(role, tenant_id)
            reply = f"Esa acción no está permitida para {identity.employee_name}."
            _ = exc
        except (BBEViolation, PolicyDenied, SkillDenied, ConfirmationRequired) as exc:
            role = conversation.state.last_employee or EmployeeRole.SALES
            identity = identity_for(role, tenant_id)
            reply = f"El runtime bloqueó la acción: {exc}"
        finally:
            _meter_gateway_tokens(self.gateway, tenant_id, url=self.database_url)
            self.trace.end_turn()

        stuck_pack = self.store.get_shop_knowledge(tenant_id)
        if _stuck_marker(stuck_pack) in reply:
            first_alert = not conversation.state.owner_notified
            from factory_os.domain.knowledge import item_word

            self._mark_needs_human(
                conversation,
                customer,
                f"Adri no encontró la {item_word(stuck_pack)} en el catálogo",
            )
            if first_alert:
                reply = f"{reply}\n\n{_customer_notice(stuck_pack)}"

        conversation.state.last_employee = role
        identity = identity_for(role, tenant_id)
        self.store.append_message(conversation, identity.employee_name, reply)
        self.store.save_conversation_state(conversation)
        self._publish(conversation, customer)
        return TurnResult(
            employee=identity.employee_name,
            role=role.value,
            reply=reply,
            conversation_id=str(conversation.id),
            needs_human=conversation.state.needs_human,
            human_takeover=conversation.state.human_takeover,
        )

    def _run_employee(
        self,
        identity,
        conversation: Conversation,
        customer: Customer,
        wa_number: str,
        text: str,
    ) -> str:
        role = identity.role
        if role is EmployeeRole.SALES:
            return handle_sales(
                identity, self.tools, conversation, customer.id, text, self.gateway, store=self.store
            )
        if role is EmployeeRole.COBROS:
            return handle_cobros(
                identity, self.tools, conversation, self.gateway, text=text, store=self.store
            )
        if role is EmployeeRole.OPS:
            return handle_ops(
                identity, self.tools, conversation, wa_number, text, self.gateway, store=self.store
            )
        if role is EmployeeRole.POSTVENTA:
            return handle_postventa(
                identity, self.tools, conversation, text, self.gateway, store=self.store
            )
        if role is EmployeeRole.INVENTORY:
            return handle_inventory(identity, self.tools, conversation, text)
        if role is EmployeeRole.ACCOUNTING:
            return handle_accounting(identity, self.tools, conversation, text)
        if role is EmployeeRole.ANALYST:
            return handle_analyst(
                identity, self.tools, conversation, text, self.gateway, store=self.store
            )
        if role is EmployeeRole.SUPPLIERS:
            return handle_suppliers(identity, self.tools, conversation, text)
        return handle_catalog_admin(identity, self.tools, conversation, text)

    def handle_staff(self, tenant_id: UUID, role: EmployeeRole, text: str) -> TurnResult:
        if not is_staff_role(role):
            raise ValueError("staff role required")
        self.store.require_tenant(tenant_id)
        customer = self.store.get_or_create_customer(tenant_id, f"staff-{role.value}")
        conversation = self.store.get_or_create_conversation(tenant_id, customer)
        conversation.state.channel = "internal"
        self.store.append_message(conversation, "staff", text)
        identity = identity_for(role, tenant_id)
        self.trace.begin_turn(
            conversation_id=conversation.id,
            employee=identity.employee_name,
            role=identity.role.value,
        )
        try:
            reply = self._run_employee(identity, conversation, customer, customer.wa_number, text)
        except PermissionDenied as exc:
            reply = f"Esa acción no está permitida para {identity.employee_name}."
            _ = exc
        except (BBEViolation, PolicyDenied, SkillDenied, ConfirmationRequired) as exc:
            reply = f"El runtime bloqueó la acción: {exc}"
        finally:
            _meter_gateway_tokens(self.gateway, tenant_id, url=self.database_url)
            self.trace.end_turn()
        conversation.state.last_employee = role
        self.store.append_message(conversation, identity.employee_name, reply)
        self.store.save_conversation_state(conversation)
        self._publish(conversation, customer)
        return TurnResult(
            employee=identity.employee_name,
            role=role.value,
            reply=reply,
            conversation_id=str(conversation.id),
        )

    def handle_inbound(self, tenant_id: UUID, wa_number: str, text: str) -> TurnResult:
        result = self.handle_turn(tenant_id, wa_number, text)
        if result.reply:
            self.channel.send_text(wa_number, result.reply)
        self._deliver_payment_qr(tenant_id, result.conversation_id, wa_number)
        self._deliver_location_request(tenant_id, result.conversation_id, wa_number)
        return result

    def _deliver_payment_qr(self, tenant_id: UUID, conversation_id: str, wa_number: str) -> None:
        """After Cobros issues/resends a QR, send Baneco image + action buttons once."""
        if not conversation_id:
            return
        try:
            from uuid import UUID as _UUID

            conversation = self._require_conversation(tenant_id, _UUID(conversation_id))
        except Exception:
            return
        state = conversation.state
        if state.payment_id is None or not state.provider_ref:
            return
        reason = str(state.folder.reason or "") if state.folder is not None else ""
        if reason not in {"qr_issued", "qr_resent"}:
            return
        payment = self.store.get_payment(tenant_id, state.payment_id)
        if payment is None:
            return
        from factory_os.domain.models import EmployeeRole, PaymentStatus

        if payment.status is PaymentStatus.CONFIRMED:
            return
        send_payment_qr(
            self.channel,
            wa_number,
            payment.qr_payload,
            amount=str(payment.amount),
            currency=payment.currency or "BOB",
        )
        body = (
            "El pago es solo con QR. Cuando transferís, mandame el comprobante o tocá Ya transferí "
            "para consultar al banco (eso no confirma el cobro). Si no ves la imagen, tocá Reenviar QR."
        )
        try:
            self.channel.send_reply_buttons(wa_number, body, payment_qr_buttons())
        except Exception:
            return
        # Flip reason so the next inbound does not re-fire image+buttons.
        state.pass_to(
            EmployeeRole.COBROS,
            from_role=EmployeeRole.COBROS,
            pending="wait_adapter",
            reason="qr_awaiting_bank",
            payment_state="pending",
        )
        self.store.save_conversation_state(conversation)

    def _deliver_location_request(
        self, tenant_id: UUID, conversation_id: str, wa_number: str
    ) -> None:
        """After pago confirmado, pedir pin de Maps una sola vez. No reenviar al pedir el nombre."""
        if not conversation_id:
            return
        try:
            from uuid import UUID as _UUID

            conversation = self._require_conversation(tenant_id, _UUID(conversation_id))
        except Exception:
            return
        folder = conversation.state.folder
        if folder is None:
            return
        reason = str(folder.reason or "")
        # Only the first bank-confirm handoff. need_shipping_data must not re-fire Maps.
        if reason != "payment_confirmed":
            return
        if folder.pending != "collect_address":
            return
        send = getattr(self.channel, "send_location_request", None)
        if not callable(send):
            return
        try:
            send(
                wa_number,
                "Para el envío, compartí tu ubicación de Maps (o escribí la dirección).",
            )
        except Exception:
            return
        from factory_os.domain.models import EmployeeRole

        # Avoid re-sending the Maps prompt on every follow-up while collecting address.
        conversation.state.pass_to(
            EmployeeRole.OPS,
            from_role=EmployeeRole.OPS,
            pending="collect_address",
            reason="awaiting_shipping_data",
            payment_state="confirmed",
        )
        self.store.save_conversation_state(conversation)
    def set_takeover(self, tenant_id: UUID, conversation_id: UUID, active: bool) -> Conversation:
        conversation = self._require_conversation(tenant_id, conversation_id)
        conversation.state.human_takeover = active
        conversation.state.needs_human = active
        self.store.save_conversation_state(conversation)
        customer = self.store.get_customer(tenant_id, conversation.customer_id)
        if customer:
            self._publish(conversation, customer)
        return conversation

    def human_reply(self, tenant_id: UUID, conversation_id: UUID, text: str) -> Conversation:
        conversation = self._require_conversation(tenant_id, conversation_id)
        if not conversation.state.human_takeover:
            conversation = self.set_takeover(tenant_id, conversation_id, True)
        customer = self.store.get_customer(tenant_id, conversation.customer_id)
        if customer is None:
            raise KeyError("customer")
        self.store.append_message(conversation, "Humano", text)
        self.store.save_conversation_state(conversation)
        self.channel.send_text(customer.wa_number, text)
        self._publish(conversation, customer)
        return conversation

    def confirm_payment_from_adapter(self, provider_ref: str) -> None:
        confirm = getattr(self.payments, "confirm", None)
        if callable(confirm):
            confirm(provider_ref)
        self.store.confirm_from_adapter(provider_ref)
        payment = self.store.payment_status(self.store.tenant_id, provider_ref)
        if payment is not None and payment.order_id is not None:
            self._remember_confirmed_order(payment, provider_ref)
        self._notify_settlement(payment)

    def _remember_confirmed_order(self, payment, provider_ref: str) -> None:
        for conversation in self.store.list_conversations(self.store.tenant_id):
            if conversation.state.provider_ref != provider_ref and conversation.state.payment_id != payment.id:
                continue
            conversation.state.order_id = payment.order_id
            conversation.state.folder.order_id = payment.order_id
            self.store.save_conversation_state(conversation)

    def _notify_settlement(self, payment) -> None:
        if payment is None or payment.status is not PaymentStatus.CONFIRMED:
            return
        if self.settlement_notifier is None:
            return
        try:
            self.settlement_notifier(payment)
        except Exception:
            return

    def apply_payment_webhook(self, raw: bytes, headers: dict[str, str]) -> dict[str, str]:
        """Parse adapter webhook; confirm only when state is confirmed and event is new."""
        from factory_os.domain.models import PaymentStatus

        event = self.payments.parse_webhook(raw, headers)
        is_new = self.store.record_webhook_event(
            self.store.tenant_id,
            event_id=event.event_id,
            provider=self.payments.name,
            provider_ref=event.provider_reference,
            state=event.state.value,
            payload={"headers": {k: v for k, v in headers.items() if k.lower().startswith("x-")}},
        )
        # Replays also retry the idempotent store transition. If the process
        # failed after recording the event but before placing the order, the
        # bank's retry must be able to finish that transition.
        if event.state is PaymentStatus.CONFIRMED:
            self.confirm_payment_from_adapter(event.provider_reference)
        return {
            "status": "ok" if is_new else "duplicate",
            "event_id": event.event_id,
            "provider_ref": event.provider_reference,
            "payment_state": event.state.value,
        }

    def _require_conversation(self, tenant_id: UUID, conversation_id: UUID) -> Conversation:
        self.store.require_tenant(tenant_id)
        conversation = self.store.get_conversation(tenant_id, conversation_id)
        if conversation is None:
            raise KeyError("conversation")
        return conversation

    def _mark_needs_human(self, conversation: Conversation, customer: Customer, reason: str) -> None:
        conversation.state.needs_human = True
        if conversation.state.owner_notified:
            return
        alert = owner_alert_text(
            name=customer.name,
            wa_number=customer.wa_number,
            reason=reason,
            inbox_url=self.inbox_base_url,
            conversation_id=str(conversation.id),
        )
        if not self.owner_numbers:
            conversation.state.owner_notified = True
            return
        if send_text_to_owners(self.channel, self.owner_numbers, alert):
            conversation.state.owner_notified = True

    def _publish(self, conversation: Conversation, customer: Customer) -> None:
        self.events.publish(
            {
                "type": "conversation",
                "id": str(conversation.id),
                "wa_number": customer.wa_number,
                "needs_human": conversation.state.needs_human,
                "human_takeover": conversation.state.human_takeover,
                "stage": conversation.state.stage.value,
                "skill": conversation.state.last_skill,
                "nba": conversation.state.last_action,
                "employee": conversation.state.last_employee.value if conversation.state.last_employee else None,
            }
        )
