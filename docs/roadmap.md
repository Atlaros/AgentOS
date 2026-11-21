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
  - [ ] CI verde en PR
  - [ ] Ningún import de Factory
  - [ ] `.env.example` sin secretos

## Fase 3 — Identity & Access + Organizations

- Users/memberships (mínimo), Applications, API keys hasheadas, AgentIdentity, RLS.  
- Criterios:
  - [ ] Crear org + app + key
  - [ ] Request sin key = 401
  - [ ] Cross-org isolation test verde

## Fase 4 — Wallet & Assets (+ Fake)

- Link wallet externa; list; balances vía `FakeNetworkAdapter`.  
- Criterios:
  - [ ] Link + list por org
  - [ ] Balances deterministas en Fake
  - [ ] No columna de secret

## Fase 5 — Policy + PaymentRequest + Ledger (sin cadena real)

- Reglas allow/deny/require_human; approvals; ledger append-only.  
- Criterios:
  - [ ] Monto alto → pending_approval
  - [ ] Sin approve → execute = 403
  - [ ] Ledger muestra decisiones

## Fase 6 — Stellar Testnet + Transfers

- `StellarTestnetAdapter`; execute + confirm; runbook lab.  
- Criterios:
  - [ ] Transfer testnet confirmada
  - [ ] Idempotency no doble submit
  - [ ] Fake sigue siendo default en unit

## Fase 7 — REST completo + MCP + SDK

- Contratos de `contratos-rest-mcp.md`; MCP tools; SDK Python thin.  
- Criterios:
  - [ ] Mismo use-case vía REST y MCP
  - [ ] MCP no bypasea policy

## Fase 8 — Piloto consumidor (fuera de AgentOS)

- Agent-IA V2 (cafetería) como **cliente**; no merge de código.  
- Criterios:
  - [ ] Demo: consulta + payment request + transfer bajo policy
  - [ ] Factory sin cambios requeridos

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
