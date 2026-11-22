from tests.conftest import make_shop


def test_cross_tenant_rejected() -> None:
    from uuid import uuid4

    shop = make_shop()
    try:
        shop.handle_turn(uuid4(), "5917", "hola")
        assert False, "expected cross-tenant deny"
    except PermissionError:
        pass
