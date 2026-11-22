from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable
from uuid import UUID

from factory_os.contracts.employees import Identity
from factory_os.domain.models import Conversation, WorkingState
from factory_os.harness.bbe import BBEAuditLog, evaluate_bbe, evaluate_skill
from factory_os.harness.policy import PolicyEngine


class PermissionDenied(Exception):
    pass


class UnknownTool(Exception):
    pass


class ConfirmationRequired(Exception):
    def __init__(self, tool_name: str) -> None:
        super().__init__(f"{tool_name} requires runtime confirmation")
        self.tool_name = tool_name


@dataclass(frozen=True)
class ToolSpec:
    name: str
    permission: str
    read_only: bool
    handler: Callable[[Identity, dict[str, Any]], dict[str, Any]]
    confirmation_required: bool = False
    description: str = ""


class ToolRuntime:
    def __init__(
        self,
        specs: list[ToolSpec],
        policy: PolicyEngine | None = None,
        bbe_audit: BBEAuditLog | None = None,
        autonomy_for: Callable[[UUID], tuple] | None = None,
    ) -> None:
        self._specs = {spec.name: spec for spec in specs}
        self._policy = policy
        self.bbe_audit = bbe_audit or BBEAuditLog()
        self.handler_calls = 0
        self.autonomy_for = autonomy_for

    def execute(
        self,
        identity: Identity,
        name: str,
        payload: dict[str, Any],
        *,
        skill: str | None = None,
        channel: str = "internal",
        confirmed: bool = False,
        state: WorkingState | None = None,
        autonomy: tuple | None = None,
    ) -> dict[str, Any]:
        spec = self._specs.get(name)
        if spec is None:
            raise UnknownTool(name)
        if spec.permission not in identity.permissions:
            raise PermissionDenied(f"{identity.employee_name} cannot run {name}")
        evaluate_bbe(identity, name, channel=channel, payload=payload, audit=self.bbe_audit)
        evaluate_skill(
            identity,
            skill,
            name,
            state=state,
            payload=payload,
            read_only=spec.read_only,
        )
        if self._policy is not None:
            self._policy.evaluate(identity, name, payload)
        if spec.confirmation_required and not confirmed and not payload.get("confirmed"):
            raise ConfirmationRequired(name)
        from factory_os.domain.autonomy import AutonomyDenied, autonomy_decision, template_autonomy

        if autonomy is not None:
            grants = autonomy
        elif self.autonomy_for is not None:
            grants = self.autonomy_for(identity.tenant_id)
        else:
            grants = template_autonomy("cafe")
        decision = autonomy_decision(
            grants,
            name,
            payload,
            confirmed=confirmed or bool(payload.get("confirmed")),
        )
        if decision is not None:
            kind, action = decision
            if kind == "deny":
                raise AutonomyDenied(action)
            raise ConfirmationRequired(name)
        self.handler_calls += 1
        return spec.handler(identity, payload)


def run_tool(
    runtime: ToolRuntime,
    identity: Identity,
    conversation: Conversation,
    name: str,
    payload: dict[str, Any],
    *,
    confirmed: bool = False,
) -> dict[str, Any]:
    return runtime.execute(
        identity,
        name,
        payload,
        skill=conversation.state.last_skill,
        channel=conversation.state.channel,
        confirmed=confirmed,
        state=conversation.state,
    )
