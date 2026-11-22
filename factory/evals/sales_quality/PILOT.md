# Piloto WhatsApp (T16) — checklist

Fase 2 automatizada (T14–T15) ya midió el corpus FakeGateway. El piloto real necesita al **owner** en el número de prueba.

## Antes

1. Stack: `docker compose up -d` (api :8000, db, redis).
2. Túnel: `./scripts/ngrok_pilot.sh` (no levantar otro proceso en `:8000` ni otro túnel).
3. `CATALOG_SEED=closet` + pay_test; migraciones hasta `009`.
4. `MODEL_PROVIDER` con Gemini/OpenRouter/Groq (no `fake`).

## Durante

Para cada falla nueva anotar:

| Campo | Ejemplo |
| --- | --- |
| Failure id | F11 |
| Texto cliente | turnos en orden |
| Respuesta Adri | pegar tal cual |
| Qué esperabas | sin re-saludo / respeta presupuesto / … |

## Después → golden

```bash
.venv/bin/python scripts/append_sales_golden.py \
  --failure F11 \
  --id sq_26_f11_descripcion_corta \
  --customer 'mensaje del cliente' \
  --must-not '¡Hola!' \
  --checks no_repeat_list,address_tu \
  --reply 'respuesta observada'
.venv/bin/pytest -q evals/test_sales_quality.py
```

Usar `--dry-run` primero. No meter secretos ni números reales de clientes en el corpus.

## Hecho cuando

- Al menos una sesión piloto con el owner.
- Fallas nuevas convertidas en casos del corpus (o documentadas como no-repro).
- `docs/00` fila Adri actualizada.
