from factory_os.domain.process_catalog import diagnose_processes
from factory_os.domain.provision import TEMPLATE_MODULES


def test_cafe_diagnosis_marks_bar_as_gap_with_shared_palette() -> None:
    rows = diagnose_processes("cafe", TEMPLATE_MODULES["cafe"])
    by_id = {row.process_id: row for row in rows}
    assert by_id["wa_order"].status == "covered"
    assert by_id["counter_sale"].status == "covered"
    assert by_id["bar_queue"].status == "gap"
    assert by_id["bar_queue"].gaps == ("barra",)


def test_ropa_restock_partial_without_proveedores() -> None:
    rows = diagnose_processes("ropa", ("whatsapp", "pedido", "cobros", "catalogo"))
    by_id = {row.process_id: row for row in rows}
    assert by_id["wa_order"].status == "covered"
    assert by_id["restock"].status == "partial"
    assert by_id["restock"].gaps == ("proveedores",)
    assert "catalogo" in by_id["restock"].evidence
