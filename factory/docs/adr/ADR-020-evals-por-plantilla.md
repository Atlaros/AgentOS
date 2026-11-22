# ADR-020 — Evals por plantilla

**Estado:** aceptado (18/11/2026). Autoriza la fase 3 de [ADR-017](ADR-017-vision-y-alcance-factory-agent-os.md).
**Relación:** usa el aislamiento de [ADR-018](ADR-018-aislamiento-de-negocios.md) y las plantillas de [ADR-019](ADR-019-aprovisionamiento-desde-plantilla.md). No adelanta el deploy del piloto.

---

## 1. Contexto

La fase 3 pide: evals por plantilla y lista de salida. Una mejora del núcleo no debe romper un rubro ya probado. Closet ya tiene golden y corpus de ventas. Café no tenía una lista de salida propia.

## 2. Decisión

Cada plantilla (`ropa` / Closet, `cafe`) tiene:

- Un **golden** de punta a punta en `evals/`.
- Una **lista de salida** (`evals/template_exit.py`) con los tests que deben pasar antes de dar la plantilla por lista.

El runner de sales-quality puede cargar el catálogo de la plantilla (`make_eval_shop(industry=...)`). Por defecto sigue Closet, para no romper el corpus actual.

El texto del cliente no confirma el pago en ninguna plantilla.

## 3. Fuera

- Consola, lienzo y autoservicio.
- Sustituir el corpus de Closet por uno de café en esta fase.

## 4. Cómo se prueba

`evals/test_closet_golden.py` sigue verde. `evals/test_cafe_golden.py` cubre búsqueda y pago. `evals/test_template_exit.py` exige que la lista de salida de cada plantilla exista y apunte a tests reales.
