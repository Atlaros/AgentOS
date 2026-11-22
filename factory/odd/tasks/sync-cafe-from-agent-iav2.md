# Sync café pilot from Agent-IAv2 into Factory

**Objective:** Bring café demo pieces that Factory is missing from Agent-IAv2 (`a8bf47e`), without overwriting Factory-only canvas/operator/provision. Work stays in this repo.  
**Branch:** `feat/sync-cafe-from-agent-iav2`  
**Runner:** `FACTORY_OS_TEST_DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:5434/factory_os_test uv run pytest -q` (focused tests per slice)

## Specs

- **S1** User: "quiero traer de forma selectiva lo q no tiene factori de agent ia v2, mas q todo son cosas de la cafe yaq se va suar en el demo como cleinte real… en el repo de factori"
- **S2** Source tip: Agent-IAv2 `a8bf47e`. Destination: Factory `3b9f419` + this branch. No edits in Agent-IAv2.
- **S3** Never overwrite Factory-only surfaces: operator canvas, provision, rule_runtime published maps, isolation migrations `048`/`049` already in Factory.
- **S4** Panel-admin SQL from v2 (`048`/`049` there) lands as **`061`/`062`** here and is registered in `MIGRATION_FILES`.
- **S5** Café seed, product photos, panel UX (caja/ledger/reportes), admin/owner roles, and secret-reset UI are in scope for the demo client.
- **S8** User: "actuamente del codigoq se trae de agente ia hay un ui ux pero si no sirve apra loq es fctori no pasa nada o modifciamos mientras mas pulido y prolijos eel proecyto mejor". Café UI that fights Factory is dropped or adapted. Agent-IA login branding does not replace Factory chrome. Operator canvas stays.
- **S6** User: "no quiero dejar esto sin resolver, quiero tdd odd evaluones, Risk: item 5 (el arranque ahora se niega a migrar una base remota). Lo cubre tests/test_remote_db_guard.py. uqoeor se resulve no quiero q hagas haciendo trampa ok , no edjamoe estos risk tratemolo". Production startup migrates and does not seed or prune the catalog. Local and test still sync the pilot seed and prune. `FACTORY_ALLOW_REMOTE_DB` is not the control. Verify stays on local Docker Postgres. Do not run this branch against the live café.
- **S7** Assumption: Langfuse + Render cafe deploy wiring can come in a later slice after the local café panel runs.
- **S9** User: "voy salir por una hoas, quier q continuaes unificando, usndo genlte ia, tdd odd evaluiones corrige los risk no quiero risk q luego rompna algo, cuando vualq uero q estod terminado. tambien ve coenctado cona gentos ayudame a tanto este repo y agentos estos cabledo y lsito apra probar en lcoal como funciona todo, como sif uera producion."
- **S10** A local or test process refuses a remote database host before it migrates, seeds, or prunes. Loopback and the Compose service name `db` stay allowed. Production still migrates a remote host and does not rewrite or delete the catalog.
- **S11** After the payment adapter confirms, Factory posts one fiat settlement to the local AgentOS. `Idempotency-Key` is the `provider_ref`. Customer text does not post. Empty AgentOS config does nothing. A failed post does not undo the local confirmation. AgentOS records a ledger entry and does not create a wallet transfer.

## Tasks

| ID | Specs | Route | Status |
| --- | --- | --- | --- |
| T1 | S3-S4 | inline | done — 061/062 + MIGRATION_FILES |
| T2 | S5 | inline | done — API, settings, memory tests 3 passed |
| T3 | S5,S8 | inline | done — follow-up cards, report kicker, caja says Productos. `tsc --noEmit` clean |
| T4 | S5,S8 | inline | done — photos, café logo, seed 53. Agent-IA login brand skipped |
| T5 | S5-S6 | inline | done — focused tests green; live smoke via `scripts/smoke_factory_agentos_lab.py` (AgentOS :8080) |
| T6 | S9-S10 | inline | done — local/test refuses a dotted remote host. 14 guardrail tests passed |
| T7 | S9,S11 | inline | done — adapter confirm posts `/v1/fiat-settlements`. Café golden + settlement tests passed. Live smoke: customer text no post; adapter confirm + idempotent replay OK |

## Log

- **L1** 2026-11-21 User asked for a selective café bring from Agent-IAv2 into Factory (not into v2). Factory-only canvas/operator must stay. v2 migrations 048/049 collide with Factory isolation 048/049 → renumber to 061/062.
- **L2** T1 done: `061_panel_admin_and_job.sql`, `062_panel_admin_role.sql`, registered in `MIGRATION_FILES`. T2 started: `panel_access.py` admin helpers + `PanelUser.job_title`. Next: store/postgres/API + settings UI from v2 commit `8cae090`, without touching operator/canvas.
- **L3** 2026-11-21 User: "actuamente del codigoq se trae de agente ia hay un ui ux pero si no sirve apra loq es fctori no pasa nada o modifciamos mientras mas pulido y prolijos eel proecyto mejor".
- **L4** T2: `set_panel_user_secret`, job_title on store/postgres, owner/admin roles on `/api/panel/users`, settings reset form. `tests/test_panel_admin_roles.py` 3 passed. T4 started: 106 product photos, `del-campus-cafe.jpg`, café seed now 53 products (dropped banana-with-water). `agent-ia.jpg` not copied. T3 panel UX still open.
- **L5** 2026-11-21 User: continue the plan with TDD, not plan mode. RED then GREEN: overdue payment without order labels `provider_ref` / `Sin cliente` (`tests/test_reports_followup.py`). RED import then GREEN: private media cache + 304 (`tests/test_media_cache_headers.py`, `media.py`, `GET /api/media`). Focused run: 20 passed (`test_media_cache_headers`, `test_reports_followup`, `test_catalog_cafe`, `test_panel_admin_roles`). Caja/ledger screen port and local smoke still open.
- **L6** 2026-11-21 User: correct risks so production does not break. First response blocked remote migrate/prune with `FACTORY_ALLOW_REMOTE_DB`. User rejected that as a cheat (see L7).
- **L7** 2026-11-21 User: "no quiero dejar esto sin resolver, quiero tdd odd evaluones, Risk: item 5 (el arranque ahora se niega a migrar una base remota). Lo cubre tests/test_remote_db_guard.py. uqoeor se resulve no quiero q hagas haciendo trampa ok , no edjamoe estos risk tratemolo". RED: production `get_shop` still called `retain_catalog_skus`. GREEN: production passes `sync_seed=False` and skips prune, seed, and `mark_sold` (that subtract exists only to undo a seed). Local still prunes and seeds. `assert_local_database` and `tests/test_remote_db_guard.py` removed. `tests/test_production_guardrails.py`: hosted open migrates only.
- **L8** 2026-11-21 User: "voy salir por una hoas, quier q continuaes unificando, usndo genlte ia, tdd odd evaluiones corrige los risk no quiero risk q luego rompna algo, cuando vualq uero q estod terminado. tambien ve coenctado cona gentos ayudame a tanto este repo y agentos estos cabledo y lsito apra probar en lcoal como funciona todo, como sif uera producion." RED then GREEN: local startup raises `local_remote_database_refused` before opening `db.example.com`; loopback and Compose host `db` stay allowed. Production still migrates without rewriting the catalog. Adapter confirm notifies AgentOS `POST /v1/fiat-settlements` with `Idempotency-Key` = `provider_ref`; customer text does not; a down AgentOS does not undo the confirm. Café golden 2 passed, settlement request 1 passed, guardrails 14 passed. AgentOS `tests/unit/test_fiat_settlement.py` 3 passed. Follow-up panel ported. `apps/web` `tsc --noEmit` clean. Two-process smoke not started.
- **L9** 2026-11-22 Live lab smoke observed: `scripts/smoke_factory_agentos_lab.py` against AgentOS `:8080` / Postgres `:5433`. Customer text no settlement; adapter confirm posts once; idempotent replay 200. Runbook: `docs/lab-production-like.md`. Live café untouched.
