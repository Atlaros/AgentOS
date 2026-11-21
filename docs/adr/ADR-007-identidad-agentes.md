# ADR-007 — Identidad de aplicaciones y agentes

**Estado:** propuesto (pendiente aprobación)  
**Fecha:** 2026-11-20

## Contexto

Factory autentica panel con bearer de dueño. AgentOS necesita identidad de *apps* y *agentes* que operan por API.

## Decisión propuesta (MVP)

- **Organization**
- **User** (humano, membership + roles)
- **Application** (cliente OAuth2 client-credentials o API key hasheada)
- **AgentIdentity** (sujeto no humano ligado a Application + scopes)

Toda operación financiera exige: `organization_id` + subject (`user` | `application` | `agent`) + scopes + evaluación Policy.

No hay “el LLM dijo que pague” como autorización.

## Consecuencias

- Tokens de corta vida + rotación.
- Scopes mínimos: `wallets:read`, `balances:read`, `payments:create`, `transfers:execute`, `audit:read`.

## Abierto

- OAuth2 completo vs API keys hasheadas en MVP (recomendación: API keys hasheadas + scopes para ir más rápido; OAuth después).
