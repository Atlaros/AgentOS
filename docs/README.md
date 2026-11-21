# AgentOS — Fase 1 (arquitectura)

Paquete de diseño en este repositorio independiente.  
Producto nuevo: infraestructura financiera para agentes (REST · SDK · MCP).  
Primera red: **Stellar Testnet**.

## Decisión

**Alternativa B:** repositorio independiente + extracción selectiva de *patrones* (no módulos) + reconstrucción del dominio financiero.

Factory Agent y Agent-IA V2 **no se modifican** y **no son dependencias**.

## Índice

| Documento | Contenido |
| --- | --- |
| [agentos-audit-fase0.md](agentos-audit-fase0.md) | Auditoría Fase 0 |
| [adr/ADR-001-estrategia-extraccion.md](adr/ADR-001-estrategia-extraccion.md) | Repo nuevo vs fork |
| [adr/ADR-002-monolito-modular.md](adr/ADR-002-monolito-modular.md) | Monolito modular |
| [adr/ADR-003-multi-tenancy.md](adr/ADR-003-multi-tenancy.md) | Org + RLS |
| [adr/ADR-004-wallets-y-claves.md](adr/ADR-004-wallets-y-claves.md) | Wallets externas; sin secrets en DB |
| [adr/ADR-005-adaptadores-blockchain.md](adr/ADR-005-adaptadores-blockchain.md) | Ports + Stellar Testnet |
| [adr/ADR-006-rest-sdk-mcp.md](adr/ADR-006-rest-sdk-mcp.md) | Superficies de integración |
| [adr/ADR-007-identidad-agentes.md](adr/ADR-007-identidad-agentes.md) | Apps, agents, scopes |
| [arquitectura.md](arquitectura.md) | Dominios y planos |
| [patrones-referencia.md](patrones-referencia.md) | Qué estudiar / qué no copiar |
| [modelo-datos.md](modelo-datos.md) | Schema MVP |
| [estructura-repo.md](estructura-repo.md) | Carpetas y deps |
| [contratos-rest-mcp.md](contratos-rest-mcp.md) | API + tools |
| [flujo-stellar-testnet.md](flujo-stellar-testnet.md) | E2E transferencia |
| [roadmap.md](roadmap.md) | Fases y aceptación |
| [riesgos-y-decisiones.md](riesgos-y-decisiones.md) | **Aprobaciones pendientes** |

## Qué no hacer todavía

- No implementar código ni crear el repo hasta aprobar D1–D9.
- No tocar Factory Agent OS ni Agent-IA V2.
- No portar Baneco ni custodia.

## Corazón del MVP (recordatorio)

Un agente externo puede: **consultar wallet → solicitar transferencia → ejecutarla bajo políticas** (con aprobación humana cuando corresponda), auditado, vía REST y MCP.
