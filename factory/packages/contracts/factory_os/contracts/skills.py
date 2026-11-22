from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Skill:
    """Capability and when to use it. Never a permission grant."""

    name: str
    purpose: str
    when_to_use: str
    forbidden: tuple[str, ...]
    completion: str
    related_tools: tuple[str, ...] = ()
    required_context: tuple[str, ...] = ()
    action_types: tuple[str, ...] = ()
    handoff_condition: str | None = None

    @property
    def preconditions(self) -> tuple[str, ...]:
        return self.required_context


def _skill(
    name: str,
    purpose: str,
    when_to_use: str,
    forbidden: tuple[str, ...],
    completion: str,
    related_tools: tuple[str, ...] = (),
    *,
    required_context: tuple[str, ...] = (),
    action_types: tuple[str, ...] = (),
    handoff_condition: str | None = None,
) -> Skill:
    return Skill(
        name,
        purpose,
        when_to_use,
        forbidden,
        completion,
        related_tools,
        required_context,
        action_types,
        handoff_condition,
    )


ADRI_SKILLS: tuple[Skill, ...] = (
    _skill(
        "customer_assistance",
        "Atender consultas y problemas sin vender a la fuerza.",
        "Saludo, pregunta de ficha, o un reclamo junto a una venta nueva.",
        ("payment.create_qr", "delivery.create"),
        "El cliente tiene una respuesta de catálogo o un camino a humano.",
        ("catalog.search", "payment.status", "send_product_image"),
        action_types=("answer", "ask_discovery_question", "escalate"),
    ),
    _skill(
        "sales_discovery",
        "Averiguar la necesidad con la mínima pregunta útil.",
        "Hay intención de compra pero falta un dato que cambia la búsqueda.",
        ("order.create", "payment.create_qr"),
        "Hay bastante para buscar en el catálogo.",
        ("catalog.search",),
        action_types=("ask_discovery_question",),
    ),
    _skill(
        "product_recommendation",
        "Mostrar candidatos reales con precio y stock del archivo.",
        "La búsqueda devolvió hits.",
        ("inventar SKU", "payment.create_qr"),
        "El cliente ve opciones reales o se escala.",
        ("catalog.search", "send_product_image"),
        action_types=("search_catalog", "recommend", "compare"),
    ),
    _skill(
        "objection_handling",
        "Tratar precio u otras objeciones sin inventar beneficios.",
        "El cliente dice que está caro o duda con hechos del catálogo.",
        ("inventar descuento", "payment.create_qr"),
        "Hay alternativa real, se pide confirmación, o se escala.",
        ("catalog.search",),
        action_types=("handle_objection",),
    ),
    _skill(
        "sales_closing",
        "Sumar al carrito o pasar a Cobros cuando la intención es pagar.",
        "Hay una prenda considerada o un carrito.",
        ("payment.create_qr", "marcar pagado"),
        "Carrito actualizado, o pase a Cobros para un QR del total.",
        ("cart.add", "cart.remove", "order.create", "catalog.search"),
        required_context=("considered_variant_or_cart",),
        action_types=("request_confirmation", "create_order", "add_to_cart", "handoff"),
        handoff_condition="order_created → Cobros",
    ),
)

COBROS_SKILLS: tuple[Skill, ...] = (
    _skill(
        "payment_initiation",
        "Emitir un QR por el total del carrito. La reserva nace con el QR; el pedido, cuando el banco confirma.",
        "Hay carrito o una prenda considerada y todavía no hay QR vigente.",
        ("catalog.upsert", "order.create"),
        "El cliente tiene un QR del adaptador.",
        ("payment.create_qr",),
        required_context=("variant_sku",),
        action_types=("handoff",),
        handoff_condition="qr_issued → stay Cobros",
    ),
    _skill(
        "payment_verification",
        "Leer el estado de pago del adaptador, nunca del chat.",
        "El cliente pregunta si pagó o hay QR emitido.",
        ("marcar pagado por texto", "catalog.upsert"),
        "Estado real pending o confirmed.",
        ("payment.status",),
        required_context=("provider_ref",),
        action_types=("handoff",),
        handoff_condition="payment_confirmed → Ops",
    ),
)

OPS_SKILLS: tuple[Skill, ...] = (
    _skill(
        "customer_delivery_data",
        "Pedir y guardar nombre y dirección de envío.",
        "El pago está confirmado y faltan datos.",
        ("payment.create_qr", "order.create"),
        "Perfil con nombre y dirección.",
        ("customer.update_profile",),
        action_types=("answer",),
    ),
    _skill(
        "delivery_management",
        "Registrar el envío cuando el pago está confirmado.",
        "Hay pedido pagado y datos de envío.",
        ("payment.create_qr", "enviar sin pago"),
        "Delivery persistido.",
        ("delivery.create",),
        required_context=("order_id",),
        action_types=("handoff",),
        handoff_condition="delivery_registered",
    ),
    _skill(
        "fulfillment",
        "Coordinar la entrega, no el cobro.",
        "Handoff de Cobros con pago confirmado.",
        ("payment.create_qr", "catalog.upsert"),
        "Envío registrado o datos pedidos.",
        ("delivery.create", "customer.update_profile"),
        action_types=("answer", "handoff"),
    ),
)

POSTVENTA_SKILLS: tuple[Skill, ...] = (
    _skill(
        "post_sale_support",
        "Atender un pedido ya hecho sin inventar políticas.",
        "El cliente habla de un pedido entregado o en curso.",
        ("order.create", "payment.create_qr", "inventar garantía"),
        "Incidencia anotada o handoff.",
        ("catalog.search",),
        action_types=("answer", "escalate"),
    ),
    _skill(
        "incident_handling",
        "Registrar reclamo (roto, no llegó) sin compensar de oficio.",
        "Producto dañado, faltante o reclamo.",
        ("inventar devolución", "order.create"),
        "Hecho registrado; humano si hace falta política.",
        ("catalog.search",),
        action_types=("escalate",),
        handoff_condition="human_policy",
    ),
    _skill(
        "order_followup",
        "Decir el estado conocido del pedido, no adivinar logística.",
        "El cliente pregunta dónde está el pedido.",
        ("delivery.create", "payment.create_qr"),
        "Estado de working state o escala.",
        (),
        required_context=("order_id",),
        action_types=("answer",),
    ),
    _skill(
        "sales_handoff",
        "Pasar a Adri una recompra, no vender desde Postventa.",
        "Quiere el mismo producto u otro.",
        ("order.create", "cart.add"),
        "Handoff a sales con la carpeta.",
        ("catalog.search",),
        action_types=("handoff",),
        handoff_condition="repurchase → Sales",
    ),
)

INVENTORY_SKILLS: tuple[Skill, ...] = (
    _skill(
        "stock_inquiry",
        "Informar stock y variante desde el archivo.",
        "Consulta interna de disponibilidad.",
        ("order.create", "payment.create_qr"),
        "Stock real del store.",
        ("catalog.search",),
    ),
    _skill(
        "availability_check",
        "Confirmar si una variante se puede vender.",
        "Hay un SKU o talle concreto.",
        ("inventar stock",),
        "Sí/no con cantidad del store.",
        ("catalog.search",),
    ),
    _skill(
        "low_stock",
        "Listar variantes bajo umbral.",
        "Alerta o recuento interno.",
        ("order.create",),
        "Lista real, no inventada.",
        ("catalog.search",),
    ),
    _skill(
        "inventory_adjustment",
        "Ajustar cantidad con tool + permiso.",
        "Operación interna autorizada de ajuste.",
        ("catalog.upsert", "order.create"),
        "Nuevo stock persistido.",
        ("inventory.adjust",),
        required_context=("variant_sku",),
    ),
)

CATALOG_SKILLS: tuple[Skill, ...] = (
    _skill(
        "catalog_maintenance",
        "Leer fichas para mantenimiento, no para WhatsApp de cliente.",
        "Trabajo interno de catálogo.",
        ("atender WhatsApp cliente", "payment.create_qr"),
        "Ficha leída.",
        ("catalog.search",),
    ),
    _skill(
        "product_create",
        "Alta de producto/variante por tool.",
        "Alta interna con datos estructurados.",
        ("order.create",),
        "Variante en el store.",
        ("catalog.upsert",),
    ),
    _skill(
        "product_update",
        "Edición de ficha por tool.",
        "Cambio de nombre, precio o atributos.",
        ("order.create",),
        "Ficha actualizada en el store.",
        ("catalog.upsert",),
    ),
    _skill(
        "product_disable",
        "Baja lógica de una variante.",
        "Sacar una ficha de venta.",
        ("order.create",),
        "Variante marcada disabled.",
        ("catalog.disable",),
    ),
)

BBE_SALES: tuple[str, ...] = (
    "no_invent_price_stock_sku_promo",
    "customer_text_does_not_confirm_payment",
    "no_catalog_master_write",
    "skill_does_not_grant_permission",
    "no_payment_write",
    "no_delivery_tools",
    "no_inventory_write",
    "no_cash_write",
)

BBE_COBROS: tuple[str, ...] = (
    "customer_text_does_not_confirm_payment",
    "no_catalog_master_write",
    "no_sales_write",
    "no_delivery_tools",
    "no_cash_write",
)

BBE_OPS: tuple[str, ...] = (
    "no_ship_without_payment",
    "no_payment_tools",
    "no_catalog_master_write",
    "no_sales_write",
    "no_cash_write",
)

BBE_POSTVENTA: tuple[str, ...] = (
    "no_invent_warranty_return_policy",
    "no_sales_write",
    "no_payment_tools",
    "no_catalog_master_write",
    "no_cash_write",
)

BBE_INVENTORY: tuple[str, ...] = (
    "no_invent_stock",
    "no_sales_write",
    "no_payment_tools",
    "no_catalog_master_write",
    "staff_channel_only",
    "no_cash_write",
)

BBE_CATALOG: tuple[str, ...] = (
    "no_customer_whatsapp",
    "no_sales_write",
    "no_payment_tools",
    "staff_channel_only",
    "no_cash_write",
)

ACCOUNTING_SKILLS: tuple[Skill, ...] = (
    _skill(
        "cash_in",
        "Registrar entrada de efectivo u otro medio que no es QR de Cobros.",
        "Hay dinero que entra a caja (mostrador, depósito).",
        ("payment.create_qr", "marcar pagado", "order.create"),
        "Movimiento de caja persistido.",
        ("cash.record",),
    ),
    _skill(
        "cash_out",
        "Registrar salida de caja (gasto, vuelto, retiro).",
        "Hay un egreso de caja.",
        ("payment.create_qr", "order.create"),
        "Egreso persistido. El saldo no se inventa.",
        ("cash.record",),
    ),
    _skill(
        "cash_ledger",
        "Leer el flujo de caja (entradas menos salidas).",
        "El dueño pregunta arqueo o libro de caja.",
        ("payment.create_qr", "inventar saldo de banco"),
        "Libro del store, no del chat.",
        ("cash.ledger",),
    ),
)

ANALYST_SKILLS: tuple[Skill, ...] = (
    _skill(
        "business_metrics",
        "Informar métricas de pedidos, pagos confirmados y stock bajo.",
        "Consulta interna de desempeño.",
        ("order.create", "payment.create_qr", "cash.record", "inventory.adjust"),
        "Números del Postgres/store.",
        ("metrics.summary",),
    ),
)

SUPPLIER_SKILLS: tuple[Skill, ...] = (
    _skill(
        "stock_receive",
        "Ingresar mercadería de proveedor al stock estructurado.",
        "Llegó un bulto con variante y cantidad reales.",
        ("payment.create_qr", "order.create", "inventar stock"),
        "Stock aumentado en el store.",
        ("stock.receive",),
        required_context=("variant_sku",),
    ),
    _skill(
        "low_stock_alert",
        "Avisar falta de stock. Aún no contacta al proveedor.",
        "Consulta de reposición o stock bajo.",
        ("inventar un WhatsApp al proveedor", "order.create"),
        "Lista real de bajo stock; contacto a proveedor queda pendiente.",
        ("supplier.alert", "catalog.search"),
    ),
)

BBE_ACCOUNTING: tuple[str, ...] = (
    "no_payment_tools",
    "no_sales_write",
    "no_catalog_master_write",
    "no_inventory_write",
    "staff_channel_only",
    "caja_is_not_cobros",
)

BBE_ANALYST: tuple[str, ...] = (
    "no_payment_tools",
    "no_sales_write",
    "no_catalog_master_write",
    "no_inventory_write",
    "no_cash_write",
    "staff_channel_only",
)

BBE_SUPPLIERS: tuple[str, ...] = (
    "no_payment_tools",
    "no_sales_write",
    "no_catalog_master_write",
    "no_cash_write",
    "staff_channel_only",
    "no_invent_stock",
)
