# Factory published rules run

Las reglas publicadas reaccionan a hechos. Rama `factory/phase-1-isolation`. Entrega local. Runner: `.venv/bin/pytest -q`.

## Specs

S1. Pedido del owner, textual: "continua" sobre docs/00 ítem 3: "Las reglas publicadas corren."

S2. Una regla publicada `qr_pending` + umbral de horas + `notify_owner` avisa al dueño cuando hay QR pendientes viejos. No confirma pagos.

S3. Una regla publicada `stock_low` + `below_minimum` + `draft_purchase_order` crea un borrador de OC. No envía ni recibe sola.

S4. Un segundo corrido no duplica el mismo aviso ni el mismo borrador para los mismos hechos (idempotencia).

S5. `POST /api/rules/run` dispara la evaluación para el tenant del runtime (cron/operador).

## Tasks

- [x] T1 — S2–S4. `rule_runtime` + tests. Route: inline.
- [x] T2 — S5. Endpoint + test. Route: inline.
- [x] T3 — docs/00 + suite + commit. Route: inline. Commit: 0a17df5. 665 passed, 19 skipped.

## Log

L1. 2026-11-19. "continua"
