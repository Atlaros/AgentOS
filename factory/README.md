# Factory Agent OS

### Empleados digitales que atienden, venden y cobran — con el dueño siempre al mando.

**Factory Agent OS** es la fábrica de agentes de Atlaros para emprendedores, pymes y medianas empresas. El negocio arma sus flujos con nodos de plataforma; el equipo humano trabaja junto a empleados digitales en WhatsApp, mostrador y caja.

Primera idea, sin adornos:

> **Primero comprender. Después mejorar. Después automatizar.**  
> Lo que mueve plata, stock, pedidos o asientos tiene piso de aprobación humana. El dueño lo endurece; **nunca** lo baja.

Primeros rubros: **cafeterías** y **tiendas de ropa**.

---

## El problema

Las pymes ya venden por chat. Un bot genérico inventa precios, “confirma” pagos con texto y no deja auditoría. Un ERP completo es demasiado. Un lienzo libre donde se programa cualquier cosa es peligroso.

Hace falta un **equipo híbrido**: personas + agentes, sobre el mismo negocio, con barandas reales.

## La respuesta

```text
Cliente (WhatsApp / mostrador)
        │
        ▼
┌────────────── Motor ──────────────┐
│  Catálogo · pedidos · cobros      │
│  Caja · stock · proveedores       │
│  Contabilidad gerencial · reportes│
└───────────────┬───────────────────┘
                │ gobernado por
                ▼
┌──────────── Factory ──────────────┐
│  Multi-negocio · plantillas       │
│  Operador · diagnóstico · lienzo  │
│  Autonomía · roster · evals       │
└───────────────────────────────────┘
```

| Capa | Qué es | Para el negocio |
| --- | --- | --- |
| **Motor** | Los módulos que hacen andar el día a día | Atiende, vende, cobra, registra |
| **Factory** | La plataforma que convierte el motor en producto multi-negocio | Alta en horas, sin fork por cliente |

Un módulo se construye **una vez**. Una plantilla es **datos**. Un negocio es **configuración**, no un repositorio aparte.

---

## Qué puede hacer hoy

| Capacidad | Valor |
| --- | --- |
| **Empleados digitales por rol** | Ventas, cobros, ops… roster por tenant, clones seguros (ADR-026) |
| **Conversación comercial** | El LLM conduce la venta; el runtime autoriza y ejecuta |
| **Cobros con baranda** | El texto del cliente **nunca** confirma un pago — solo el adaptador |
| **Lienzo con barandas** | React Flow: publicar flujos validados; puerto `equipo` para agentes (ADR-027) |
| **Consola del operador** | Negocios, lienzo, empleados, autonomía, invitaciones |
| **Aislamiento** | Tenant desde identidad del runtime + RLS. Cross-tenant = 0 |
| **Evals por rubro** | Café y ropa con suites que protegen regresiones |

El motor **opera un negocio real**. El trabajo de este repo es Factory (plataforma). El deploy del café vivo **no** se toca desde aquí.

---

## Qué no es

- Un ERP completo ni estados financieros oficiales  
- Un chatbot suelto sin caja ni políticas  
- Un lienzo libre para ejecutar código, SQL o APIs arbitrarias  
- Un producto distinto (fork) por cada cliente  

---

## Cómo saber que funciona

| Medida | Meta |
| --- | --- |
| Alta de un negocio de rubro conocido | En horas, sin código nuevo |
| Cambios de código por cliente | Tienden a cero |
| Fugas entre negocios | Cero, con pruebas de aislamiento |
| Automatizaciones de plata o stock | Todas con piso de aprobación humana |

Estado por fase: [`docs/00-vision-y-estado.md`](docs/00-vision-y-estado.md) (fuente de verdad).

---

## Empezá acá

| Si sos… | Abrí |
| --- | --- |
| Agente / contribuidor | [`AGENTS.md`](AGENTS.md) |
| Producto / visión | [`docs/00-vision-y-estado.md`](docs/00-vision-y-estado.md) |
| Arquitectura | [`docs/01-arquitectura.md`](docs/01-arquitectura.md) |
| Contratos e invariantes | [`docs/02-contratos.md`](docs/02-contratos.md) |
| Motor (módulos vivos) | [`docs/motor.md`](docs/motor.md) |
| Lab + AgentOS | [`docs/lab-production-like.md`](docs/lab-production-like.md) |

### Invariantes (no negociables)

1. El tenant sale de la **identidad del runtime**, nunca del texto del cliente ni del LLM.  
2. READ amplio y controlado; WRITE tipado + permiso + policy + validación + idempotencia.  
3. El LLM **no** recibe `DATABASE_URL`, service role, secretos ni SQL.  
4. Precio, stock, pago y pedido salen de **Postgres**, no del modelo.  
5. Skills no conceden permisos. El lienzo publica configuración validada; no ejecuta código libre.  

---

## Correr en lab

```bash
uv sync --extra dev          # pins en uv.lock
.venv/bin/pytest -q          # MODEL_PROVIDER=fake · sin red ni Docker
```

Postgres de test (nunca la base del café vivo):

```bash
docker compose up -d db      # 127.0.0.1:5434
# CREATE DATABASE factory_os_test; + extensión vector
FACTORY_OS_TEST_DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:5434/factory_os_test \
  .venv/bin/pytest -q
```

Panel:

```bash
cd apps/web && npm install && npm run dev
```

Catálogo de cafetería: `CATALOG_SEED=cafe`. Secretos solo en `.env` local — nunca en git, chat ni logs.

---

## Stack

Next.js 15 · React 19 · TypeScript · FastAPI · LangGraph (turno) · PostgreSQL + RLS + pgvector · Redis (dedup WhatsApp) · Model Gateway (Gemini → OpenRouter → Groq).

---

## Relación con otros repos

| Repo | Rol |
| --- | --- |
| **Este** ([Factory-Agent-OS-next](https://github.com/Atlaros/Factory-Agent-OS-next)) | Factory Agent OS — plataforma + motor |
| [AgentOS](https://github.com/Atlaros/AgentOS) | Rieles financieros para agentes (wallets, policy, ledger, Stellar Testnet) |
| [Factory-Agent-OS](https://github.com/Atlaros/Factory-Agent-OS) | Código **viejo** — no pisar |

Juntos, la marca de producto es **Factory AgentOS**: Factory habla con el cliente; AgentOS mueve (y registra) la plata.

---

## Atlaros

Hecho para dueños que ya venden — y quieren agentes que trabajen **con** ellos, no **en lugar** de su criterio.
