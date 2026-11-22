# 01 — Arquitectura

Cómo está armado Factory Agent OS. Visión y estado en [00](00-vision-y-estado.md). Qué da cada módulo del motor en [motor](motor.md).

## Dos planos

| Plano | Qué decide | Dónde vive |
| --- | --- | --- |
| **Control** (Factory) | qué negocios hay, de qué rubro, qué módulos tienen prendidos, qué reglas publicaron, cuánta autonomía tiene cada empleado, quién entra | consola del operador, panel del dueño, lienzo, alta; tablas `tenants`, `catalog_rules`, `catalog_rule_versions`, autonomía |
| **Ejecución** (motor) | qué pasa en cada turno de WhatsApp, cada cobro, cada ticket de caja, cada asiento | runtime de agentes, tools, adaptadores, módulos del dominio |

El plano de control **publica configuración versionada**. El plano de ejecución **la lee**. El lienzo no ejecuta nada: guarda y publica. Si una configuración no pasa validación, no se publica.

## Stack

| Pieza | Elección | Para qué |
| --- | --- | --- |
| Panel, consola y lienzo | Next.js 15 + React 19 + TypeScript (`apps/web`) | las tres superficies de UI |
| Lienzo | React Flow (`@xyflow/react`), [ADR-025](adr/ADR-025-lienzo-con-react-flow.md) | dibujo e interacción; la validación sigue en el servidor. Hoy el lienzo todavía está hecho a mano |
| API | Python + FastAPI (`apps/api`) | webhooks, panel, consola, alta |
| Turno conversacional | LangGraph, grafo corto | solo el turno de WhatsApp, no los procesos del negocio |
| Modelo | Model Gateway Gemini → OpenRouter → Groq | `propose` y `draft`; Fake en pytest |
| Datos | PostgreSQL con RLS + pgvector | fuente de verdad de todo |
| Embeddings | Cohere | descubrir productos y fragmentos de la ficha |
| Redis | claim y dedup de entrada de WhatsApp | no es fuente de verdad ni historial |
| Tests | pytest (`tests/`, `evals/`) | el panel todavía no tiene runner |

Astro queda solo para un posible sitio público (`apps/site`), nunca para el panel.

## Las tres superficies

| Superficie | Quién | Qué hace |
| --- | --- | --- |
| Consola del operador (`/operator`) | nosotros | crea negocios desde plantilla, ve módulos, versiones, tokens, estado de WhatsApp, diagnóstico, lienzo |
| Panel del dueño (`/`, `/owner`) | el negocio | opera: pedidos, caja, catálogo, contabilidad, conocimiento, autonomía |
| Lienzo (`/operator/flow`) | operador, luego dueño | paleta \| lienzo \| propiedades; el núcleo está bloqueado |

Todas usan el shell y los tokens del panel ([motor, ADR-005](motor.md#adr-005--panel-y-sistema-visual)).

## Cómo se construye un agente

Un agente no es un chatbot aparte. Es una entrada en el runtime único con tres partes.

| Parte | Qué es | Quién la cambia |
| --- | --- | --- |
| **Contrato** | `EmployeeContract`: rol, canal, tools permitidas, límites, piso de autonomía | la plataforma lo define; el dueño puede endurecerlo, no aflojarlo |
| **Cerebro** | el orquestador propone WHO y el empleado propone WHAT con el Model Gateway. Las invariantes y el prompt base están en código; la identidad y el estilo salen de la ficha del negocio (`shop_knowledge`) | prompt base: código; estilo: el dueño |
| **Manos** | tools tipadas con el pipeline Permission → BBE → Skill → Policy → Confirmación → handler → validación → trace | código, una vez para todos los negocios |

## El turno

```text
WhatsApp → webhook (firma, dedup wamid, debounce)
  → tenant desde el número que recibe
  → grafo LangGraph: orquestador → empleado
  → el empleado propone; el runtime autoriza y ejecuta tools
  → draft con hechos de Postgres → grounded_draft → respuesta
```

- `thread_id = conversation_id`. El paso durable vive en `WorkingState.graph_node` (Postgres). El checkpointer de LangGraph está en memoria (`graph.py`).
- El grafo se arma por negocio: `graph_nodes_for_modules` elige `adri` / `cobros` / `operaciones` / `postventa` según los módulos del tenant (vacío = los cuatro). El orquestador siempre corre. Falta atarlo al mapa publicado del lienzo.
- Una escritura negada no corta el turno: el empleado recibe el hecho y sigue la charla.

## Nodos

Un **nodo del lienzo** es una pieza de negocio con puertos tipados. No es un nodo de LangGraph.

| Campo | Ejemplo |
| --- | --- |
| Puertos de salida y entrada | `pedido`, `pago_confirmado`, `aviso`, `aprobacion` |
| Módulo que lo respalda | Cobros, Caja, Proveedores |
| Piso de autonomía | confirmar pago: nunca automático |
| Rubros donde está | cafetería, ropa |

- Dos nodos se unen solo por el mismo puerto. El camino canal → pedido → Cobros está bloqueado: no se borra ni se puentea. «Pago confirmado» solo sale de Cobros.
- Las **reglas** (Cuando → Si → Entonces) reaccionan a hechos guardados en Postgres y corren como código común, con aprobación humana cuando tocan plata o stock.
- El contrato de cada nodo vive en `packages/contracts/.../nodes.py`. De ahí salen la paleta y la validación del lienzo. El turno ya se recorta por módulos activos; el mapa publicado del lienzo todavía no manda el grafo.

## Datos

- Todo dato de negocio lleva `tenant_id`. RLS lo filtra; el tenant sale de la identidad del runtime.
- Las tablas de plataforma que la consola lee para todos los negocios (`tenants`, `catalog_rule_versions`) no tienen RLS y solo las toca la consola.
- Un módulo no escribe tablas de otro módulo. Si necesita algo, lo pide por su función de dominio.
- pgvector descubre; el catálogo estructurado manda en precio, stock y variantes.
- Migraciones en `db/migrations/` (SQL numerado). Nunca se aplican solas a la base del negocio vivo.

## Memoria de la conversación

| Capa | Dónde |
| --- | --- |
| Mensajes | Postgres, por conversación |
| Estado del turno | `WorkingState` en Postgres |
| Carpeta del handoff | hechos (`order_id`, `payment_state`, `need`, `pending`) |
| Ficha del cliente | Postgres |
| Redis | solo claim y dedup; nunca historial |

## Puertos y adaptadores

El dominio no conoce proveedores. Cada integración entra por un puerto: canal (Meta WhatsApp), pago (Baneco QR), modelo (Model Gateway), medios (`MediaEnricher`), factura. Cada puerto tiene un Fake para pytest. Detalle en [02](02-contratos.md).

## Árbol

```text
apps/api/        FastAPI: webhooks, panel, consola, alta
apps/web/        Next.js: panel del dueño, consola, lienzo
packages/
  contracts/     contratos: empleados, tools, puertos
  domain/        módulos del negocio y de Factory (tenant_config, provision, autonomy, process_catalog, flow_canvas)
  agents/        orquestador, empleados, grafo
  harness/       Model Gateway, policies, BBE, trazas
  tools/         tools tipadas
workers/         tareas fuera del turno
db/              migraciones y seeds (cafetería, Closet)
evals/           goldens por rubro, salida de plantilla, calidad de venta
tests/           pytest
odd/             tareas ODD
docs/            esta documentación
```
