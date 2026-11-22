import pytest

from factory_os.contracts.employees import identity_for
from factory_os.domain.models import EmployeeRole, PILOT_TENANT_ID
from factory_os.harness.tools import PermissionDenied
from tests.conftest import make_shop


def test_sales_cannot_create_qr() -> None:
    shop = make_shop()
    adri = identity_for(EmployeeRole.SALES, PILOT_TENANT_ID)
    with pytest.raises(PermissionDenied):
        shop.tools.execute(adri, "payment.create_qr", {"order_id": "x"})


def test_context_compiler_is_compact() -> None:
    from factory_os.harness.context import compile_context
    from factory_os.domain.models import Conversation
    from uuid import uuid4

    identity = identity_for(EmployeeRole.SALES, PILOT_TENANT_ID)
    conv = Conversation(id=uuid4(), tenant_id=PILOT_TENANT_ID, customer_id=uuid4())
    conv.messages = [("customer", "hola"), ("Adri", "ok")]
    text = compile_context(identity, conv)
    assert "Adri" in text
    assert str(PILOT_TENANT_ID) in text
    assert "shop=Authentic Closet" in text
