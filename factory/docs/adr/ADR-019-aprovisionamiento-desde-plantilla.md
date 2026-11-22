# ADR-019 — Aprovisionamiento desde plantilla

**Estado:** aceptado (18/11/2026). Autoriza la fase 2 de [ADR-017](ADR-017-vision-y-alcance-factory-agent-os.md).
**Relación:** requiere el aislamiento de [ADR-018](ADR-018-aislamiento-de-negocios.md). No abre un segundo tenant en vivo. No adelanta el deploy del piloto.

---

## 1. Contexto

La fase 2 pide: un comando crea un negocio desde una plantilla, con permisos y autonomía por negocio. Hoy el proceso atiende un solo `PILOT_TENANT_ID` y el seed del catálogo exige que el JSON lleve ese mismo id.

## 2. Decisión

Un comando de aprovisionamiento crea un tenant nuevo desde la plantilla `cafe` o `ropa`. En la consola: `POST /api/operator/businesses` (panel en `/operator`):

- Genera un `tenant_id`.
- Escribe `industry` y `enabled_modules` en el tenant (ADR-018).
- Si hay base, siembra el catálogo de esa plantilla **como** ese tenant (el id del JSON no manda; manda el tenant creado).
- Permisos y autonomía por negocio quedan como datos del tenant. En la primera rebanada se fijan los módulos de la paleta compartida. La autonomía de plantilla declara el piso: confirmar un pago queda en «nunca»; el asiento y el stock piden aprobación; responder al cliente queda dentro de límites. El operador puede apretar un negocio con `POST /api/operator/autonomy` (y la consola lo muestra). El dueño del alta puede apretar el suyo con `POST /api/owner/autonomy` desde `/owner`. No se puede aflojar ese piso. Cuando hay base, el apriete queda en `tenant_autonomy`. `ToolRuntime` aplica el mapa efectivo del tenant: un pago confirmado a mano se niega, y un ajuste de stock apretado a «nunca» no corre aunque venga confirmado.

El piloto sigue siendo el negocio vivo. El comando no lo reemplaza ni toca su WhatsApp.

## 3. Fuera

- Consola del operador (fase 4).
- Lienzo (fase 6).
- Autoservicio (fase 7).
- Segundo número de WhatsApp en producción.

## 4. Cómo se prueba

Sin base: el comando en memoria crea un tenant con `industry` y módulos de la plantilla. Con base de prueba: el catálogo del nuevo tenant no es el del piloto.
