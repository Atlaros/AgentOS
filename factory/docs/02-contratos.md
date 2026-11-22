# 02 — Contratos: empleados, nodos, tools y adaptadores

Qué puede hacer cada empleado, qué es un nodo, con qué tools, bajo qué reglas y detrás de qué adaptadores. El código es la autoridad: `packages/contracts/` y `packages/harness/`. Si este doc y el código difieren, se corrige el doc en el mismo cambio.

## Las seis piezas

```text
BBE        = cómo debe comportarse (invariantes no negociables)
Skill      = qué capacidad aplica y cuándo. No concede permisos
Permission = qué tool tiene permitido usar
Policy     = qué regla de negocio aplica en esta situación
Tool       = la acción concreta, tipada
Workflow   = cómo se coordinan el proceso y el estado
```

El LLM no se autoconcede permisos. Una skill no abre una tool. BBE no sustituye policies ni validación.

El LLM sí tiene autoridad para conducir la conversación comercial. Decide WHAT —qué preguntar, buscar, recomendar, comparar o cerrar— y el runtime decide si la operación propuesta está autorizada. Ver [motor, ADR-003](motor.md#adr-003--el-llm-conduce-la-venta).

## Pipeline de una tool

```text
propuesta del LLM → Permission → BBE (registra ok/deny) → Skill → Policy → Confirmación → handler → validación → trace
```

- **Permission primero** (`ToolRuntime.execute`): un LLM que nombre `payment.create_qr` desde Adri no llega ni a BBE.
- Un DENY en cualquier etapa no corre el handler.
- `confirmation_required` exige confirmación del runtime (el cliente nombró un código o confirmó una variante mostrada), no una inferencia del modelo.

## Empleados

| Empleado | Rol | Canal | Tools | Límite |
| --- | --- | --- | --- | --- |
| Coordinador | orchestrator | — | ninguna (no debe tenerlas) | solo elige quién atiende |
| Adri | sales | WhatsApp | `catalog.search`, `send_product_image`, `cart.add`, `order.create` | no cobra, no marca pagado, no edita catálogo |
| Cobros | collections | WhatsApp | `payment.create_qr`, `payment.status` | no toca catálogo; el pago lo confirma el adaptador |
| Operaciones | ops | WhatsApp | `customer.update_profile`, `delivery.create` | no envía sin pago confirmado |
| Postventa | postventa | WhatsApp | `catalog.search` | sin WRITE de garantía ni devolución |
| Inventario | inventory | interno | `catalog.search`, `inventory.adjust` | staff |
| Catálogo | catalog_admin | interno | `catalog.search`, `catalog.upsert`, `catalog.disable` | staff; nunca atiende WhatsApp de cliente |
| Contabilidad | accounting | interno | `cash.record`, `cash.ledger` | consolida el libro; el QR lo confirma Cobros; la compra y la CxP nacen en Proveedores |
| Analista | analyst | interno | `metrics.summary` | READ: narra sobre `build_analytics_summary`; si el modelo falla o inventa cifras, va el resumen tipado |
| Proveedores | suppliers | interno | `catalog.search`, `stock.receive`, `supplier.alert` | enviar una OC exige preview y `confirm: true` de supervisor; el stock entra al recibir |

Todos corren sobre el mismo harness (`ShopRuntime`). Adri no es un chatbot aparte.

Un empleado se configura en tres capas: invariantes (código), permisos y autonomía (por negocio), estilo (ficha del negocio). El dueño puede endurecer la autonomía; no puede bajarla del piso de la plantilla.

### Roster por tenant ([ADR-026](adr/ADR-026-roster-empleados-por-tenant.md))

- El **catálogo** (`EMPLOYEE_REGISTRY`) sigue en código.
- El **roster** (`tenant_employees`) es por negocio: `display_name`, `style`, `enabled`, clones.
- `sales` y `collections` no se apagan. El Coordinador no entra al roster.
- Un clone hereda solo el `base_role` del catálogo: mismos permisos/BBE/skills (nunca más). Skills no conceden permisos. No hay tools a medida.
- WHO solo elige roles enabled del roster del tenant.

## Autonomía

Cada acción sensible tiene un nivel por negocio, de menor a mayor: `never`, `recommend`, `approval`, `within_limits`. La plantilla fija el piso (`autonomy.py`, `grants_for_tenant`). Con `never` o `recommend` la acción no corre; con `approval` corre solo con confirmación humana.

| Regla | Contrato |
| --- | --- |
| Confirmar un pago (`confirm_payment`) | siempre `never`: solo el adaptador del banco o la caja |
| Asientos (`post_journal`), ajuste de stock (`adjust_stock`) | piso `approval` |
| Aflojar por debajo del piso | falla |
| Dónde se ve | consola del operador y `/owner` |

## Nodos

Un nodo es una pieza de negocio del lienzo. No es un nodo de LangGraph. Fuente: `packages/contracts/.../nodes.py` (`NODE_CATALOG`). El dominio (`flow_canvas`) solo lo consume.

| Campo | Contrato |
| --- | --- |
| `kind` | uno del catálogo; un `kind` desconocido no entra al lienzo |
| Puertos | `pedido`, `pago_confirmado`, `aviso`, `aprobacion`, `equipo`; dos módulos se unen solo por el mismo puerto (`connect_modules`, `compatible_targets`). Un empleado del roster se asigna a un módulo con `equipo` ([ADR-027](adr/ADR-027-empleados-en-lienzo.md)) |
| Módulo | el módulo del motor que lo ejecuta |
| Piso de autonomía | `autonomy_action` del nodo (p. ej. Cobros → `confirm_payment`); el lienzo no lo baja |
| Rubros | `industries` (`cafe`, `ropa`); la paleta sale de `palette_kinds` |

Barandas:

- El camino canal → pedido → Cobros está bloqueado (`LOCKED_EDGES`): no se borra ni se puentea. Los `core` están siempre en el mapa.
- `pago_confirmado` solo sale de Cobros (`pago_confirmado_sources`). Ninguna regla lo inventa.
- Una regla (Cuando → Si → Entonces) se guarda en borrador y se publica solo si sus puertos son compatibles. Cada publicación es una versión a la que se puede volver (`catalog_rule_versions`).
- Nodos libres, SQL y APIs arbitrarias no existen.

### Agregar un nodo

1. Que sea un hecho que el catálogo no expresa todavía.
2. Contrato: puertos, módulo, piso de autonomía, rubros.
3. Test: una conexión inválida no se publica; el nodo no confirma pagos.
4. Eval del rubro que lo usa en verde.
5. Se construye una vez para toda la plataforma.

## Módulos del panel

Detalle de cada uno en [motor](motor.md). Contratos que el resto del sistema puede asumir:

| Módulo | Contrato |
| --- | --- |
| Caja | turno con arqueo; ticket `TK-…` y pedido `origin=counter`; el QR emitido desde Caja no suma al efectivo; anular, reabrir y descontar exigen PIN de supervisor; adjuntos con bytes en disco, no en la base |
| Libro (`/ledger`) | solo lectura salvo ajuste manual; consolida pago confirmado, caja y compra; un void no suma |
| Partida doble | asientos derivados; void → asiento `reverse`; cierre de período rechaza asientos nuevos (`period_closed`); export con supervisor; gerencial, no oficial |
| Proveedores | OC `draft` → `sent` → `partially_received` → `received`; el asiento y el stock nacen al recibir; efectivo sale por Caja, transferencia contra CxP `2100` |
| Analítica | ventana de 7 días contra los 7 anteriores; venta = pago `CONFIRMED` o caja registrada; alertas por tipo; staff no la ve |
| Reportes | Descargas y Seguimiento; un aviso al cliente exige preview y `confirm: true` y no confirma un pago |

APIs humanas de Proveedores: `GET/POST /api/suppliers`, `PATCH /api/suppliers/{id}`, `GET /api/suppliers/replenishment`, `POST/GET /api/purchase-orders`, `PATCH /api/purchase-orders/{id}`, `POST /api/purchase-orders/{id}/receive`, `POST /api/purchase-orders/{id}/payments`, `POST /api/stock/receive`.

APIs de Analítica y Reportes: `GET /api/metrics?period=`, `GET/PATCH /api/analytics/thresholds`, `POST /api/analytics/ask`, `POST /api/analytics/digest/run`, `GET /api/alerts`, `GET /api/reports/downloads/history`, `GET /api/reports/package`, `GET /api/reports/accounting-package`, `POST /api/reminders/preview`, `POST /api/reminders/send`.

## Skills

Campos: `purpose`, `when_to_use`, `forbidden`, `related_tools`, `required_context`, `action_types`, `handoff_condition`. `required_context` se exige solo en WRITE; un READ no se bloquea por una carpeta incompleta. Fuente: `packages/contracts/.../skills.py`.

| Empleado | Skill | Tools | Contexto requerido | Handoff |
| --- | --- | --- | --- | --- |
| Adri | `customer_assistance` | `catalog.search`, `send_product_image` | — | escala a humano |
| Adri | `sales_discovery` | `catalog.search` | — | — |
| Adri | `product_recommendation` | `catalog.search`, `send_product_image` | — | — |
| Adri | `objection_handling` | `catalog.search` | — | — |
| Adri | `sales_closing` | `cart.add`, `order.create` | variante considerada o carrito | pedido creado → Cobros |
| Cobros | `payment_initiation` | `payment.create_qr` | variante o carrito | una reserva y un QR por el total; el pedido nace cuando el banco confirma |
| Cobros | `payment_verification` | `payment.status` | `order_id` | pago confirmado por el banco → la variante queda vendida y pasa a Operaciones |
| Operaciones | `customer_delivery_data` | `customer.update_profile` | — | — |
| Operaciones | `delivery_management` | `delivery.create` | `order_id` | envío registrado |
| Operaciones | `fulfillment` | `delivery.create`, `customer.update_profile` | — | — |
| Postventa | `post_sale_support` | `catalog.search` | — | — |
| Postventa | `incident_handling` | `catalog.search` | — | política → humano |
| Postventa | `order_followup` | — | `order_id` | — |
| Postventa | `sales_handoff` | `catalog.search` | — | recompra → Adri |

El staff tiene sus skills en el mismo archivo (`stock_inquiry`, `inventory_adjustment`, `product_create`, `cash_in`, `business_metrics`, `stock_receive`, …).

Hueco: no hay skill `payment_communication` (explicar el QR o un fallo del proveedor sin inventar plazos). Hoy lo cubre el draft de Cobros.

## BBE: invariantes

Registro en `ToolRuntime.bbe_audit`: `{decision, role, employee, tenant_id, tool, channel, reason}`. No guarda el payload del cliente.

| Invariante | `rule_id` |
| --- | --- |
| El texto del cliente no confirma un pago | `customer_text_does_not_confirm_payment` |
| No inventar precio, stock, SKU ni promo | `no_invent_price_stock_sku_promo` (+ draft con grounding) |
| No usar tools de pago fuera de Cobros | `no_payment_tools` |
| No crear envíos fuera de Operaciones | `no_delivery_tools` |
| No enviar sin pago confirmado | `no_ship_without_payment` (+ policy) |
| No escribir el catálogo maestro | `no_catalog_master_write` |
| No escribir ventas fuera de Adri | `no_sales_write` |
| No tocar caja ni inventario fuera de rol | `no_cash_write`, `no_inventory_write` |
| No inventar garantía ni devolución | `no_invent_warranty_return_policy` |
| Staff no atiende WhatsApp de cliente | `staff_channel_only`, `no_customer_whatsapp` |

Sin `rule_id` propio todavía: no continuar el turno con `needs_human` activo, y no inventar urgencia ni escasez.

## Policies

Las evalúa `PolicyEngine` antes del handler.

| Policy | Tool | Estado |
| --- | --- | --- |
| Variante existente en el catálogo estructurado | `cart.add`, `order.create`, `inventory.adjust`, `catalog.disable`, `stock.receive` | existe |
| Revalidar stock y que la variante esté habilitada | `cart.add`, `order.create` | existe |
| Pedido existente para emitir QR | `payment.create_qr` | existe |
| Pago confirmado, nombre y dirección para enviar | `delivery.create` | existe |
| El stock no queda negativo | `inventory.adjust` | existe |
| Dirección e importe válidos | `cash.record` | existe |
| Un solo QR activo por pedido pendiente | `payment.create_qr` | objetivo |
| Ningún descuento por chat sin policy explícita | — | el agente no improvisa descuentos en objeciones |

## Guardrails y Validation

| Capa | Cuida | Ejemplos |
| --- | --- | --- |
| Guardrails | lo que se **dice** | no inventar redes ni ubicación vacías de la ficha; no dar consejo legal o médico |
| Validation | lo que se **cree** cierto | el draft que inventa precio, SKU o pago se descarta (`grounded_draft`); el webhook de pago se valida por firma y `event_id` antes de confirmar |

## Tools

Todas en `packages/tools/.../registry.py`.

| Tool | Quién | READ/WRITE | Confirmación | Nota |
| --- | --- | --- | --- | --- |
| `catalog.search` | Adri, Postventa, staff | READ | — | precio y stock de la fila SQL |
| `send_product_image` | Adri | READ | — | solo `product_sku`; imagen principal desde el store; niega URL libre y agotado |
| `cart.add` | Adri | WRITE | — | variante real con stock |
| `order.create` | Adri | WRITE | sí | precio de la variante, no del texto |
| `payment.create_qr` | Cobros | WRITE | — | vía adaptador |
| `payment.status` | Cobros | READ | — | el adaptador decide |
| `customer.update_profile` | Operaciones | WRITE | — | nombre y dirección explícitos |
| `delivery.create` | Operaciones | WRITE | — | falla sin pago confirmado |
| `inventory.adjust`, `catalog.upsert`, `catalog.disable`, `cash.record`, `stock.receive` | staff | WRITE | sí | canal interno |
| `cash.ledger`, `metrics.summary`, `supplier.alert` | staff | READ | — | |

### ToolSpec objetivo

`name`, `description`, `input_schema`, `output_schema`, `permission`, `read_only`, `confirmation_required`, `idempotency`, `timeout`, `audit_policy`. Hoy el dataclass tiene `name`, `permission`, `read_only`, `confirmation_required` y `description`.

Plantilla con `payment.create_qr`:

| Campo | Valor |
| --- | --- |
| `permission` | Cobros |
| `read_only` | no |
| `confirmation_required` | no: crear el QR no compromete; confirmar el pago no es una tool del LLM |
| `idempotency` | por `order_id`: un segundo `create_qr` sobre el mismo pedido pendiente devuelve el QR existente |
| `timeout` | SLA del proveedor; el fake responde al instante |
| `audit_policy` | `order_id`, `provider_reference`, monto; no el payload crudo |

## Adaptadores

Regla común: interfaz con métodos fijos; el fake y el real implementan lo mismo; la selección es por variable de entorno + factory, nunca por un `import` del real en el handler. El fake es determinista, sin red ni credenciales. Ningún adaptador es alcanzable por el LLM.

### Pago

```text
create_qr(order_id, amount, currency, tenant_id) -> { qr_payload, provider_reference, expires_at }
status(provider_reference) -> { state: pending|confirmed|expired|failed, confirmed_at }
parse_webhook(raw_payload, headers) -> { provider_reference, state, event_id }   # valida firma
```

- El pago se marca confirmado **solo** cuando el webhook o `status` traen `confirmed`. El texto del cliente ("ya pagué") consulta el estado, no confirma.
- Cada `event_id` se procesa una vez; Baneco puede reintentar.
- Si el proveedor falla: 2–3 reintentos con backoff; después Cobros avisa que hubo un problema con el QR y ofrece reintentar. No inventa el estado.
- Hoy: `FakePaymentProvider` y `BanecoPaymentProvider`. Live con `QR_PROVIDER=baneco` + `ENABLE_LIVE_PAYMENTS` + `BANECO_*`. Webhooks `/webhooks/payments/{fake|baneco}` con idempotencia por `event_id`; en Baneco manda `statusQR`. `fake-confirm` solo si provider=fake.

### Canal (WhatsApp)

```text
send_text(to, text) -> message_id
send_image(to, content|link, caption) -> None
send_document(to, content, caption) -> None
parse_inbound(raw_payload) -> InboundMessage{ wa_number, text, message_id?, media_id?, media_kind?, mime?, filename?, caption? }
```

- El tenant sale de mapear el `phone_number_id` del webhook contra `tenants`, nunca del cuerpo del mensaje.
- El webhook exige `X-Hub-Signature-256`. `FakeChannel` guarda lo enviado para los tests.
- Outbox [objetivo]: el turno escribe `outbox` y un worker entrega con reintento.
- Hoy: `Channel` tiene `send_text`, `send_template`, `send_image`, `send_document`, typing, botones y pedido de ubicación; los medios de entrada se descargan en background después del claim del `wamid`; `WHATSAPP_OUTBOUND_PROVIDER=meta|fake`.
- Mesa humana: si el agente no encuentra el producto o el cliente pide una persona, el runtime marca `needs_human`, avisa al dueño una vez (`OWNER_WA_NUMBERS`) y el humano toma el chat en `/inbox`.

### Model Gateway

| Operación | Rol |
| --- | --- |
| `propose` | `SalesDecision` tipado: `{action, skill, understanding, preference_patch, tool_call, response_goal}`. No es autorización |
| `draft` | redacta sobre hechos ya leídos; si inventa precio, stock, SKU, promo o pago, se descarta y va el texto fijo |

- Cadena: Gemini (`GOOGLE_API_KEY`) → OpenRouter → Groq. `MODEL_PROVIDER=fake` en pytest.
- Si todos fallan: heurística y textos fijos. El flujo de venta no se cae.
- Con un proveedor disponible y una propuesta válida, el LLM conduce el flujo; las heurísticas no la reemplazan.
- El runtime valida `preference_patch`: solo datos explícitos se vuelven memoria durable.
- El turno puede ejecutar un loop acotado LLM → READ tool → LLM para consultar hechos antes de recomendar.
- `order.create` solo corre si el cliente nombró un código o confirmó una variante ya mostrada ("confirmo", "me llevo ese").

### Otros puertos

| Puerto | Real | Fake |
| --- | --- | --- |
| `MediaEnricher` (transcribir, resumir) | no hay | sí |
| Factura | puerto; no escribe `payments` | sí |

## MCP vs tools internas

| Caso | Tecnología |
| --- | --- |
| Catálogo, carrito, pedido, cliente, pago | tools tipadas Python + service layer |
| ERP, CRM, calendario, SaaS externos | MCP cuando aporte interoperabilidad |
| Banco | adaptador encapsulado; MCP opcional |

Tools internas y MCP externos van detrás del mismo registry y del mismo pipeline de permisos.
