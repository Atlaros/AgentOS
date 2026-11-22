# ADR-006 — REST, SDK y MCP

**Estado:** propuesto (pendiente aprobación)  
**Fecha:** 2026-11-20

## Contexto

Los consumidores serán apps y agentes. MCP no sustituye auth ni custodia.

## Decisión propuesta

| Interfaz | Rol en MVP |
| --- | --- |
| **REST API** | Interfaz operativa principal (CRUD + ops) |
| **SDK** (Python primero) | Cliente thin sobre REST |
| **MCP Server** | Tools de lectura + ops gated por Policy (mismo backend que REST) |

MCP Client (AgentOS consume tools externas) = post-MVP. Entregado como librería, no como proxy REST.

## Actualización — MCP Client

`connect_mcp` (`agentos_mcp.client`) abre una sesión contra un servidor externo por stdio, Streamable HTTP, o in-process en tests. Lista tools y llama una; el texto del resultado es `str`. Tool ausente o con error: `McpToolError`.

No autentica contra AgentOS, no crea payment requests, transfers ni asientos de ledger, y no persiste servidores externos.

## Consecuencias

- Una sola capa de autorización sirve REST y MCP.
- Tools MCP mapean 1:1 a casos de uso, no a SQL.

## Abierto

- ¿MCP entra en la misma release que la primera transferencia Stellar o en la fase siguiente inmediata?
