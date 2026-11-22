from factory_os.contracts.employees import CONCEPTUAL_ROLES, ROLE_PERMISSIONS, identity_for
from factory_os.domain.models import EmployeeRole, PILOT_TENANT_ID


def test_seven_conceptual_roles_and_three_runtime_employees() -> None:
    keys = [role.key for role in CONCEPTUAL_ROLES]
    assert keys == [
        "orchestrator",
        "sales",
        "collections",
        "ops",
        "postventa",
        "inventory",
        "catalog_admin",
        "accounting",
        "analyst",
        "suppliers",
    ]
    runtime = [role for role in CONCEPTUAL_ROLES if role.runtime]
    assert len(runtime) == 10
    assert EmployeeRole.ACCOUNTING in set(EmployeeRole)
    assert EmployeeRole.ANALYST in set(EmployeeRole)
    assert EmployeeRole.SUPPLIERS in set(EmployeeRole)
    adri = identity_for(EmployeeRole.SALES, PILOT_TENANT_ID)
    assert adri.employee_name == "Adri"
    assert "catalog.search" in ROLE_PERMISSIONS[EmployeeRole.SALES]
    assert "payment.create_qr" in ROLE_PERMISSIONS[EmployeeRole.COBROS]
    assert "delivery.create" in ROLE_PERMISSIONS[EmployeeRole.OPS]
    # Shared READ of payment.status (ADR-004); Adri still cannot create QR.
    assert "payment.create_qr" not in ROLE_PERMISSIONS[EmployeeRole.SALES]
    assert "payment.status" in ROLE_PERMISSIONS[EmployeeRole.SALES]
    assert "payment.status" in ROLE_PERMISSIONS[EmployeeRole.COBROS]
