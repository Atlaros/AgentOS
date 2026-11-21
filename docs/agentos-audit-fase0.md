# AgentOS — Auditoría Fase 0 (solo lectura)

**Fuente inspeccionada:** Factory Agent OS (`Factory-Agent-OS-next`, tip `3b9f419` / `main`).  
**Fecha:** 2026-11-20.  
**Restricción:** sin modificar el repo Factory; sin migraciones; sin secretos.  
**Confianza:** ver matriz al final.

---

## Resumen ejecutivo

Factory Agent OS es un monorepo (FastAPI + Next.js + Postgres/RLS + Redis + LangGraph en el turno) que combina:

1. Un **motor de comercio conversacional** (catálogo, pedidos, pagos QR Baneco/Fake, caja, contabilidad gerencial, WhatsApp Meta) — en gran parte el “motor” heredado / fusionado desde la línea Agent-IA V2 / piloto.
2. Una capa **Factory** (aislamiento multi-negocio, provision, consola, lienzo con barandas, reglas publicadas, autoservicio apagado).

**AgentOS no debe ser el “siguiente nivel” de Factory.** Es un producto paralelo: infraestructura financiera agnóstica (wallets, redes, políticas, REST/SDK/MCP). Factory y Agent-IA pueden ser *consumidores* después.

**Recomendación de extracción: Alternativa B (extracción selectiva)** a un repo nuevo vacío, copiando solo patrones y módulos REUSE/ADAPT/EXTRACT. No fork-and-delete del monorepo completo (arrastra WhatsApp, lienzo de rubro, catálogo, seeds de café).

---

## Documento 1 — Inventario del repositorio

### Stack (confirmado por código)

| Capa | Tecnología | Evidencia |
|------|------------|-----------|
| API | FastAPI / uvicorn | `pyproject.toml`, `apps/api/factory_os/api/main.py` |
| Panel | Next.js 15 / React 19 | `apps/web/package.json` |
| Turno agentes | LangGraph (solo WhatsApp turn) | `packages/agents/.../graph.py` |
| DB | Postgres + pgvector + RLS | `docker-compose.yml`, `db/migrations/002_rls.sql` |
| Cache/dedup | Redis | `docker-compose.yml`, tools inbound |
| Modelos | Gemini → OpenRouter → Groq | `harness/model_gateway.py` |
| Embeddings | Cohere (fallback hash) | `domain/embeddings.py` |

### Estructura

- `apps/api` — webhooks, panel, operator, signup  
- `apps/web` — panel dueño, operator, flow, owner, signup  
- `packages/{contracts,domain,agents,harness,tools,namespace}`  
- `db/migrations` 001–060 + seeds  
- `tests/`, `evals/`, `odd/`, `workers/` (stub), `mcp/` (periférico / docs)

### Integraciones externas (nombres; sin secretos)

Meta WhatsApp, Baneco QR, Gemini/OpenRouter/Groq, Cohere, Postgres (a veces pooler Supabase en hosted). Langfuse/MCP de pagos: **no** en motor vivo (`docs/motor.md`).

### Auth real vs documentada

- Documentado: `AUTH_MODE=test` / Supabase keys en `.env.example`.  
- Implementado: Bearer `OWNER_DASHBOARD_TOKEN` + panel users / owner sessions. **No** hay SDK Supabase Auth en el código auditado.

### Entry points

- `factory-os-api`, `factory-os-worker` (stub), Next `:3000`.

---

## Documento 2 — Matriz de procedencia

| Módulo / ruta | Clasificación | Evidencia |
|---------------|---------------|-----------|
| Bootstrap Closet, agents early, commerce SQL 001–016 | **Factory** ( Closet runtime en este repo) | `37ccc4d`, `456751a`, `d122498` |
| Caja, contabilidad, proveedores, media, SQL ~022–047 | **Integración / motor heredado** (msg: Agent-IA V2) | Merge `9a88dd9`; bulk `8389a81` |
| Rename Agent-IA → Factory | **Nuevo (rename)** | `ea99890` |
| `flow_canvas`, `rule_runtime`, `turn_modules`, `nodes` contract | **Factory** | commits post-merge (`4536888`…`3eee5f8`, `9662a0a`) |
| `provision`, `operator_registry`, operator UI | **Factory** | `b9657e6`, `4f42cb4` |
| owner / signup / invites / sessions | **Factory** | `61715bc`, `a8e8889`, migs 055–057 |
| Isolation migs 048–049, autonomy 059, published maps 060 | **Factory** | phase-1 commits |
| harness Model Gateway, tool runtime | **Compartido** (patrón plataforma) | bootstrap + ADR runtime |
| Baneco / Meta adapters | **Motor / integración** | `tools/payments.py`, `tools/channel.py` |
| Byte-identity vs Agent-IA V2 remoto | **Indeterminado** | sin comparación a remoto Agent-IA (no fetch) |

---

## Documento 3 — Matriz de reutilización para AgentOS

| Componente | Veredicto | Por qué |
|------------|-----------|---------|
| Multi-tenant + RLS (`app.tenant_id`) | **REUSE** | Patrón probado; portable |
| Autonomy floor (never loosen money/stock) | **REUSE** | Modelo pequeño y claro para Policy Engine |
| Payment port + Fake provider + webhook idempotency | **ADAPT** | Puerto limpio; Baneco/BOB es específico |
| `confirm_from_adapter` choke point | **ADAPT** → núcleo ops financieras | Idea clave; no el SQL de pedidos/stock |
| Ledger / journal / caja | **EXTRACT** | Contabilidad operativa post-hecho; no es rail de wallet |
| Model Gateway / LangGraph / WhatsApp | **DISCARD** (para AgentOS core) | Consumidores externos traen su IA/canal |
| Lienzo Factory / NODE_CATALOG rubro | **DISCARD** | Producto distinto (factory de agentes de negocio) |
| Catálogo / pedidos / stock Closet-café | **DISCARD** del core AgentOS | Pueden vivir en apps consumidoras |
| Auth panel token | **REBUILD** | AgentOS necesita app/agent identity + OAuth/API keys |
| MCP server financiero | **REBUILD** | No existe; solo mención documental |
| Wallets / Stellar / claves | **REBUILD** | Ausente en el repo |
| Contabilidad gerencial completa | **DISCARD o EXTRACT parcial** | No es ledger on-chain; útil solo si AgentOS ofrece “books” aparte |

---

## Documento 4 — Arquitectura propuesta AgentOS

### Forma

**Monolito modular** al inicio (un deploy, un Postgres), límites de dominio claros. No microservicios hasta que el volumen lo pida.

### Dominios

1. **Identity & Access** — orgs, users, apps, agent identities, roles, delegated auth.  
2. **Wallet & Assets** — managed/external wallets, networks, balances, signing ports (nunca clave en fila plain).  
3. **Financial Operations** — intents de cobro/pago/transfer, estados, idempotency keys.  
4. **Policy & Authorization** — budgets, allowlists, human approval (reusar espíritu de `autonomy.py`).  
5. **Transaction & Audit** — append-only events, reconciliation hooks.  
6. **Adapters** — Stellar (primero), EVM/Solana luego, fiat ramps, custody, Baneco-like rails como *adapter* no como dominio.

### Interoperabilidad

- **REST** — fuente de verdad operativa.  
- **SDK** — cliente thin.  
- **MCP Server** — tools de consulta + ops gated por policy (no sustituye auth).  
- **MCP Client** — opcional post-MVP.

### Independencia de modelos

AgentOS **no** embebe LangGraph ni Model Gateway. Los agentes (Factory, Agent-IA, Crew, etc.) llaman REST/MCP.

### Diagrama (textual)

```
[Apps / Agents / Factory / Agent-IA]
        │ REST / SDK / MCP
        ▼
┌──────────────── AgentOS ────────────────┐
│ Identity │ Policy │ Ops Engine │ Audit   │
│          └──── Wallet & Assets ──────────│
│                    │                     │
│              Adapter ports               │
└─────────┬──────────┴──────────┬──────────┘
          ▼                     ▼
     Stellar Testnet      (otros adapters)
```

### Seguridad (mínimos antes de assets reales)

- Separar: wallet externa vs managed vs custody.  
- Claves: HSM/KMS o custody; **no** `private_key` en Postgres.  
- Idempotencia en toda op financiera (patrón webhook Factory).  
- Aprobación humana + límites (patrón autonomy).  
- Tenant isolation desde identidad de runtime, nunca del LLM.

---

## Documento 5 — Plan de extracción

### Alternativas

| Alt | Idea | Pros | Contras |
|-----|------|------|---------|
| **A Fork + delete** | Clonar Factory y borrar | Rápido al inicio | Arrastra deuda, SQL, UI, WhatsApp |
| **B Extracción selectiva** ★ | Repo vacío + copiar patrones/módulos | Independencia real | Más setup inicial |
| **C Monolito derivado** | Misma estructura, límites | Menos fricción | Riesgo de seguir acoplado |

**Recomendación: B.**

### Orden

0. Congelar alcance MVP (Stellar testnet + org + wallet + payment request + MCP read/write gated).  
1. Crear repo `AgentOS` (vacío), CI, `.env.example` propio, ADR-001 extracción aprobada.  
2. Portar **patrones**: tenancy/RLS template, autonomy/policy, payment *port* + Fake.  
3. Diseñar schema AgentOS (no copiar 060 migraciones de comercio).  
4. Implementar Identity + Policy + Ops + Stellar adapter.  
5. REST + MCP.  
6. Dashboard mínimo + piloto cafetería *como consumidor* (no como schema Factory).  
7. Solo entonces evaluar si Baneco/fiat entra como adapter.

### No hacer

- No apuntar AgentOS a la DB Supabase del café.  
- No mergear AgentOS dentro de `Factory-Agent-OS-next`.  
- No “limpiar” Factory para convertirlo en AgentOS.

---

## Documento 6 — Roadmap

| Fase | Contenido | Verificable |
|------|-----------|-------------|
| 0 | Esta auditoría + ADRs propuesta | Informe + aprobación humanas |
| 1 | Repo independiente + skeleton API | Hello + health + CI |
| 2 | Identity & orgs | CRUD org/user/app + auth |
| 3 | Wallets & assets (ports + Fake network) | Create/connect wallet, balance mock |
| 4 | Stellar testnet adapter | Real testnet tx verify |
| 5 | Ops engine + policies | Payment request + limits + audit |
| 6 | REST + MCP server | Agent externo ejecuta tool gated |
| 7 | Dashboard + piloto café *consumidor* | Flujo E2E documentado |
| 8 | Security review + threat model | Checklist firmado |

---

## Documento 7 — ADR propuestas (no aprobadas)

| ID | Tema | Opciones a decidir |
|----|------|--------------------|
| ADR-001 | Extracción | B selectiva vs A fork |
| ADR-002 | Forma | Monolito modular vs servicios |
| ADR-003 | Multi-tenancy | RLS Postgres vs app-level only |
| ADR-004 | Wallets/claves | External-only MVP vs managed + KMS |
| ADR-005 | Adapters chain | Stellar-first ports |
| ADR-006 | REST/SDK/MCP | MCP en MVP o fase 6 |
| ADR-007 | Identidad de agentes | API keys vs OAuth vs mTLS |

---

## Respuestas al formato §10

1. **Resumen:** Factory = motor comercio + factory de agentes; AgentOS = infra financiera nueva; extracción selectiva.  
2. **Estado real:** monorepo maduro en `main` `3b9f419`; fases Factory 1–4 hechas; 5–7 primer corte; sin blockchain/MCP financiero.  
3. **De Agent-IA V2:** sobre todo motor caja/contabilidad/media vía merge documentado; byte-identity **no** confirmada.  
4. **De Factory:** isolation, provision, operator, canvas, rules, turn-by-map, signup.  
5. **Integración:** rename, docs rewrite, cableado módulos↔APIs↔lienzo.  
6. **Reutilizar:** tenancy/RLS, autonomy, payment port+fake, webhook idempotency, extract ledger boundary.  
7. **Reconstruir:** identity API, wallets, Stellar, MCP, policy productizada, dashboard AgentOS.  
8. **Arquitectura:** monolito modular + adapters + REST/MCP.  
9. **Extracción:** Alternativa B.  
10. **Riesgos/bloqueos:** (a) sin diff a Agent-IA remoto; (b) Baneco≠motor multi-red; (c) no mezclar DB café; (d) claves privadas; (e) no arrastrar LangGraph/WhatsApp al core.  
11. **Roadmap:** fases 0–8 arriba.  
12. **Decisiones a aprobar:** ADR-001…007; MVP Stellar-only; ¿MCP en MVP?

### Matriz de confianza

| Afirmación | Nivel |
|------------|-------|
| Stack FastAPI/Next/Postgres/LangGraph-turno | Confirmado por código |
| Merge documentado Agent-IA V2 | Respaldado por historial Git |
| Bulk 022–047 = upstream motor | Inferido por estructura + msg merge |
| Paridad byte con Agent-IA V2 | No determinado |
| Ausencia Stellar/wallets/MCP finanzas | Confirmado por búsqueda |
| Patrón adapter pagos | Confirmado por código |

---

## Próximo paso (humano)

Aprobar o rechazar: **ADR-001 Alternativa B** y abrir repo vacío AgentOS.  
No implementar en Factory.
