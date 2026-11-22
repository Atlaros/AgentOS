# Motor

El motor es la base sobre la que se construye Factory: los módulos que hacen andar un negocio. Ya opera un negocio real, la cafetería. Este documento dice qué da cada módulo hoy y qué invariantes respeta. No es un plan: lo que el motor no tiene está marcado como **No está**.

Las secciones conservan el número de ADR con que se decidió cada pieza. El código cita esos números (`ADR-009`, `ADR-015`) y apuntan acá. El estado de Factory está en [00](00-vision-y-estado.md).

## Regla central

El LLM conversa, propone y redacta. El runtime autoriza, ejecuta y verifica.

- El tenant sale de la identidad del runtime, nunca del texto del cliente ni del modelo. RLS en Postgres y mínimo privilegio.
- READ amplio y controlado. WRITE por tool tipada, con permiso, policy, validación e idempotencia.
- Precio, stock, pago y pedido salen de Postgres, no del modelo.
- El texto del cliente no confirma un pago. Solo el adaptador del banco o la caja. El empleado lee ese estado y sigue la conversación.
- Las heurísticas y los textos fijos son respaldo cuando el modelo falla, no un guion paralelo.
- Skills no conceden permisos. BBE no sustituye policies ni validación.
- El LLM no recibe `DATABASE_URL`, service role, secretos ni SQL.

## ADR-001 · Model Gateway y contratos

- Cadena Gemini → OpenRouter → Groq, con `propose` (decisión tipada) y `draft` (redacción sobre hechos). `MODEL_PROVIDER=fake` en pytest.
- Pipeline de una tool: Permission → BBE → Skill → Policy → Confirmación → handler → validación → trace.
- El draft que inventa precio, SKU, stock, promo o pago se descarta (`grounded_draft`).
- `order.create` exige que el cliente nombre un código o confirme una variante ya mostrada.

## ADR-002 · Primer negocio

- El motor nació con Authentic Closet (ropa) por WhatsApp: venta, QR, envío. Ese catálogo queda como plantilla de ropa y como fixture de pytest (`catalog_closet.json` + `pago1`–`pago4`).

## ADR-003 · El LLM conduce la venta

- El LLM aborda, pregunta, descubre, busca, recomienda, maneja objeciones y cierra. El runtime solo tiene autoridad operacional.
- No hay listas de palabras que disparen WHO, WRITE, READ ni FAQ en el camino vivo.

## ADR-004 · Agentes y grafo corto

- El orquestador propone WHO (`propose_who` + `authorize_who`). Cada empleado propone WHAT.
- LangGraph corre un grafo corto con `thread_id = conversation_id`. El paso durable vive en `WorkingState.graph_node` (Postgres). El checkpointer de LangGraph está en memoria.
- Una escritura negada no corta el turno: el empleado recibe el hecho y sigue.
- El handoff pasa una carpeta con hechos (`order_id`, `payment_state`, `need`, `pending`, `reason`). El pago se relee siempre de `payments`.
- Grafo de turno por módulos del tenant (`turn_modules.py` / `graph.py`): sin `cobros` no hay nodo Cobros. Vacío = piloto completo.
- **No está:** grafo desde el mapa publicado del lienzo; checkpoint de LangGraph en Postgres; outbox de salida; worker de cola.

## ADR-005 · Panel y sistema visual

- Shell de `apps/web`: sidebar, navegación móvil, tema claro y oscuro, tokens.
- Un empleado se configura en tres capas: invariantes (código), permisos y autonomía, estilo (ficha).

## ADR-006 · Base operativa

- Conocimiento editable, ficha de cliente, reportes con alertas y recordatorios, personas con rol y auditoría, contabilidad con puerto de factura.
- Una factura emitida no escribe `payments`. El staff no atiende WhatsApp de cliente.
- **No está:** factura legal dentro del runtime; marketing, Instagram, campañas.

## ADR-007 · Conocimiento del negocio

- `/knowledge` edita identidad y voz. Las FAQs se guardan de a una. Un documento propone la estructura y solo escribe cuando el dueño confirma (`shop_knowledge`).
- Precio, stock y pago no salen de esta ficha.

## ADR-008 · Prompts y RAG de la ficha

- `SalesDecision` con `response_goal` cerrado. El RAG de la ficha suma hasta 2 fragmentos (FAQ, política, identidad) a la respuesta.
- El RAG no toca precio, stock ni pago.

## ADR-009 · Caja

- Turno: abrir con saldo, totales, cerrar con contado y diferencia, reabrir solo supervisor u owner.
- Mostrador: grilla táctil (`GET /api/cash/grid`), ticket `TK-…` y pedido `origin=counter`. Vender N resta N; la variante se apaga en cero. Mesa abierta aparta stock.
- Combos sin stock propio, modificadores con diferencia de precio, «Más vendidos», descuento por cobro con PIN de supervisor y tope en el total.
- El QR Baneco emitido desde Caja no suma al efectivo del arqueo.
- Anular, reabrir, cerrar, descontar y fijar precio de combo exigen PIN de supervisor.

## ADR-010 · Libro operativo

- `/ledger` consolida pago confirmado, caja y compra. Un void queda `status=voided` y no suma. Período, filtros, desglose y export.
- Solo lectura ordinaria. No duplica caja y Baneco.

## ADR-011 · Partida doble gerencial

- Asientos derivados: diario, mayor, comprobación, resultado con COGS (promedio ponderado), balance, conciliación liviana, cierre de período, CxP en compras a crédito, ajustes manuales.
- Un void genera un asiento `reverse`. Export xlsx y PDF con `require_supervisor`.
- Es gerencial, no libros oficiales.
- **No está:** IVA/IT automático; pipeline de CxC.

## ADR-012 · Proveedores

- Directorio, reposición agrupada por proveedor, órdenes `draft` → `sent` → recibida, recibir parcial o total, pagos (efectivo por Caja, transferencia contra CxP).
- El asiento y el stock nacen al recibir. Enviar la OC por WhatsApp exige preview y confirmación.
- **No está:** envío sin aprobación; IVA de compra; sugerido óptimo.

## ADR-013 · Analítica y Analista

- Tablero de 7 días contra los 7 anteriores, alertas tipadas, umbrales por negocio.
- El Analista narra sobre los mismos números y no escribe. Digest diario por WhatsApp al dueño, opt-in.
- Una venta cuenta solo con pago `CONFIRMED` o caja registrada.
- Digest al dueño: `POST /api/analytics/digest/run` y, si hay regla publicada `owner_digest` + `has_alerts` + `notify_owner`, también vía `POST /api/rules/run`. El mismo endpoint corre `qr_pending`, `stock_low`, `payment_overdue` y `customer_inactive` (nunca confirma pagos).
- **No está:** worker propio del digest (lo dispara un cron HTTP externo).

## ADR-014 · Reportes

- Descargas (operación y contabilidad, paquetes mensuales) y Seguimiento (aviso por WhatsApp al cliente con preview y confirmación).
- Un recordatorio no confirma un pago.

## ADR-015 · Medios y archivos

- `media_assets` y `product_media`, miniaturas, `GET /api/media/{id}` con autenticación.
- Medios del chat de WhatsApp, envío manual con takeover, `send_product_image` (solo por SKU), adjuntos de pedido y OC (`entity_media`), transcripción y resumen para el staff.
- Un comprobante o un resumen no confirman un pago.
- **No está:** STT y LLM de producción para medios (puerto `MediaEnricher` con Fake).

## ADR-016 · Cafetería

- Negocio vivo: cafetería, 54 productos en BOB (`catalog_cafe.json` + `shop_cafe.json`), venta por cantidad, modificadores en Caja.
- Plantilla de cafetería para Factory. Closet sigue en pytest.
- **No está:** recetas, insumos, merma; delivery de terceros; segundo teléfono.

## Empleados

| Empleado | Canal | Tools | Límite |
| --- | --- | --- | --- |
| Orquestador | — | ninguna | solo elige quién atiende |
| Adri (ventas) | WhatsApp | `catalog.search`, `send_product_image`, `cart.add`, `order.create` | no cobra ni edita catálogo |
| Cobros | WhatsApp | `payment.create_qr`, `payment.status` | no toca catálogo |
| Operaciones | WhatsApp | `customer.update_profile`, `delivery.create` | no envía sin pago confirmado |
| Postventa | WhatsApp | `catalog.search` | sin WRITE de garantía ni devolución |
| Inventario, Catálogo, Contabilidad, Analista, Proveedores | interno | según rol | no atienden WhatsApp de cliente |

Todos corren sobre el mismo runtime (`ShopRuntime`). Contratos completos en [02](02-contratos.md).

## Huecos conocidos del motor

| Pieza | Estado |
| --- | --- |
| Firma `X-Hub-Signature-256` | se exige; sin secret la API responde 503 |
| Cola de entrada | ACK + dedup `wamid` + debounce + `BackgroundTasks`; sin worker |
| Outbox de salida | no hay |
| `ToolSpec` completo (`input_schema`, `idempotency`, `timeout`, `audit_policy`) | parcial |
| Postventa | anota y escala; sin WRITE |
| Langfuse, MCP | no hay |
