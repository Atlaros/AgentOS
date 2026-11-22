"""Channel.send_template for supplier OC (Fake + Meta shape)."""

from __future__ import annotations

from factory_os.tools.channel import FakeChannel


def test_fake_channel_records_template_and_mirror_sent() -> None:
    channel = FakeChannel()
    channel.send_template(
        "59170000001",
        name="supplier_order",
        language="es",
        body_parameters=["Pedido PO-ABC123 — líneas"],
    )
    assert len(channel.templates) == 1
    entry = channel.templates[0]
    assert entry["wa_number"] == "59170000001"
    assert entry["name"] == "supplier_order"
    assert entry["language"] == "es"
    assert entry["body_parameters"] == ["Pedido PO-ABC123 — líneas"]
    assert channel.sent
    assert "[template supplier_order]" in channel.sent[0][1]

def test_fake_channel_template_without_parameters() -> None:
    channel = FakeChannel()
    channel.send_template("5917", name="minimal", language="es")
    assert channel.templates[0]["body_parameters"] == []
    assert "template:minimal" in channel.sent[0][1]