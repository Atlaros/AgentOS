# ADR-021 — Consola del operador

**Estado:** aceptado (18/11/2026). Autoriza la fase 4 de [ADR-017](ADR-017-vision-y-alcance-factory-agent-os.md).
**Relación:** lista negocios creados por [ADR-019](ADR-019-aprovisionamiento-desde-plantilla.md). No es el panel del dueño del piloto.

---

## 1. Contexto

La fase 4 pide una consola del operador: negocios, módulos activos, versiones, costos y estado de WhatsApp, sin tocar la base a mano.

## 2. Decisión

Primera rebanada:

- Un registro de negocios aprovisionados. Sin base, queda en memoria del proceso. Con `database_runtime_url`, la consola lee `tenants` (nombre, rubro, módulos). Reiniciar el proceso no borra esa lista.
- `GET /api/operator/businesses` con autenticación de panel (`require_human`).
- `POST /api/operator/businesses` crea un negocio desde plantilla sin alta pública.
- Una página `/operator` en el panel que lista id, nombre, rubro y módulos, y permite aprovisionar.

El alta pública, cuando hay base de runtime, escribe el mismo tenant. WhatsApp queda `connected` solo en el negocio que atiende el canal de Meta de este proceso. Un negocio con su propio número y token queda `own_number`. El resto queda `not_connected`. La versión es `published` si ese negocio tiene una regla publicada, y `draft` si no. El costo queda en null hasta que ese negocio acumule tokens del modelo; entonces muestra el total (por ejemplo `42 tokens`). Cuando hay base, el total queda en `model_usage` y sobrevive un reinicio; si la tabla todavía no existe, el total queda en memoria. La tabla `tenants` no tiene RLS; el listado es solo para quien ya entró al panel.

## 3. Fuera

- Autoservicio del cliente (fase 7).
- Lienzo (fase 6).
- Sustituir el nav del dueño del piloto por multi-tenant vivo.
