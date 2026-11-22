from uuid import uuid4

from factory_os.domain.tenant_config import (
    clear_memory_tenant_configs,
    get_tenant_config,
    put_tenant_config,
)


def test_tenant_config_is_per_tenant_in_memory() -> None:
    clear_memory_tenant_configs()
    cafe = uuid4()
    ropa = uuid4()
    put_tenant_config(cafe, industry="cafe", modules=["caja", "cobros"])
    put_tenant_config(ropa, industry="ropa", modules=["catalogo"])
    assert get_tenant_config(cafe).industry == "cafe"
    assert get_tenant_config(cafe).modules == ("caja", "cobros")
    assert get_tenant_config(ropa).industry == "ropa"
    assert "caja" not in get_tenant_config(ropa).modules


def test_unknown_tenant_defaults_to_closet() -> None:
    clear_memory_tenant_configs()
    config = get_tenant_config(uuid4())
    assert config.industry == "closet"
    assert config.modules == ()
