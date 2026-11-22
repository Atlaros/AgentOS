# Riesgos de seguridad y decisiones pendientes

**Estado:** bloquean o condicionan el inicio de código (Fase 2+).

## Riesgos (MVP)

| ID | Riesgo | Mitigación propuesta | Severidad |
| --- | --- | --- | --- |
| R1 | Filtración de secret keys | No persistir secrets; signer solo en env/lab; scans en CI | Crítica |
| R2 | Cross-tenant leak | RLS + tests obligatorios; org solo desde auth | Crítica |
| R3 | Agent bypasea policy vía MCP | MCP → mismos use cases; sin tools “raw submit” | Alta |
| R4 | Doble gasto / replay | Idempotency keys + unique constraints | Alta |
| R5 | Confundir testnet con mainnet | `network` explícito; adapter testnet separado; deny mainnet en MVP | Alta |
| R6 | Copiar deuda Factory por error | Repo nuevo; checklist anti-copia; review de deps | Media |
| R7 | Asumir Baneco/fiat sin contrato | Fuera de alcance; sin adapter fiat hasta verificación | Media |
| R8 | Custodia “temporal” que se queda | ADR-004: custodial = post-MVP con ADR nuevo | Alta |
| R9 | Prompt injection → “pagá” | Texto nunca autoriza; solo subject+policy+adapter | Alta |
| R10 | Horizon/API downtime | Estados `submitted`/`failed`; reintentos acotados; no mentir `confirmed` | Media |

## Decisiones que necesitan aprobación antes de programar

Marcá sí/no o elegí opción. Sin esto, **no** se crea repo ni se escribe código.

### D1 — Estrategia
- [x] **Aprobar Alternativa B** (repo nuevo, extracción selectiva) — ADR-001

### D2 — Nombre y hosting del repo
- [x] Nombre: `AgentOS`
- [x] Org GitHub: `Atlaros`
- [x] Visibilidad: private

### D3 — Auth MVP
- [x] API keys hasheadas + scopes (recomendado ADR-007)  
- [ ] OAuth2 client-credentials desde día 1

### D4 — Signer path en lab Stellar
- [x] Secret solo en env del proceso adapter (lab)  
- [ ] Mini signer service aparte desde el inicio

### D5 — Asset del piloto Testnet
- [x] XLM nativo  
- [ ] Asset de confianza (issuer lab)

### D6 — MCP en el mismo tren que primera transfer
- [ ] Sí: REST+MCP juntos en Fase 7 inmediata post-Stellar  
- [x] No: primero REST+SDK; MCP fase siguiente

### D7 — Membership multi-org
- [x] Un user en varias orgs (recomendado)  
- [ ] Un user = una org en MVP

### D8 — Ubicación de esta documentación al crear el repo
- [x] Copiar ADRs/docs aprobados a `docs/` del repo nuevo  
- [ ] Dejar el store como archivo histórico y reescribir en repo

### D9 — Confirmación de exclusiones
- [x] Confirmo: no modificar Factory ni Agent-IA V2  
- [x] Confirmo: no copiar migraciones / LangGraph / WhatsApp / lienzo / catálogo / pedidos / stock / contabilidad comercial

**Aprobado para demo domingo (2026-11-20):** deliverable B — Fake E2E wallet → transfer under policy. MCP y Stellar Testnet quedan stretch/post-demo.

## Decisiones explícitamente aplazadas (no bloquean scaffolding)

- Custodia / KMS / HSM  
- Mainnet  
- EVM u otras chains  
- Baneco u otros rails fiat  
- Consola web propia  
- Billing / planes SaaS  
- MCP Client (AgentOS como consumidor)

## Criterio para desbloquear Fase 2

Owner responde D1–D9 (mínimo D1, D2, D3, D4, D9).  
Entonces: crear repo vacío + scaffolding según `estructura-repo.md` y `roadmap.md` Fase 2.
