"""QR image decode + WhatsApp inbound buttons."""

from factory_os.tools.channel import FakeChannel, parse_inbound, payment_qr_buttons, send_payment_qr
from factory_os.tools.qr_media import decode_qr_image, looks_like_image_payload


TINY_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


def test_decode_baneco_png_base64() -> None:
    assert looks_like_image_payload(TINY_PNG_B64)
    assert not looks_like_image_payload("QR:pay-abc:1.00 BOB")
    decoded = decode_qr_image(TINY_PNG_B64)
    assert decoded is not None
    assert decoded.mime == "image/png"
    assert decoded.content[:8] == b"\x89PNG\r\n\x1a\n"


def test_send_payment_qr_records_image_on_fake_channel() -> None:
    channel = FakeChannel()
    assert send_payment_qr(channel, "5917001", TINY_PNG_B64, amount="1.00", currency="BOB")
    assert len(channel.images) == 1
    assert channel.images[0]["caption"].startswith("QR para pagar")
    assert send_payment_qr(channel, "5917001", "QR:pay-x:1.00 BOB") is False


def test_parse_inbound_button_and_location() -> None:
    buttons = parse_inbound(
        {
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "messages": [
                                    {
                                        "from": "5917111",
                                        "id": "wamid.btn",
                                        "type": "interactive",
                                        "interactive": {
                                            "type": "button_reply",
                                            "button_reply": {
                                                "id": "pay_check",
                                                "title": "Ya transferí",
                                            },
                                        },
                                    }
                                ]
                            }
                        }
                    ]
                }
            ]
        }
    )
    assert len(buttons) == 1
    assert buttons[0].text == "ya pagué"

    receipt = parse_inbound(
        {
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "messages": [
                                    {
                                        "from": "5917111",
                                        "id": "wamid.img",
                                        "type": "image",
                                        "image": {"id": "media.1", "mime_type": "image/jpeg"},
                                    }
                                ]
                            }
                        }
                    ]
                }
            ]
        }
    )
    assert receipt[0].text == "te envío el comprobante de pago"

    captioned = parse_inbound(
        {
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "messages": [
                                    {
                                        "from": "5917111",
                                        "id": "wamid.img2",
                                        "type": "image",
                                        "image": {
                                            "id": "media.2",
                                            "caption": "acá el voucher",
                                        },
                                    }
                                ]
                            }
                        }
                    ]
                }
            ]
        }
    )
    assert captioned[0].text == "acá el voucher"

    resend = parse_inbound(
        {
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "messages": [
                                    {
                                        "from": "5917111",
                                        "id": "wamid.r",
                                        "type": "interactive",
                                        "interactive": {
                                            "button_reply": {
                                                "id": "pay_resend_qr",
                                                "title": "Reenviar QR",
                                            }
                                        },
                                    }
                                ]
                            }
                        }
                    ]
                }
            ]
        }
    )
    assert resend[0].text == "reenviame el qr"

    loc = parse_inbound(
        {
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "messages": [
                                    {
                                        "from": "5917222",
                                        "id": "wamid.loc",
                                        "type": "location",
                                        "location": {
                                            "latitude": -17.78,
                                            "longitude": -63.18,
                                            "name": "Casa",
                                        },
                                    }
                                ]
                            }
                        }
                    ]
                }
            ]
        }
    )
    assert "maps" in loc[0].text
    assert "-17.78" in loc[0].text


def test_ops_registers_delivery_from_maps_pin() -> None:
    from factory_os.agents.turn import ShopRuntime
    from factory_os.domain.models import EmployeeRole, PILOT_TENANT_ID
    from factory_os.domain.seed import closet_seed_path, extra_seed_paths, load_catalog_json
    from factory_os.domain.store import MemoryCommerceStore
    from factory_os.tools.payments import FakePaymentProvider

    store = MemoryCommerceStore(PILOT_TENANT_ID)
    load_catalog_json(closet_seed_path(), store)
    for path in extra_seed_paths("closet"):
        load_catalog_json(path, store)
    channel = FakeChannel()
    shop = ShopRuntime(store, FakePaymentProvider(), channel=channel)
    import factory_os.agents.graph as graph_mod

    graph_mod._GRAPH = None
    wa = "59170008802"
    shop.handle_turn(PILOT_TENANT_ID, wa, "quiero una blusa de seda")
    shop.handle_turn(PILOT_TENANT_ID, wa, "confirmo")
    conv = store.list_conversations(PILOT_TENANT_ID)[0]
    shop.confirm_payment_from_adapter(conv.state.provider_ref)
    paid = shop.handle_inbound(PILOT_TENANT_ID, wa, "ya pagué")
    assert "Pago confirmado" in paid.reply
    assert channel.location_requests, "expected Maps location request after pago confirmado"

    # Pin then name across turns.
    pin = shop.handle_turn(
        PILOT_TENANT_ID, wa, "mi ubicacion maps: -17.78,-63.18 (Casa)"
    )
    assert pin.employee == "Operaciones"
    assert "nombre" in pin.reply.lower()
    ship = shop.handle_turn(PILOT_TENANT_ID, wa, "me llamo Ana")
    assert ship.employee == "Operaciones"
    assert "Envío registrado" in ship.reply or "pedido es #" in ship.reply
    assert "Ana" in ship.reply
    assert "Maps -17.78,-63.18" in ship.reply
    assert "#" in ship.reply
    conv = store.list_conversations(PILOT_TENANT_ID)[0]
    assert conv.state.folder.reason == "delivery_registered"
    assert conv.state.folder.to is EmployeeRole.OPS


def test_receipt_image_and_button_both_read_payment_status() -> None:
    """Comprobante and Ya transferí both READ status; neither WRITEs paid. No Maps re-ask."""
    from factory_os.agents.turn import ShopRuntime
    from factory_os.domain.models import PILOT_TENANT_ID
    from factory_os.domain.seed import closet_seed_path, extra_seed_paths, load_catalog_json
    from factory_os.domain.store import MemoryCommerceStore
    from factory_os.tools.payments import FakePaymentProvider

    store = MemoryCommerceStore(PILOT_TENANT_ID)
    load_catalog_json(closet_seed_path(), store)
    for path in extra_seed_paths("closet"):
        load_catalog_json(path, store)
    channel = FakeChannel()
    shop = ShopRuntime(store, FakePaymentProvider(), channel=channel)
    import factory_os.agents.graph as graph_mod

    graph_mod._GRAPH = None
    wa = "59170008811"
    shop.handle_turn(PILOT_TENANT_ID, wa, "quiero pago1")
    shop.handle_turn(PILOT_TENANT_ID, wa, "confirmo")
    conv = store.list_conversations(PILOT_TENANT_ID)[0]
    assert conv.state.provider_ref

    via_receipt = shop.handle_turn(PILOT_TENANT_ID, wa, "te envío el comprobante de pago")
    assert via_receipt.employee == "Cobros"
    assert "banco" in via_receipt.reply.lower() or "comprobante" in via_receipt.reply.lower()
    conv = store.list_conversations(PILOT_TENANT_ID)[0]
    assert conv.state.folder.payment_state == "pending"
    assert conv.state.folder.reason == "customer_claimed_paid"
    pay = store.get_payment(PILOT_TENANT_ID, conv.state.payment_id)
    assert pay is not None and pay.status.value != "confirmed"

    shop.confirm_payment_from_adapter(conv.state.provider_ref)
    via_button = shop.handle_inbound(PILOT_TENANT_ID, wa, "ya pagué")
    assert "confirmado" in via_button.reply.lower()
    assert channel.location_requests
    first_loc = len(channel.location_requests)

    pin = shop.handle_turn(
        PILOT_TENANT_ID, wa, "mi ubicacion maps: -17.78,-63.18 (Casa)"
    )
    assert "nombre" in pin.reply.lower()
    assert len(channel.location_requests) == first_loc

    bye = shop.handle_turn(PILOT_TENANT_ID, wa, "gracias")
    assert "nombre" in bye.reply.lower()
    assert "todo registrado" not in bye.reply.lower()
    assert "sera enviada" not in bye.reply.lower()
    assert len(channel.location_requests) == first_loc

    ship = shop.handle_turn(PILOT_TENANT_ID, wa, "me llamo Ana")
    assert "Envío registrado" in ship.reply or "pedido es #" in ship.reply


def test_inbound_delivers_qr_image_and_buttons() -> None:
    from factory_os.agents.turn import ShopRuntime
    from factory_os.domain.models import PILOT_TENANT_ID
    from factory_os.domain.seed import closet_seed_path, extra_seed_paths, load_catalog_json
    from factory_os.domain.store import MemoryCommerceStore
    from factory_os.tools.payments import FakePaymentProvider

    store = MemoryCommerceStore(PILOT_TENANT_ID)
    load_catalog_json(closet_seed_path(), store)
    for path in extra_seed_paths("closet"):
        load_catalog_json(path, store)

    class ImagePay(FakePaymentProvider):
        def create_qr(self, order_id, amount, currency):  # type: ignore[no-untyped-def]
            issued = super().create_qr(order_id, amount, currency)
            # Simulate Baneco qrImage (PNG base64) while keeping provider_ref.
            from factory_os.tools.payments import QrIssue

            return QrIssue(
                provider_ref=issued.provider_ref,
                qr_payload=TINY_PNG_B64,
                expires_at=issued.expires_at,
            )

    channel = FakeChannel()
    shop = ShopRuntime(store, ImagePay(), channel=channel)
    import factory_os.agents.graph as graph_mod

    graph_mod._GRAPH = None
    shop.handle_inbound(PILOT_TENANT_ID, "59170008801", "quiero la blusa pago1")
    assert channel.images, "expected QR image on WhatsApp channel"
    assert channel.buttons, "expected Ya transferí / Reenviar QR buttons"
    ids = [b[0] for b in channel.buttons[0]["buttons"]]
    assert ids == [x[0] for x in payment_qr_buttons()]
    # Text must not dump base64 into the chat body.
    assert TINY_PNG_B64 not in "".join(t for _, t in channel.sent)
    first_images = len(channel.images)
    first_buttons = len(channel.buttons)
    # Casual follow-up must NOT re-fire QR image/buttons.
    shop.handle_inbound(PILOT_TENANT_ID, "59170008801", "buenas tardes")
    assert len(channel.images) == first_images
    assert len(channel.buttons) == first_buttons
    # Explicit resend button text → one more image.
    shop.handle_inbound(PILOT_TENANT_ID, "59170008801", "reenviame el qr")
    assert len(channel.images) == first_images + 1
    assert len(channel.buttons) == first_buttons + 1
