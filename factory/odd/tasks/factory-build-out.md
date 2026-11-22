# Factory build-out

Cerrar lo que quedó a medias de ADR-017, en la rama `factory/phase-1-isolation`. Entrega local, sin push. El café en vivo no se toca. Runner: `.venv/bin/pytest -q`.

## Specs

S1. Pedido del owner, textual: "sigue contruyendo todo, ahciend test y evalcuaicon suando gnelte ia odd y tdd".

S2. La autonomía manda de verdad. Confirmar un pago a mano queda bloqueado. Apretar el piso de stock a «nunca» bloquea el ajuste aunque venga confirmado. El piso de la plantilla sigue pidiendo confirmación para ajustar stock.

S3. Una regla tiene versiones: publicar guarda una versión, y se puede volver a una versión anterior. Una versión no puede confirmar un pago.

S4. El lienzo une puertos del mismo tipo. Un puerto distinto no conecta. Pedido y Cobros siguen bloqueados.

S5. El alta crea el usuario del dueño de ese negocio. Sin flag o sin invitación no crea ni el negocio ni el usuario. El secreto sale una sola vez.

S6. WhatsApp queda asociado al negocio. El canal de Meta de este proceso sigue siendo el del piloto.

S7. El café que ya corre se deja quieto. Sin aplicar migraciones en su base y sin reiniciar su proceso.

## Tasks

- [x] T1 — S2. La autonomía frena la tool. Route: inline. RED ImportError AutonomyDenied. GREEN tests/test_autonomy_enforcement.py, test_employees.py, evals/test_cafe_golden.py. Risk: item 2 (autorización de tools). Commit: 5df0ce9.
- [x] T2 — S3. Versiones de una regla en memoria. Route: inline. RED ImportError revert_rule. GREEN tests/test_flow_canvas.py. Risk: none. Commit: d7b9bb3.
- [x] T3 — S4. Conexión de puertos en el dominio. La pantalla sigue sin arrastrar nodos. Route: inline. RED ImportError connect_modules. GREEN tests/test_flow_canvas.py. Risk: none. Commit: d7b9bb3.
- [x] T4 — S5. El alta crea el dueño y el panel del piloto lo rechaza. Route: inline. RED ModuleNotFoundError business_owners. GREEN tests/test_public_signup.py. Risk: item 2 (credencial nueva, alta sigue apagada). Commit: 55b4adb.
- [x] T5 — S6. WhatsApp del canal vivo sigue siendo el piloto; el otro negocio queda not_connected. Ya cubierto por test_live_whatsapp_and_published_rule_show_on_the_console. Risk: none.
- [x] T6 — S3 y S4 en la pantalla. Conectar un puerto y volver una versión. RED 404 en `/api/operator/connections`. GREEN tests/test_flow_canvas.py, evals cafe y template exit. Lo vi en el navegador. Risk: none. Commit: 42c6cf4.
- [x] T7 — Arrastrar un módulo sobre otro usa el puerto elegido y el mismo freno. Lo vi en la pantalla: WhatsApp sobre Cobros queda trabado; Cobros sobre Caja pasa. GREEN tests/test_flow_canvas.py, evals cafe y template exit. Risk: none. Commit: 956985a.
- [x] T8 — S3. La versión publicada queda en `catalog_rule_versions` y se puede restaurar con base. Route: inline. El test de Postgres se salta sin `FACTORY_OS_TEST_DATABASE_URL`. Risk: item 1 (tabla nueva, no aplicada al café). Commit: 975ebc0.
- [x] T9 — S5. El dueño entra a su negocio en `/owner`. La sesión no abre el panel del piloto. Route: inline. RED 404 en `/api/owner/login`. GREEN tests/test_public_signup.py. Risk: item 2 (sesión nueva, el piloto sigue con 401). Commit: 61715bc.
- [x] T10 — S6. El dueño reserva un identificador de WhatsApp que no es el del canal en vivo. Ese mensaje no entra al piloto. Route: inline. RED 404 en `/api/owner/whatsapp`. GREEN tests/test_owner_whatsapp.py y tests/test_channel.py. Risk: item 2 (el webhook ignora solo un número reservado por otro negocio). Commit: 6842083.
- [x] T11 — S6. El número reservado contesta en su negocio. La respuesta no sale por el canal del piloto. Route: inline. RED 404 en `/api/owner/messages`. GREEN tests/test_owner_whatsapp.py y tests/test_channel.py. Risk: item 2 (el webhook ahora corre un turno en otra tienda en memoria). Commit: f31cd98.
- [x] T12 — S6. Con el token de ese negocio, la respuesta sale por Meta con ese número. El token del canal en vivo se rechaza. Route: inline. RED 200 en vez de 409 al guardar el token del piloto. GREEN tests/test_owner_whatsapp.py. Risk: item 2 (token de Meta en memoria del proceso, no es el del café). Commit: dfb7eec.
- [x] T13 — S6. Con número y token propios el estado es `own_number`. El piloto sigue `connected`. Sin token sigue `not_connected`. Route: inline. RED `not_connected` en vez de `own_number`. GREEN tests/test_owner_whatsapp.py y tests/test_operator_console.py. Risk: none. Commit: 25b5a12.
- [x] T14 — S6. Cada respuesta reservada dice si salió. Sin token o si Meta falla, `delivered` es false. Con envío exitoso, true. El piloto no la envía. Route: inline. RED KeyError `delivered`. GREEN tests/test_owner_whatsapp.py. Risk: none. Commit: 151fbd1.
- [x] T15 — S6. El número y el token sobreviven un reinicio de memoria cuando hay base. Si la tabla no existe, quedan en memoria y no se corta el canal. Route: inline. RED TypeError `url` e ImportError `load_business_channels`. GREEN tests/test_owner_whatsapp.py. El test de Postgres se salta sin `FACTORY_OS_TEST_DATABASE_URL`. La migración 052 no se aplicó al café. Risk: item 1 (tabla nueva) e item 2 (el token de ese negocio queda en la tabla). Commit: 222490c.
- [x] T16 — S6. Al recargar el número, la respuesta usa el rubro de ese negocio. Route: inline. RED saludo «Del Campus Café» para una tienda de ropa. GREEN tests/test_owner_whatsapp.py. Risk: none. Commit: 06ad315.
- [x] T17 — S5. El hash del dueño sobrevive un reinicio de memoria cuando hay base. Si la tabla no existe, queda en memoria. La sesión abierta sigue en memoria. Route: inline. RED TypeError `url` en `issue_business_owner`. GREEN tests/test_public_signup.py. El test de Postgres se salta sin `FACTORY_OS_TEST_DATABASE_URL`. La migración 053 no se aplicó al café. Risk: item 1 (tabla nueva) e item 2 (credencial del dueño). Commit: f0fb999.
- [x] T18 — S6. Las respuestas reservadas sobreviven un reinicio de memoria cuando hay base. Si la tabla no existe, quedan en memoria. Route: inline. RED TypeError `url` en `answer_reserved`. GREEN tests/test_owner_whatsapp.py. El test de Postgres se salta sin `FACTORY_OS_TEST_DATABASE_URL`. La migración 054 no se aplicó al café. Risk: item 1 (tabla nueva). Commit: 82f8617.
- [x] T19 — S5. La invitación de un solo uso sobrevive un reinicio de memoria cuando hay base. Si la tabla no existe, queda en memoria. Route: inline. RED TypeError `url` en `issue_invite`. GREEN tests/test_public_signup.py. El test de Postgres se salta sin `FACTORY_OS_TEST_DATABASE_URL`. La migración 055 no se aplicó al café. Risk: item 1 (tabla nueva) e item 2 (código de alta). Commit: e915450.
- [x] T20 — S5. El cupo por IP del alta sobrevive un reinicio de memoria cuando hay base. Si la tabla no existe, queda en memoria. Route: inline. RED TypeError `url` en `signup_slot_open`. GREEN tests/test_public_signup.py. El test de Postgres se salta sin `FACTORY_OS_TEST_DATABASE_URL`. La migración 056 no se aplicó al café. Risk: item 1 (tabla nueva) e item 2 (tope del alta pública). Commit: 879471b.
- [x] T21 — S5. La sesión abierta del dueño sobrevive un reinicio de memoria cuando hay base. Si la tabla no existe, queda en memoria. Route: inline. RED: tras `clear_business_owners` la sesión no reaparece. GREEN tests/test_public_signup.py. El test de Postgres se salta sin `FACTORY_OS_TEST_DATABASE_URL`. La migración 057 no se aplicó al café. Risk: item 1 (tabla nueva) e item 2 (token de sesión del dueño). Commit: c064f1d.
- [x] T22 — S1 / fase 4. La consola muestra el gasto del modelo por negocio cuando hubo tokens. Sin uso sigue null. Route: inline. RED: cost sigue null tras `record_model_tokens`. GREEN tests/test_operator_console.py. Solo memoria en este corte. Risk: none. Commit: 7862f85.
- [x] T23 — S1 / fase 4. El total de tokens por negocio sobrevive un reinicio de memoria cuando hay base. Si la tabla no existe, queda en memoria. Route: inline. RED TypeError `url` en `record_model_tokens`. GREEN tests/test_operator_console.py. El test de Postgres se salta sin `FACTORY_OS_TEST_DATABASE_URL`. La migración 058 no se aplicó al café. Risk: item 1 (tabla nueva). Commit: fdcb8aa.
- [x] T24 — S5. El dueño cierra la sesión y ese token deja de abrir el negocio. Con base también se borra de `owner_sessions`. Route: inline. RED ImportError `close_owner_session`. GREEN tests/test_public_signup.py. Risk: item 2 (revoca el Bearer del dueño). Commit: a3d10c7.
- [x] T25 — S5. Hay pantalla `/signup` para el alta con invitación. Sin flag o sin invitación no crea. Route: inline. RED: no había ruta `/signup`. GREEN tests/test_public_signup.py + tsc. Risk: none. Commit: a8e8889.
- [x] T26 — S5. El operador emite una invitación desde `/operator` y ve el código una vez. Route: inline. RED: la consola no tenía control de invitaciones. GREEN tsc + API invites. Risk: none. Commit: 7c7f983.
- [x] T27 — S2. Un negocio puede apretar su autonomía por debajo del piso; no puede aflojarlo. El runtime usa ese mapa. Con base sobrevive en `tenant_autonomy`. Route: inline. RED ImportError `grants_for_tenant`. GREEN tests/test_autonomy_enforcement.py + test_operator_console. Risk: item 2 (autorización de tools) e item 1 (tabla nueva). Commit: fcf4149.
- [x] T28 — S2. En `/operator` se puede apretar la autonomía de un negocio. Route: inline. GREEN tsc. Risk: none. Commit: 9066013.
- [x] T29 — S2. El dueño del alta aprieta la autonomía de su negocio desde `/owner`. No puede aflojar el piso ni tocar otro negocio. Route: inline. RED 404 en `/api/owner/autonomy`. GREEN tests/test_public_signup.py + tsc. Risk: item 2 (autorización de tools). Commit: 85d0498.
- [x] T30 — S1 / fase 2+4. El operador crea un negocio desde plantilla en `/operator` sin alta pública. Route: inline. RED 405 en `POST /api/operator/businesses`. GREEN tests/test_operator_console.py + tsc. Risk: none. Commit: a5b325e.
- [x] T31 — S4 / fase 6. Al arrastrar un módulo solo se iluminan los destinos válidos para el puerto elegido. Route: inline. RED ImportError `compatible_targets`. GREEN tests/test_flow_canvas.py + tsc. Risk: none. Commit: c152327.
- [x] T32 — S4 / fase 6. Los módulos se posicionan en un lienzo 2D; el enlace va por el puerto y sigue iluminando solo destinos válidos. Route: inline. RED: el riel sigue siendo una lista vertical. GREEN tsc + tests/test_flow_canvas.py. Risk: none. Commit: 2face39.
- [x] T33 — S4 / fase 6. Hay paleta de módulos del catálogo; arrastrar uno al lienzo lo coloca sin inventar nodos fuera del catálogo. Route: inline. RED ImportError `palette_modules`. GREEN tests/test_flow_canvas.py + tsc. Risk: none. Commit: 5aca0d5.

## Log

L1. 2026-11-18. "sigue contruyendo todo, ahciend test y evalcuaicon suando gnelte ia odd y tdd"

L2. T1–T5 en código. El lienzo todavía no se arrastra en la pantalla. Las versiones de una regla con base no tienen tabla de historial. El dueño del alta no entra al panel del piloto.

L3. 2026-11-18. "sigue contuyenbdo, ve contruyendo y hacienlos los tesy evaluaciones,". T6: la pantalla prueba la conexión y vuelve la versión. El arrastre de nodos sigue fuera.

L4. 2026-11-18. "sigue contuyenbdo, ve contruyendo y hacienlos los tesy evaluaciones,". T7: el arrastre usa el puerto elegido. El historial de versiones con base sigue sin tabla.

L5. 2026-11-18. "continua construyendo". T8: migración 051 guarda cada publicación y el revert la restaura. No se aplicó a la base del café. Postgres local no estaba escuchando, así que el test de esa base se salta.

L6. 2026-11-18. "continua construyendo". T9: el dueño del alta entra a `/owner` y lee solo su negocio. El panel del piloto sigue en 401.

L7. 2026-11-18. "continua contruyendo". T10: el dueño reserva un identificador de WhatsApp distinto del canal en vivo. Ese mensaje no entra al piloto. El número del café sigue atendiendo.

L8. 2026-11-18. "contnua contruyendo". T11: el número reservado contesta en su tienda. El canal del piloto no envía esa respuesta.

L9. 2026-11-18. "continua contruyedno". T12: la respuesta sale por Meta con el token de ese negocio. El token del canal en vivo se rechaza.

L10. 2026-11-18. "continua". T13: el negocio con número y token propios queda `own_number`. El canal del café sigue `connected`.

L11. 2026-11-18. "continua". T14: cada respuesta dice si salió. Sin token o si Meta falla, queda guardada.

L12. 2026-11-18. "continua contriyendo". T15: el número y el token se guardan en `business_whatsapp`. Si la tabla no está, siguen en memoria. No se aplicó al café.

L13. 2026-11-18. "q sigue? continua". T16: al recargar el número, la respuesta usa el rubro de ese negocio.

L14. 2026-11-18. "continua contruyendo". T17: el hash del dueño se guarda en `business_owners`. Si la tabla no está, sigue en memoria. La sesión abierta no se guarda.

L15. 2026-11-18. "continua, no se esta sguein el plan? o que se esta sigueindo para contruir  la ptaforma?". T18: las respuestas reservadas se guardan en `business_reserved_replies`. El plan sigue siendo ADR-017 (7 fases); este tramo cierra agujeros de la fase 7.

L16. 2026-11-18. "me sale el boton paln cerca del chat, sige contruyendo". T19: la invitación se guarda en `signup_invites`. El botón Plan de Cursor no cambia el flujo: se sigue con ODD.

L17. 2026-11-18. "continua". T20: el cupo por IP del alta se guarda en `signup_rate_hits`.

L18. 2026-11-18. "continua". T21: la sesión abierta del dueño se guarda en `owner_sessions`.

L19. 2026-11-18. "continua". T22: la consola muestra tokens del modelo por negocio.

L20. 2026-11-18. "continua". T23: el total de tokens se guarda en `model_usage`.

L21. 2026-11-18. "continua". T24: el dueño cierra la sesión. T25: pantalla `/signup`.

L22. 2026-11-18. "continua". T26: el operador emite la invitación desde la consola.

L23. 2026-11-18. "continuara". T27: autonomía por negocio apretada y persistida.

L24. 2026-11-18. "continuara". T28: panel para apretar autonomía en la consola.

L25. 2026-11-19. "continua contruyebdo". T29: el dueño aprieta autonomía en `/owner`.

L26. 2026-11-19. "continua contruyebdo". T30: el operador aprovisiona desde la consola.

L27. 2026-11-19. "continua contruyebdo". T31: al arrastrar solo se iluminan destinos válidos.

L28. 2026-11-19. "continua contruyebdo". T32: lienzo 2D con posiciones y asa Link.

L29. 2026-11-19. "continua contruyebdo". T33: paleta del catálogo en el lienzo.
