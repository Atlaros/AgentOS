# Tenant employee roster + clones

**Objective:** Per-business digital employee list from the catalog (enable/rename/style) plus clones of a base role, without freeform tools. Lab only.  
**Branch:** `feat/tenant-employee-roster`  
**Delivery:** ask-on-risk  
**Runner:** `FACTORY_OS_TEST_DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:5434/factory_os_test .venv/bin/pytest -q` + focused evals

## Specs

- **S1** User: "el tener predetermiando y la opcion de crar los suyos"
- **S2** User: "Ambos" for A (catalog roster: enable/disable, name/style, autonomy) and B (create own as clones of a base role, not freeform tools)
- **S3** User: production = "A) Lab local / deploy nuevo de Factory, sin tocar el Supabase ni el Render de la cafetería viva."
- **S4** Plan: `sales` and `collections` cannot be disabled; Coordinador is not in the roster; clone permissions ⊆ base role; skills never grant tools.
- **S5** Plan: provision seeds catalog rows; choose_employee skips disabled; operator/owner API+UI; evals for disabled employee; soft-archive clones.
- **S6** Plan: finish café sync T5 smoke Factory↔AgentOS locally; lab runbook; never live café.

## Tasks

| ID | Specs | Route | Status |
| --- | --- | --- | --- |
| T0 | S1-S4 | inline | done — ADR-026 + 00/02 |
| T1 | S4-S5 | inline | done — migration 063 + domain A |
| T2 | S4-S5 | inline | done — choose_employee + roster constrain |
| T3 | S5 | inline | done — operator/owner API+UI A |
| T4 | S5 | inline | done — evals A (`evals/test_employee_roster.py`) |
| T5 | S1-S2,S4-S5 | inline | done — clones B + WHO context + UI create/archive |
| T6 | S3,S6 | inline | done — smoke `scripts/smoke_factory_agentos_lab.py` lab_smoke_ok; `docs/lab-production-like.md` |

## Log

- **L1** 2026-11-22 User chose both catalog roster and clones (clones = base_role only), lab production only. Plan: employee_roster_deep. Implement with Gentle AI, ODD, TDD, evals.
- **L2** 2026-11-22 A+B green: domain, WHO filter, API, UI, evals. Live smoke Factory→AgentOS: customer text no settlement; adapter confirm posts; idempotent replay 200. Cafetería viva untouched.
