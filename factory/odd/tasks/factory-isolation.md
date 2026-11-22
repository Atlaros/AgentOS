# Factory isolation

Fase 1 de ADR-017, decidida en ADR-018. Rama `factory/phase-1-isolation`. Entrega `stacked-to-main`. Runner: `.venv/bin/pytest -q tests/test_whatsapp_dedup.py tests/test_inbound_buffer.py tests/test_tenant_config.py`.

Pronóstico de la fase: por encima de 400 líneas. Commits por rebanada de riesgo / ~400 líneas. Sin push hasta pedido explícito.

## Specs

S1. El owner pidió, textual: "si el ard esta proijo y con beunas practicas, empieza con la impletacion, ya sabes usando od, gentle ia tdd evalcuaiones apra codigo de calidad. pero antes de emepzar actulzia gntle ia."

S2. ADR-017, fase 1, textual: "Aislamiento: tablas, RLS, Redis, archivos, canales y herramientas. Rubro y módulos como datos de un tenant. El arranque no modifica datos de negocio." Resultado: "Suite de dos negocios en prueba, con cero fugas. Sin segundo tenant en vivo."

S3. Claim WhatsApp por tenant en memoria y Redis. Sin tenant, clave de hoy. Postgres fuera de esta rebanada original; luego entró en T3.

S4. Buffer WhatsApp por tenant. Mismo teléfono, dos negocios, no se mezclan.

S5. Postgres `whatsapp_inbound_events` único por `(tenant_id, message_id)` + RLS.

S6. Retain del piloto no borra productos de otro tenant.

S7. Rubro y módulos como datos del tenant, sin UI.

S8. Owner 18/11/2026: implementar las 7 fases en código sin freno de cliente real; entrega `stacked-to-main`.

## Tasks

- [x] T1 — ADR-018 y punteros. Cubre S1-S2. Inline.
- [x] T2 — claim memoria/Redis. Cubre S3. RED luego GREEN (5 passed). Risk: item 2.
- [x] T3 — buffer por tenant + wire en main. Cubre S4. RED TypeError luego GREEN. Risk: item 2.
- [x] T4 — migración 048 + PostgresInboundDeduper. Cubre S5. Test skip sin DB. Risk: item 1+2.
- [x] T5 — test retain cross-tenant. Cubre S6. Skip sin DB. Risk: item 6 cubierto por test.
- [x] T6 — industry/modules + migración 049. Cubre S7. GREEN memoria. Risk: item 1 (migración).
- [x] T7 — enmienda ADR-017 (sin cliente real; stacked-to-main). Cubre S8.

## Log

L1. 2026-11-18. "si el ard esta proijo y con beunas practicas, empieza con la impletacion..."

L2. Gentle AI 4.5.0, Engram 3.7.2. ADR-017 aceptado. Fase 1 no lienzo.

L3. T2 RED/GREEN claim. Verifier 5 passed.

L4. Owner: código de las 7 fases sin freno de cliente real; `stacked-to-main`.

L5. T3–T7 implementados. Focused: 10 passed, 2 skipped (sin FACTORY_OS_TEST_DATABASE_URL).
