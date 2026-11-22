# AGENTS.md · Factory Agent OS

Entrada única para agentes que trabajan en este repo. Leer esto y [`docs/00-vision-y-estado.md`](docs/00-vision-y-estado.md) antes de tocar código.

**Repo:** [Factory-Agent-OS-next](https://github.com/Atlaros/Factory-Agent-OS-next); en GitHub solo está `main`. No abras otra carpeta ni otro repo desde este chat. [Factory-Agent-OS](https://github.com/Atlaros/Factory-Agent-OS) es otro código, más viejo: no pisarlo. El paquete de código se llama `factory_os`.

## Qué es

Factory Agent OS es una fábrica de agentes para emprendedores, pymes y medianas empresas. Cada negocio arma sus flujos con los nodos que ofrece la plataforma. Primeros rubros: cafeterías y tiendas de ropa.

Dos capas, un producto:

- **Motor**: los módulos que hacen andar un negocio (WhatsApp, Adri, Cobros, Caja, catálogo, pedidos, proveedores, contabilidad, analítica, reportes). Ya opera una cafetería real. Ver [`docs/motor.md`](docs/motor.md).
- **Factory**: aislar negocios, crearlos desde plantilla, evals por rubro, consola, diagnóstico, lienzo con nodos, autonomía, alta sin operador. Es el trabajo de este repo.

El deploy de la cafetería no es trabajo de este repo.

## Mapa de docs

| Doc | Para qué |
| --- | --- |
| [00 Visión y estado](docs/00-vision-y-estado.md) | visión, estado por fase, qué falta. Manda sobre los demás |
| [01 Arquitectura](docs/01-arquitectura.md) | dos planos, stack, cómo se construye un agente, nodos, turno, datos |
| [02 Contratos](docs/02-contratos.md) | empleados, autonomía, nodos, skills, BBE, policies, tools, adaptadores |
| [03 Evaluación](docs/03-evaluacion.md) | evals por rubro, por nodo y de venta |
| [Motor](docs/motor.md) | qué da cada módulo hoy (ADR-001 a ADR-016 condensados) |
| [`docs/adr/`](docs/adr/) | ADR-000 (este repo), ADR-017 (visión y fases), ADR-018 a ADR-024 (una por fase), ADR-025 (lienzo con React Flow) |
| [`odd/README.md`](odd/README.md) | tareas ODD |

Si el código contradice un doc, se corrige el doc en el mismo cambio.

## Invariantes

- Tenant desde la identidad del runtime, nunca del texto del cliente ni del LLM. RLS. Cross-tenant = 0.
- READ amplio y controlado; WRITE por tool tipada + permiso + policy + validación + idempotencia.
- El LLM no recibe `DATABASE_URL`, service role, secretos ni SQL.
- Precio, stock, pago y pedido salen de Postgres, no del modelo.
- El texto del cliente no confirma un pago. Solo el adaptador. El empleado lee ese estado y sigue la conversación.
- El LLM conduce la venta. Las heurísticas son respaldo, no un guion paralelo.
- Skills no conceden permisos. BBE no sustituye policies ni validación.
- Un runtime para todos los empleados y todos los negocios. Un negocio es configuración, no un fork.
- Lo que mueve plata, stock, pedidos o asientos tiene piso de aprobación humana. El dueño lo endurece; no lo baja.
- El lienzo publica configuración validada; no ejecuta código, SQL ni APIs arbitrarias. `pago_confirmado` solo sale de Cobros.
- Redis no es fuente de verdad ni historial.

## Agregar un nodo

Solo si expresa un hecho que el catálogo no tiene. Contrato (puertos, módulo, piso de autonomía, rubros), tests de barandas, eval del rubro en verde. Se construye una vez para toda la plataforma. Detalle en [02](docs/02-contratos.md#agregar-un-nodo).

## Cómo se trabaja

- Gentle AI con **ODD**: cada cambio es una tarea en `odd/tasks/<feature>.md`, con Engram. SDD solo si el owner lo pide.
- Test primero (RED → GREEN). Loop: incidente → golden → tarea → regresión verde.
- SOLID pragmático: un módulo no escribe tablas de otro; cada integración entra por un puerto con Fake.
- Cambiar el alcance exige un ADR.
- Al cerrar una tarea, actualizar la fila de la fase en 00.
- No commitear ni pushear si el owner no lo pide.
- El negocio vivo no se toca: no aplicar migraciones a su base ni reiniciar su proceso (`:8000`, `:3000`).
- Docs de producto en español; identificadores de código en inglés.

## Correr

```bash
uv sync --extra dev            # pins from uv.lock; creates .venv
.venv/bin/pytest -q            # MODEL_PROVIDER=fake, sin red ni Docker
```

- Las dependencias se fijan en `uv.lock`. No lo ignores: un entorno nuevo tiene que resolver las mismas versiones.
- Pytest corre en memoria con el catálogo de Closet. Los tests con Postgres usan `FACTORY_OS_TEST_DATABASE_URL`; nunca la base del negocio vivo.
- Postgres local: `docker compose up -d db` (host `127.0.0.1:5434`). Crear base de test: `CREATE DATABASE factory_os_test;` + extensión `vector`. Luego:
  `FACTORY_OS_TEST_DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:5434/factory_os_test .venv/bin/pytest -q`
- Catálogo de cafetería con `CATALOG_SEED=cafe`.
- Panel: `cd apps/web && npm install && npm run dev`. Tests del panel: `cd apps/web && npm test`.
- `.env.example` tiene solo nombres. Nunca poner secretos en git, chat ni logs.

## Stack

Next.js 15 + React 19 + TypeScript (`apps/web`) · FastAPI + Python (`apps/api`, `packages/*`) · LangGraph solo para el turno · PostgreSQL + RLS + pgvector · Cohere · Model Gateway Gemini → OpenRouter → Groq · Redis para dedup de WhatsApp. Detalle en [01](docs/01-arquitectura.md).
