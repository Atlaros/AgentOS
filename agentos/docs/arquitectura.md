# Arquitectura objetivo — AgentOS

**Estado:** propuesto · **Producto:** monolito modular independiente  
**Referencia:** ADR-001 … ADR-007 · auditoría Fase 0

## Principio

AgentOS es **infraestructura financiera para agentes y aplicaciones**.  
No es un bot, no es un lienzo, no es un POS. Los agentes viven *fuera* y consumen REST/MCP.

## Planos

```
┌─────────────────────────────────────────────────────────────┐
│  Consumidores: Agent-IA V2 · apps · agentes externos        │
│  (REST · SDK · MCP tools)                                   │
└───────────────────────────┬─────────────────────────────────┘
                            │ auth + org context
┌───────────────────────────▼─────────────────────────────────┐
│  API Gateway (FastAPI) — authn/authz, rate limit, idempotency│
├─────────────────────────────────────────────────────────────┤
│  Dominios (paquetes internos)                               │
│  1 Identity & Access                                        │
│  2 Organizations & Tenancy                                  │
│  3 Wallet & Asset Management                                │
│  4 Financial Operations                                     │
│  5 Policy & Authorization Engine                            │
│  6 Ledger & Transaction Audit                               │
│  7 Blockchain & Financial Adapters (Stellar Testnet + Fake) │
└───────────────────────────┬─────────────────────────────────┘
                            │
                    PostgreSQL + RLS
```

## Dominios (responsabilidad)

| # | Dominio | Responsabilidad | No hace |
| --- | --- | --- | --- |
| 1 | Identity & Access | Users, Applications, Agents, credentials, scopes | Chat / LLM |
| 2 | Organizations & Tenancy | Orgs, memberships, contexto RLS | Billing SaaS completo (MVP mínimo) |
| 3 | Wallet & Assets | Link wallets, assets, balances cached/read | Custodia de secrets |
| 4 | Financial Operations | PaymentRequest, TransferIntent, lifecycle | Contabilidad comercial |
| 5 | Policy | Límites, autonomía, aprobación humana | Heurísticas de venta |
| 6 | Ledger | Asientos de ops financieras, audit trail | Diario gerencial de café |
| 7 | Adapters | Stellar / Fake / futuros rails | Lógica de negocio |

## Flujo de una operación (resumen)

1. Cliente autentica → subject + `organization_id`.
2. Caso de uso valida input tipado.
3. Policy evalúa (límites, autonomía, aprobación).
4. Si `require_human` → estado `pending_approval` (no llama a red).
5. Si autorizado → Adapter ejecuta (idempotent key).
6. Ledger registra intento + resultado + refs de red.
7. Respuesta REST / tool MCP con estado canónico.

## Stack propuesto (MVP)

| Capa | Elección | Nota |
| --- | --- | --- |
| API | FastAPI + Python 3.12+ | Alineado a skills del equipo; no arrastra LangGraph |
| DB | PostgreSQL 16 + RLS | Schema nuevo; sin migraciones Factory |
| Auth | API keys hasheadas + scopes (MVP) | OAuth2 post-MVP (ADR-007) |
| Adapters | stellar-sdk (testnet) + Fake | Solo en módulo adapters |
| MCP | servidor MCP thin → mismos use cases | Misma policy |
| CI | GitHub Actions: lint + pytest | Sin Docker obligatorio en unit |
| Deploy | un servicio API + Postgres | Render/Fly/etc. a decidir |

**Excluido a propósito:** LangGraph, Redis-como-historial, Next.js de Factory, WhatsApp/Meta, React Flow.

## Invariantes

1. Tenant solo desde identidad confiable del runtime.
2. WRITE tipado + policy + validación + idempotencia.
3. Sin SQL arbitrario expuesto a agentes.
4. Sin secret keys en tablas de producto.
5. `pago_confirmado` / éxito on-chain solo desde adapter verificado, no desde texto.
6. Independiente de cualquier framework de agentes.

## Relación con Factory / Agent-IA

```
Agent-IA V2  ──REST/MCP──►  AgentOS
Factory      ──(futuro)──►  AgentOS   (opcional; no al revés)
```

AgentOS **no** importa paquetes de esos repos.
