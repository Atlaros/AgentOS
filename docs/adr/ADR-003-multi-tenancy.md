# ADR-003 — Multi-tenancy

**Estado:** propuesto (pendiente aprobación)  
**Fecha:** 2026-11-20

## Contexto

Factory usa `tenant_id` + RLS con `app.tenant_id` y rol runtime sin `BYPASSRLS`. El patrón es útil; el schema no se copia.

## Decisión propuesta

- Tenant = **Organization** en AgentOS.
- Toda fila de negocio lleva `organization_id`.
- Postgres RLS: `organization_id = current_setting('app.organization_id')::uuid`.
- Rol de aplicación distinto del rol admin de migraciones.
- La identidad del tenant **nunca** viene del texto de un LLM ni del body sin autenticar.

## Consecuencias

- Reimplementar el patrón RLS (referencia conceptual a Factory `002_rls.sql` / `tenant_connection`), schema propio.
- Tests de aislamiento cross-org obligatorios desde el MVP.

## Abierto

- ¿Un usuario humano puede pertenecer a varias orgs? (recomendado: sí, con membership).
