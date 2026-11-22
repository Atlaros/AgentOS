from factory_os.tools.inbound_buffer import MemoryInboundBuffer


def test_memory_buffer_coalesces_with_zero_debounce() -> None:
    buf = MemoryInboundBuffer()
    first = buf.coalesce("5917001", "hola", debounce_s=0)
    assert first == "hola"
    a = buf.coalesce("5917002", "hola", debounce_s=0)
    # With debounce 0 each call owns the flush of what was pushed in that call only
    # after setting token — second push on same wa with 0 debounce still works sequentially.
    assert a == "hola"
    joined = buf.coalesce("5917003", "uno", debounce_s=0)
    assert joined == "uno"


def test_same_wa_number_does_not_mix_tenants() -> None:
    buf = MemoryInboundBuffer()
    a = buf.coalesce("5917001", "cafe", debounce_s=0, tenant_id="tenant-a")
    b = buf.coalesce("5917001", "ropa", debounce_s=0, tenant_id="tenant-b")
    assert a == "cafe"
    assert b == "ropa"


def test_buffer_without_tenant_keeps_phone_key() -> None:
    buf = MemoryInboundBuffer()
    first = buf.coalesce("5917001", "uno", debounce_s=0)
    second = buf.coalesce("5917001", "dos", debounce_s=0)
    assert first == "uno"
    assert second == "dos"
