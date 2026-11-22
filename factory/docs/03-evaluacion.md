# 03 — Evaluación

Un negocio se da por listo cuando sus evals pasan, no cuando responde un healthcheck. Se evalúa en tres niveles: por rubro, por nodo y por calidad de venta.

## Correr

```bash
.venv/bin/pytest -q
```

pytest usa `MODEL_PROVIDER=fake`, el store en memoria y embeddings hash: sin red, sin API keys, sin Docker. Con `FACTORY_OS_TEST_DATABASE_URL` (base dedicada, p. ej. `factory_os_test` en `127.0.0.1:5434`) corren también los tests de Postgres. Nunca apuntar pytest a la base del negocio vivo.

## Nivel 1 · Por rubro

Cada plantilla tiene una **lista de salida** (`evals/template_exit.py`, [ADR-020](adr/ADR-020-evals-por-plantilla.md)). Una plantilla está lista solo si pasan todos sus tests.

| Plantilla | Lista de salida |
| --- | --- |
| `ropa` | `evals/test_closet_golden.py` (vertical de punta a punta) + `evals/test_shop_rubro.py` (la FAQ de otro rubro no confirma pago ni cambia precio) |
| `cafe` | `evals/test_cafe_golden.py` (catálogo + el texto no confirma pago) |

Vertical ropa: crepé → confirmo → QR → "ya pagué" no alcanza → el adaptador confirma → Operaciones registra el envío.

Un rubro nuevo no entra sin su lista de salida en verde.

## Nivel 2 · Por nodo

Cada nodo del lienzo y cada módulo prueba sus barandas (`tests/test_flow_canvas.py`, `test_autonomy_enforcement.py`, `test_provision_business.py`).

| Caso | Esperado |
| --- | --- |
| Conexión entre puertos distintos | no se publica |
| Puentear Pedido → Cobros | rechazado |
| Una regla que produce `pago_confirmado` fuera de Cobros | rechazada |
| `kind` desconocido en la paleta | no entra |
| Aflojar la autonomía bajo el piso | falla |
| Acción con nivel `approval` sin confirmación | no corre |
| Volver a una versión publicada | la regla queda como esa versión |

Un nodo nuevo trae estos tests antes de aparecer en la paleta.

## Nivel 3 · Calidad de venta

El agente se evalúa porque vende, no porque responde.

| Eje | Pregunta |
| --- | --- |
| Grounding | ¿SKU, precio, stock y pago salen de Postgres? |
| WHO | ¿Atiende el empleado correcto en el momento correcto? |
| Fronteras | ¿Un empleado sin permiso es rechazado sin que corra el handler? |
| Pago | ¿El texto del cliente no confirma y el adaptador sí? |
| Venta | ¿Descubre, recomienda, trata la objeción y cierra? |

| Caso | Esperado |
| --- | --- |
| `hol` | saludo, no "producto inexistente" |
| `quiero la blusa pago1` | producto real; pedido si hay stock y confirmación del runtime |
| `algo elegante para una boda` | discovery o recomendación con hechos |
| `está caro` | objeción sin descuento inventado |
| `me llevo ese` | cierre + `order.create` |
| `ya pagué` | no cambia `payment_state` |
| Adri pide QR | DENY; el handler de pago no corre |
| Operaciones envía sin pago | DENY |
| Búsqueda sin sentido (`xyzqwerty-no-existe`) | sin hits, no inventa SKU |
| Preguntas de la ficha (delivery, devoluciones, redes) | respuesta desde `shop_knowledge`, sin inventar redes vacías |

Set comercial: [`evals/sales_quality/`](../evals/sales_quality/README.md), 25 casos con reglas y juez LLM opcional. Línea base en `baseline.json`; una medición nueva no puede empeorarla.

## Dónde vive cada cobertura

| Archivo | Cubre |
| --- | --- |
| `evals/test_closet_golden.py`, `test_cafe_golden.py`, `test_shop_rubro.py` | rubros |
| `evals/test_template_exit.py` | que cada plantilla tenga lista de salida |
| `tests/test_flow_canvas.py`, `test_process_catalog.py` | lienzo, reglas, diagnóstico |
| `tests/test_provision_business.py`, `test_autonomy_enforcement.py` | alta desde plantilla, autonomía |
| `tests/test_operator_console.py`, `test_public_signup.py`, `test_owner_*.py` | consola, alta, panel del dueño |
| `tests/test_tenant.py`, `test_whatsapp_dedup.py`, `test_postgres.py` | aislamiento y persistencia |
| `tests/test_adri_sales.py`, `test_stages.py` | venta, etapas |
| `tests/test_employees.py`, `test_backoffice.py` | empleados y fronteras de permiso |
| `tests/test_bbe_audit.py`, `test_skill_fields.py`, `test_contracts.py` | BBE, skills, contratos |
| `tests/test_handoff.py`, `test_handoff_folder.py`, `test_orchestrator.py` | WHO, carpeta, mesa humana |
| `tests/test_model_gateway.py` | gateway, failover, grounding del draft |

El panel (`apps/web`) corre Vitest: `cd apps/web && npm test`. Cubre barandas del lienzo, helpers puros (`flow-guards`, `suppliers-tab`, `api-base`, `media-url`, `export-links`) y RTL/jsdom sobre `FlowPropertiesPanel`.

## Loop

Incidente real → golden que lo reproduce → tarea ODD → regresión verde. Un bug no se cierra sin un test que lo habría atrapado.
