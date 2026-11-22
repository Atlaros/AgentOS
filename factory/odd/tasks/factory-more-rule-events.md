# More published rule events

Close docs/00 item 3 — wire additional business events into rule_runtime. Branch `factory/phase-1-isolation`. Runner: `.venv/bin/pytest -q tests/test_rule_runtime.py`.

## Specs

S1. Pedido del owner: "continua con lo siguente en el orden" — ítem 3 (más eventos si el rubro pide).

S2. `payment_overdue` + `notify_owner` fires for `PaymentStatus.EXPIRED`, idempotent, never confirms payment.

S3. `customer_inactive` + `notify_owner` fires from inactive customer rows (tenant inactive_days / `days>N`), idempotent, notifies owner only (not customer reminders).

S4. docs/00 ítem 3 updated; `tests/test_rule_runtime.py` green.

## Tasks

- [x] T1 — S2–S3. RED→GREEN in rule_runtime. Route: inline. 7 passed.
- [x] T2 — S4 + commit. Route: inline.

## Log

L1. 2026-11-20. "continua con lo siguente en el orden"
L2. Added payment_overdue + customer_inactive → notify_owner; docs/00 item 3 closed.
