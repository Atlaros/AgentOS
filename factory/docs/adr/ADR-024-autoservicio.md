# ADR-024 — Autoservicio del cliente

**Estado:** aceptado (18/11/2026). Autoriza la fase 7 de [ADR-017](ADR-017-vision-y-alcance-factory-agent-os.md).
**Relación:** reutiliza [ADR-019](ADR-019-aprovisionamiento-desde-plantilla.md) sin sesión de operador.

---

## 1. Contexto

La fase 7 pide alta sin el operador. El aprovisionamiento ya crea el negocio; falta un camino público acotado.

## 2. Decisión

`POST /api/public/signup` crea un negocio desde plantilla `cafe` o `ropa`. Queda registrado en la consola del operador. La pantalla pública es `/signup` (proxy Next en `/api/public/signup`).

Está apagado por defecto (`public_signup_enabled=false`). Con el flag prendido exige una invitación de un solo uso, emitida por `POST /api/operator/invites` con sesión de panel (botón en `/operator`). Sin flag o sin invitación válida responde 403 y no crea el negocio ni el usuario del dueño. La invitación se gasta al crear el negocio. Cuando hay base, la invitación queda en `signup_invites` y sobrevive un reinicio; si la tabla todavía no existe, queda en memoria. El alta devuelve el correo y el secreto del dueño una sola vez; se guarda el hash. Cuando hay base, el hash queda en `business_owners` y el dueño puede volver a entrar después de un reinicio. Si la tabla todavía no existe, el hash queda en memoria. Cuando hay base, la sesión abierta queda en `owner_sessions` y sobrevive un reinicio; si la tabla todavía no existe, la sesión queda en memoria. Ese secreto no entra al panel del piloto. `POST /api/owner/login` abre una sesión de ese negocio y `GET /api/owner/business` devuelve solo ese negocio. `DELETE /api/owner/session` cierra esa sesión (también en `owner_sessions` cuando hay base). La misma sesión no abre conversaciones ni la consola del operador. La pantalla es `/owner`.

Cada IP puede crear como máximo `public_signup_max_per_window` negocios por ventana (`public_signup_window_s`, 5 por hora). Al superar el tope responde 429 y no gasta la invitación. Cuando hay base, el cupo queda en `signup_rate_hits` y sobrevive un reinicio; si la tabla todavía no existe, el cupo es de este proceso. Por defecto cuenta la IP del par TCP e ignora `X-Forwarded-For`. Con `trusted_proxy_hops=1` (el API solo se alcanza por ngrok u otro proxy que agrega ese encabezado) cuenta la IP que el proxy vio. Otra IP sigue pudiendo usar una invitación vigente.

Límites de esta rebanada:

- Sin cobro de suscripción.
- El dueño puede reservar un identificador de WhatsApp que no sea el del canal en vivo y guardar el token de Meta de ese negocio. El token del canal en vivo se rechaza. La respuesta sale solo con el token y el número de ese negocio, y el estado de ese negocio pasa a `own_number`. El dueño ve si esa respuesta salió. Sin token, o si Meta falla, el mensaje queda guardado en el negocio, el estado sigue `not_connected` y no entra al piloto. `connected` sigue siendo solo el canal en vivo.
- Sin DNS.
- Captcha sigue fuera.
- `trusted_proxy_hops` queda en 0 hasta que el proceso escuche solo detrás del proxy. Si se prende y el API es público, el cliente puede inventar la IP.

## 3. Fuera

- Deploy del piloto.
- Sustituir el tenant vivo del piloto.
