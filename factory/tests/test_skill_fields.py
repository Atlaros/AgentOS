import pytest

from factory_os.contracts.employees import ROLE_PERMISSIONS, identity_for
from factory_os.contracts.skills import ADRI_SKILLS, COBROS_SKILLS
from factory_os.domain.models import EmployeeRole, PILOT_TENANT_ID, WorkingState
from factory_os.harness.bbe import SkillDenied, evaluate_skill
from factory_os.harness.tools import PermissionDenied
from tests.conftest import make_shop


def test_skill_fields_are_contract_not_keys() -> None:
    closing = next(skill for skill in ADRI_SKILLS if skill.name == "sales_closing")
    assert closing.required_context == ("considered_variant_or_cart",)
    assert "create_order" in closing.action_types
    assert closing.handoff_condition is not None
    assert "Cobros" in closing.handoff_condition
    assert closing.preconditions == closing.required_context
    assert "payment.create_qr" not in closing.related_tools
    assert "payment.create_qr" not in ROLE_PERMISSIONS[EmployeeRole.SALES]

    initiation = next(skill for skill in COBROS_SKILLS if skill.name == "payment_initiation")
    assert initiation.required_context == ("variant_sku",)
    assert initiation.handoff_condition is not None


def test_sales_closing_cannot_unlock_payment() -> None:
    shop = make_shop()
    adri = identity_for(EmployeeRole.SALES, PILOT_TENANT_ID)
    before = shop.tools.handler_calls
    with pytest.raises(PermissionDenied):
        shop.tools.execute(
            adri,
            "payment.create_qr",
            {"order_id": "x"},
            skill="sales_closing",
        )
    assert shop.tools.handler_calls == before


def test_write_without_required_context_is_skill_denied() -> None:
    shop = make_shop()
    adri = identity_for(EmployeeRole.SALES, PILOT_TENANT_ID)
    before = shop.tools.handler_calls
    with pytest.raises(SkillDenied) as denied:
        shop.tools.execute(
            adri,
            "order.create",
            {"variant_sku": "h001-M-VP", "customer_id": str(shop.store.tenant_id)},
            skill="sales_closing",
            confirmed=True,
            state=WorkingState(),
        )
    assert "considered_variant_or_cart" in str(denied.value)
    assert shop.tools.handler_calls == before


def test_read_skips_required_context() -> None:
    evaluate_skill(
        identity_for(EmployeeRole.COBROS, PILOT_TENANT_ID),
        "payment_verification",
        "payment.status",
        state=WorkingState(),
        read_only=True,
    )
