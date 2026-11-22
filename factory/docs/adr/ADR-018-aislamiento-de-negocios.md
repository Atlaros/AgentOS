# ADR-018 — Aislamiento de negocios

**Estado:** aceptado (18/11/2026). Autoriza la fase 1 de [ADR-017](ADR-017-vision-y-alcance-factory-agent-os.md).
**Relación:** no abre un segundo tenant en vivo, no adelanta el deploy del piloto y no cambia las decisiones del [motor](../motor.md).

---

## 1. Contexto

La fase 1 de ADR-017 pide que dos negocios de prueba no se vean, y que el arranque no modifique datos de otro negocio. Hoy el proceso atiende un solo negocio.

El dedup de WhatsApp ya recibe `tenant_id` y no lo usa. En memoria y en Redis la clave es solo el `message_id` (`wa:msg:{id}`). En Postgres el conflicto es solo `message_id`. El buffer de Redis arma la clave con el teléfono (`wa:buf:{wa}`), sin tenant.

## 2. Decisión

Un dato de un negocio no se lee ni se borra desde otro. El texto del cliente no elige el tenant. El tenant sale de la identidad del runtime. Un negocio puede reservar un `phone_number_id` distinto del canal de este proceso. Un mensaje que llega con ese identificador se contesta en la tienda de ese negocio. Si ese negocio guardó su propio token de Meta y el envío sale, la respuesta queda marcada como enviada y su estado es `own_number`. El token del canal en vivo se rechaza y no se usa. El número y el token se guardan cuando hay base; si la tabla todavía no existe, quedan en memoria y el canal en vivo sigue contestando. Al volver a cargar, la respuesta usa el rubro de ese negocio. Si no hay token o Meta falla, queda guardada en el negocio, no sale, y el canal del piloto no se usa. Esas respuestas se guardan cuando hay base; si la tabla todavía no existe, quedan en memoria. `connected` sigue siendo solo el canal de este proceso.

Rebanadas de esta fase:

1. **Claim** (memoria y Redis): el mismo `message_id` en otro tenant es nuevo; en el mismo, duplicado. Sin tenant, la clave de hoy.
2. **Buffer**: el mismo teléfono en otro tenant no mezcla el debounce. Sin tenant, la clave de hoy.
3. **Postgres**: `whatsapp_inbound_events` único por `(tenant_id, message_id)`, con RLS. Migración `048_whatsapp_inbound_tenant.sql`.
4. **Arranque**: `retain_catalog_skus` del piloto no borra el catálogo de otro tenant (RLS + test).
5. **Rubro y módulos**: columnas `industry` y `enabled_modules` en `tenants` (`049_tenant_industry_modules.sql`), leídas con el tenant del runtime. Sin UI.

## 3. Fuera

- Lienzo, nodos nuevos y aprovisionamiento (fases 2+).
- Segundo tenant en vivo.
- Deploy del piloto.
- Bus de eventos.
- Consola del operador (fase 4).

## 4. Cómo se prueba

- Memoria: dos tenants, mismo `message_id` / mismo teléfono, sin mezcla.
- Postgres (con `FACTORY_OS_TEST_DATABASE_URL`): claim por tenant; retain del piloto no toca al otro.
- Memoria: `TenantConfig` distinto por tenant.
