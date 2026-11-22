# 00 — Visión y estado

Qué construimos, qué existe y qué sigue. Si otro documento contradice este, manda este.

## Visión

**Factory Agent OS es una fábrica de agentes para emprendedores, pymes y medianas empresas.** Cada negocio opera con un equipo mixto: el dueño y su gente, más empleados digitales que atienden, venden, cobran y ejecutan tareas. El negocio arma sus flujos con los nodos que la plataforma ofrece, sin programar.

Empezamos con dos rubros: **cafeterías** y **tiendas de ropa**. Los nodos y los módulos se piensan primero para esos dos. Un rubro nuevo entra con su plantilla; si le falta un hecho que el catálogo no expresa, se crea ese nodo una sola vez para toda la plataforma.

Idea rectora: **primero comprender, después mejorar, después automatizar.** Todo lo que mueve plata, stock, pedidos o asientos tiene un piso de aprobación humana. El dueño puede endurecerlo; no puede bajarlo.

## Dos capas, un producto

| Capa | Qué es | Estado |
| --- | --- | --- |
| **Motor** | Los módulos que hacen andar un negocio: WhatsApp, Adri, Cobros, Caja, catálogo y stock, pedidos, proveedores, contabilidad gerencial, analítica, reportes, conocimiento y medios. | Existe. Opera un negocio real. Ver [motor](motor.md) |
| **Factory** | Lo que convierte el motor en plataforma: aislar negocios, crearlos desde plantilla, evals por rubro, consola del operador, diagnóstico de procesos, lienzo con nodos, autonomía por negocio, alta sin operador. | En construcción. Es el trabajo de este repo |

Factory no reemplaza el motor y no es otro código base. Lo gobierna. El deploy del negocio vivo no es trabajo de este repo.

## Cómo se arma un negocio

```text
Núcleo (igual para todos)      negocios, usuarios, roles, auditoría, conversaciones, pedidos, pagos, runtime de agentes
Módulos (se prenden por negocio)  caja, proveedores, contabilidad, analítica, reportes, ...
Plantillas de rubro (datos)    cafetería, ropa
Negocios (configuración)       cada cliente
```

Un módulo se construye una vez. Una plantilla es solo datos: módulos activos, categorías, plan de cuentas, ficha y estilo del agente, piso de autonomía. Un negocio es una configuración, no un fork.

## Cómo sabemos que funciona

| Medida | Meta |
| --- | --- |
| Alta de un negocio de un rubro conocido | en horas, sin código nuevo |
| Cambios de código por cliente | tienden a cero |
| Fugas de datos entre negocios | cero, con pruebas de aislamiento |
| Una mejora del núcleo | no rompe un rubro ya probado |
| Automatizaciones que tocan plata o stock | todas con aprobación humana |

## Qué no es

Un ERP completo. Un chatbot aparte. Un lienzo libre donde se programa cualquier cosa. Un producto distinto por cliente. Estados financieros oficiales.

## Estado de Factory

Fases de [ADR-017](adr/ADR-017-vision-y-alcance-factory-agent-os.md). Leyenda: **hecho** = en código con tests · **primer corte** = funciona, con huecos nombrados · **no** = no empezó.

| Fase | Qué | Estado | Dónde |
| --- | --- | --- | --- |
| 1 | Aislamiento: dedup, buffer y canal por negocio; rubro y módulos como datos | hecho | [ADR-018](adr/ADR-018-aislamiento-de-negocios.md), `tenant_config.py` |
| 2 | Aprovisionamiento desde plantilla, con piso de autonomía | hecho | [ADR-019](adr/ADR-019-aprovisionamiento-desde-plantilla.md), `provision.py` |
| 3 | Evals por plantilla y lista de salida | hecho | [ADR-020](adr/ADR-020-evals-por-plantilla.md), `evals/` |
| 4 | Consola del operador: negocios, módulos, versiones, tokens por negocio, estado de WhatsApp | hecho | [ADR-021](adr/ADR-021-consola-del-operador.md), `/operator` |
| 5 | Catálogo de procesos por rubro y diagnóstico (cubierto, parcial, hueco) | primer corte | [ADR-022](adr/ADR-022-catalogo-de-procesos.md), `process_catalog.py` |
| 6 | Mapa y lienzo con barandas: puertos tipados, reglas versionadas, lienzo 2D, paleta | primer corte | [ADR-023](adr/ADR-023-lienzo-con-barandas.md), `flow_canvas.py`, `/operator/flow` |
| 7 | Autoservicio: alta con invitación, dueño, sesión, WhatsApp propio, autonomía | primer corte, apagado por defecto | [ADR-024](adr/ADR-024-autoservicio.md), `/signup`, `/owner` |
| — | Roster de empleados por tenant + clones sobre rol base (sin tools libres) | hecho | [ADR-026](adr/ADR-026-roster-empleados-por-tenant.md), `tenant_employees`, `/operator` Employees, `/owner` |
| — | Empleados del roster en el lienzo (puerto `equipo`, team al publicar) | primer corte | [ADR-027](adr/ADR-027-empleados-en-lienzo.md), `flow_canvas` team, paleta Equipo |

## Qué falta

1. **Contrato de nodo único.** Hecho en `packages/contracts/.../nodes.py`: puertos, módulo, piso de autonomía y rubros. El lienzo lo lee; no lo redefine.
2. **Los módulos activos gobiernan de verdad.** Hecho para mapa, nav y APIs del módulo: el lienzo sale de `tenant_id`, el panel oculta pestañas apagadas y un GET a un módulo apagado responde `404 module_disabled`. Vacío = piloto sin restricción.
3. **Las reglas publicadas corren.** Hecho el corte de café/ropa: `qr_pending → notify_owner`, `stock_low → draft_purchase_order`, `owner_digest → notify_owner`, `payment_overdue → notify_owner` y `customer_inactive → notify_owner` vía `POST /api/rules/run` (`rule_runtime.py`). Idempotente; no confirma pagos. Más eventos solo si un rubro nuevo los pide.
4. **El turno se arma por negocio.** Hecho: el turno prefiere el mapa publicado del lienzo (`publish_flow_map` / `POST /api/operator/flow-map/publish`); si no hay publicación, cae a los módulos del tenant (`graph_nodes_for_modules`). Vacío = piloto completo. Sin `cobros` (en mapa o módulos) el orquestador no enruta ahí. Publicar sin `pedido`+`cobros` responde `path_locked`.
5. **Lienzo completo.** Hecho el corte de producto: React Flow ([ADR-025](adr/ADR-025-lienzo-con-react-flow.md)) con selección → panel de propiedades (kind, locked, puertos), barra Try / Publish map / Propose (`POST …/flow-map/try|publish|propose`). Propose nunca publica solo; Apply proposal solo coloca en el lienzo. `tests/test_flow_canvas.py` y guards Vitest siguen verdes.
6. **Tests del panel.** Hecho el corte: Vitest en `apps/web` (`npm test`) con helpers puros y RTL/jsdom sobre `FlowPropertiesPanel` (`flow-properties.test.tsx`). Barandas del lienzo (ADR-025) siguen en `flow-guards.test.ts`.
7. **Pruebas con Postgres.** Primer corte: con `docker compose up -d db` y `FACTORY_OS_TEST_DATABASE_URL` a una base dedicada (`factory_os_test` en `:5434`), los tests de Postgres corren. Nunca apuntar a la base del café.
8. **Roster de empleados por negocio.** Hecho ([ADR-026](adr/ADR-026-roster-empleados-por-tenant.md)): seed al provisionar, enable/rename/style, clones sobre `base_role` (permisos ⊆ base), WHO filtra disabled, API/UI operador y dueño, evals café/ropa. Lab only ([lab-production-like](lab-production-like.md)); no el café vivo.
9. **Empleados en el lienzo.** Primer corte ([ADR-027](adr/ADR-027-empleados-en-lienzo.md)): paleta Equipo (roster enabled), nodos `emp:{key}`, puerto `equipo` hacia módulos permitidos por `CANVAS_MODULES_BY_ROLE`, `team` al publicar. Sin billeteras ni tools libres.

Las tareas viven en [`odd/README.md`](../odd/README.md).

## Cómo se actualiza

Cuando una tarea cierra, se actualiza la fila de la fase en el mismo cambio. Si cambia el alcance, primero va un ADR.
