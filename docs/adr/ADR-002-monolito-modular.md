# ADR-002 — Monolito modular

**Estado:** propuesto (pendiente aprobación)  
**Fecha:** 2026-11-20

## Contexto

AgentOS necesita límites claros (identity, wallets, ops, policy, adapters) sin microservicios prematuros.

## Decisión propuesta

Un **monolito modular** (un proceso API, un Postgres, paquetes internos por dominio).

Separación futura a servicios solo cuando un dominio lo justifique por escala o equipo.

## Consecuencias

- Deploy simple para MVP.
- Contratos internos entre módulos (imports solo hacia *ports*, no entre implementaciones de adapters).
- Un CI y un artefacto.

## Alternativas

- Microservicios desde día 1: costo operativo alto sin tráfico.
