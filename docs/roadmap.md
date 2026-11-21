# Roadmap de implementación — AgentOS

**Estrategia:** no construir toda la infra financiera de golpe.  
**Corazón del MVP:** agente externo consulta wallet → solicita transferencia → ejecuta bajo policy.

Gate: **ninguna fase de código arranca** hasta aprobar ADRs + decisiones abiertas en `riesgos-y-decisiones.md`.

## Fase 0 — Auditoría (hecha)

- Entregable: `agentos-audit-fase0.md`  
- Criterio: Alternativa B elegida.

## Fase 1 — Arquitectura y ADRs (esta entrega)

- Entregables: ADRs 001–007, arquitectura, patrones, modelo de datos, estructura repo, contratos, flujo Stellar, roadmap, riesgos.  
- Criterio: owner aprueba o pide cambios; **sin código**.

## Fase 2 — Repositorio independiente (scaffolding)

- Crear repo vacío `AgentOS` (nombre a aprobar).  
- FastAPI hello + Postgres Compose + Alembic 001 (orgs mínimas) + CI pytest.  
- Criterios:
  - [x] CI workflow presente (GitHub Actions)
  - [x] Ningún import de Factory
  - [x] `.env.example` sin secretos

## Fase 3 — Identity & Access + Organizations

- Users/memberships (mínimo), Applications, API keys hasheadas, AgentIdentity, RLS.  
- Criterios:
  - [x] Crear org + app + key
  - [x] Request sin key = 401
  - [x] Cross-org isolation test verde

## Fase 4 — Wallet & Assets (+ Fake)

- Link wallet externa; list; balances vía `FakeNetworkAdapter`.  
- Criterios:
  - [x] Link + list por org
  - [x] Balances deterministas en Fake
  - [x] No columna de secret

## Fase 5 — Policy + PaymentRequest + Ledger (sin cadena real)

- Reglas allow/deny/require_human; approvals; ledger append-only.  
- Criterios:
  - [x] Monto alto → pending_approval
  - [x] Sin approve → execute = 403
  - [x] Ledger muestra decisiones

## Fase 6 — Stellar Testnet + Transfers

- `StellarTestnetAdapter`; execute + confirm; runbook lab.  
- Criterios:
  - [x] Transfer testnet confirmada (adapter live)
  - [x] Idempotency no doble submit (Fake + intent unique)
  - [x] Fake sigue siendo default en unit

## Fase 7 — REST completo + MCP + SDK

- Contratos de `contratos-rest-mcp.md`; MCP tools; SDK Python thin.  
- Criterios:
  - [x] SDK thin + MCP tools sobre SDK (misma policy)
  - [x] MCP no bypasea policy (sin tools raw submit)

## Fase 8 — Piloto consumidor (fuera de Agent-IA / Factory)

- Cliente **con forma de Agent-IA** en `examples/pilot_agent_ia_client.py`; **sin** editar repos Agent-IA/Factory.  
- Criterios:
  - [x] Demo: consulta + payment request + transfer bajo policy vía SDK
  - [x] Factory sin cambios requeridos

## Deuda lab cerrada (post F8)

- [x] Reject payment + create application/agent + list/get agents
- [x] Demo Stellar vía API (`scripts/demo_stellar_api.py`)
- [ ] CI verde en GitHub Actions — **bloqueado**: cuenta Atlaros locked por billing (runs no arrancan). Workflow corregido a Postgres `:5432` en GHA.

## Post-MVP (explícitamente después)

Custodia/KMS · OAuth2 · Mainnet · Otros adapters · Baneco solo si API verificada · Billing · UI consola propia.

## Orden recomendado (resumen ejecutivo)

1. Cerrar ADRs  
2. Repo + CI  
3. Identity  
4. Wallets + Fake  
5. Policy + Ledger  
6. Stellar Testnet  
7. MCP/SDK  
8. Piloto Agent-IA  
