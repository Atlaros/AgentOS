# Empleados en el lienzo (Factory)

**Objective:** Place roster employees (catalog + clones) on the business canvas, assign them to modules via port `equipo`, publish team with the flow map. No free wallets/tools.  
**Branch:** `feat/tenant-employee-roster`  
**Delivery:** ask-on-risk  
**Runner:** `.venv/bin/pytest -q tests/test_canvas_employees.py tests/test_flow_canvas.py` + `cd apps/web && npm test -- --run app/operator`

## Specs

- **S1** User: "en el lienzoq los empelados o agentes q estan predterminados y los yo creare peudo suarlo en los flujos juntos con los nodos de mi negocio"
- **S2** User: "arranca" on first cut: place roster employees on canvas with business nodes — still without free wallets
- **S3** User: "no te eoviode manajear risk, odd, tdd evalauiones"
- **S4** Assumption: port `equipo`; assignments ⊆ `CANVAS_MODULES_BY_ROLE`; publish keeps `path_locked` for modules; team stored beside kinds; no AgentOS wallet nodes in this cut

## Tasks

| ID | Specs | Route | Status |
| --- | --- | --- | --- |
| T0 | S2-S4 | inline | done — ADR-027 + 00/02 |
| T1 | S1,S4 | inline | done — domain place/assign/publish team RED→GREEN |
| T2 | S1,S4 | inline | done — API flow-map employee_palette + publish team |
| T3 | S1-S2 | inline | done — React Flow Equipo palette + employee nodes |
| T4 | S3-S4 | inline | done — evals/test_canvas_team.py |

## Log

- **L1** 2026-11-22 User authorized first cut: employees on canvas with modules; ODD/TDD/evals; no free wallets. Verbatim prior ask in S1–S3.
- **L2** 2026-11-22 T0–T4 green: `tests/test_canvas_employees.py`, guards vitest, `evals/test_canvas_team.py`; migration `064_published_flow_team.sql`.
