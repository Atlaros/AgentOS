"""Canvas node catalog lives in packages/contracts."""

from __future__ import annotations

from factory_os.contracts.nodes import (
    NODE_BY_KIND,
    NODE_CATALOG,
    pago_confirmado_sources,
    palette_kinds,
)
from factory_os.domain.flow_canvas import palette_modules, place_module


def test_catalog_is_the_single_source_for_the_palette() -> None:
    assert set(palette_modules()) == {node.kind for node in NODE_CATALOG}
    assert set(palette_kinds()) == set(palette_modules())
    assert "aprobacion" in palette_modules()
    assert "catalogo" in palette_modules()
    assert "sql" not in palette_modules()


def test_pago_confirmado_only_leaves_cobros() -> None:
    assert pago_confirmado_sources() == ("cobros",)
    for node in NODE_CATALOG:
        if "pago_confirmado" in node.ports_out:
            assert node.kind == "cobros"


def test_unknown_kind_cannot_be_placed() -> None:
    try:
        place_module("sql")
    except ValueError as exc:
        assert str(exc) == "unknown_module"
    else:
        raise AssertionError("expected unknown_module")


def test_each_node_declares_module_autonomy_and_industries() -> None:
    for node in NODE_CATALOG:
        assert node.module
        assert node.industries
        assert node.kind in NODE_BY_KIND
        assert set(node.industries) <= {"cafe", "ropa"}
