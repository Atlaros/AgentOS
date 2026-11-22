"""Document text becomes a shop-knowledge proposal. It does not write."""

from __future__ import annotations

import pytest

from factory_os.domain.knowledge_ingest import propose_shop_pack_from_text, text_from_upload


def test_propose_maps_vision_mission_and_faq() -> None:
    proposal = propose_shop_pack_from_text(
        "Visión\nVestir con intención.\n\nMisión\nAcompañar cada compra.\n\n"
        "P: ¿Hacen cambios?\nR: Sí, dentro de siete días.\n"
    )
    assert proposal["profile"]["vision"] == ["Vestir con intención."]
    assert proposal["profile"]["mission"] == ["Acompañar cada compra."]
    faq = proposal["faqs"][0]
    assert faq["id"] == "hacen-cambios"
    assert faq["question"] == "¿Hacen cambios?"
    assert faq["answer"] == "Sí, dentro de siete días."
    assert "price" not in proposal
    assert "price" not in proposal["profile"]
    assert "stock" not in proposal
    assert "payment_status" not in proposal


def test_price_prose_does_not_become_a_profile_key() -> None:
    proposal = propose_shop_pack_from_text(
        'Visión\nLa mejor tienda. El borrador dice "price": 99 y stock 3.\n'
    )
    assert "price" not in proposal
    assert "price" not in proposal["profile"]
    assert "stock" not in proposal["profile"]
    assert "payment_status" not in proposal
    assert '"price": 99' in proposal["profile"]["vision"][0]


def test_faq_slug_collision_uses_faq_n() -> None:
    proposal = propose_shop_pack_from_text(
        "P: ¿Hacen cambios?\nR: Sí.\n\nP: ¿Hacen cambios?\nR: También en sucursal.\n"
    )
    ids = [row["id"] for row in proposal["faqs"]]
    assert ids[0] == "hacen-cambios"
    assert ids[1] == "faq-2"
    assert len(set(ids)) == 2


def test_question_paragraph_and_hours_branches() -> None:
    proposal = propose_shop_pack_from_text(
        "Horario\n9:00 a 21:00\n\n"
        "Sucursales\nCentro | 9 a 18 | Calle Larga 1 | 7001001\n\n"
        "¿Hacen delivery?\nSí, a todo Bolivia.\n"
    )
    assert proposal["profile"]["hours"] == "9:00 a 21:00"
    assert proposal["profile"]["branches"] == [
        {"name": "Centro", "hours": "9 a 18", "address": "Calle Larga 1", "phone": "7001001"}
    ]
    assert proposal["faqs"][0]["question"] == "¿Hacen delivery?"
    assert proposal["faqs"][0]["answer"] == "Sí, a todo Bolivia."


def test_kind_biases_unlabeled_text_and_still_keeps_labeled_sections() -> None:
    hours = propose_shop_pack_from_text("Lunes a sábado de 9 a 21.", kind="hours")
    assert hours["profile"]["hours"] == "Lunes a sábado de 9 a 21."
    mixed = propose_shop_pack_from_text(
        "Visión\nSer la referencia del barrio.\n\nHorario\nLunes a sábado de 9 a 21.\n",
        kind="faq",
    )
    assert mixed["profile"]["vision"] == ["Ser la referencia del barrio."]
    assert mixed["profile"]["hours"] == "Lunes a sábado de 9 a 21."


def test_policy_sections_become_form_fields() -> None:
    proposal = propose_shop_pack_from_text(
        "Devoluciones\nNo se aceptan.\n\nCambios\nSí, en 7 días.\n\nCancelación\nAntes del envío.\n"
    )
    assert proposal["policies"]["returns"] is False
    assert proposal["policies"]["exchanges"] is True
    assert "7 días" in proposal["policies"]["claims"]
    assert proposal["policies"]["cancel"] == "Antes del envío."


def test_text_from_upload_rejects_pdf_and_reads_txt() -> None:
    with pytest.raises(ValueError, match="unsupported_document"):
        text_from_upload("manual.pdf", b"%PDF-1.4\n%binary")
    with pytest.raises(ValueError, match="unsupported_document"):
        text_from_upload("ficha.docx", b"PK\x03\x04fake-docx")
    assert text_from_upload("faq.txt", "Hola\x00 mundo".encode()) == "Hola mundo"
    assert text_from_upload("notas.md", b"# Hola", content_type="") == "# Hola"
    assert text_from_upload("tabla.csv", b"a,b\n1,2") == "a,b\n1,2"
    assert text_from_upload("pegado", "texto".encode(), content_type="text/plain") == "texto"
