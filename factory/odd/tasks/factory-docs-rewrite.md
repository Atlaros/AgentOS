# Factory docs rewrite

Reescribir toda la documentación para que describa Factory Agent OS (fábrica de agentes sobre el motor), no el roadmap del motor. Rama `factory/phase-1-isolation`. Cambio local, sin commit ni push hasta pedido del owner (AGENTS.md). Runner: revisión estructural + chequeo de links + `.venv/bin/pytest -q`.

## Specs

S1. Visión. Owner, textual: "la diea es fabrica de agentes para negocios empenderores, pyms y medanas empresas, permitirles crear flujo conn los nodos q tengamos, actualmetne tenemos dos engfocios apra empezar q es arpam cafeterias y rtenda de ropa pesnado en sesto tendremos nodos o modulos apra este rubros." `docs/00` abre con esa visión y el estado de las fases de Factory.

S2. El motor no es roadmap. Owner: "hay camboiar eso eso no es roap map". ADR-001 a ADR-016 pasan a un solo documento del motor: qué da cada módulo y qué invariantes respeta. El Deploy del piloto deja de figurar como paso actual o pendiente de este repo.

S3. Sacar lo que no aporta. Owner: "sacaremos loq no aporte a la contrucuion y tambien los doc de arutectu stac, en resumen toda la domentacion". Salen documentos que no ayudan a construir Factory. Quedan en el historial de git.

S4. Stack y arquitectura. Owner: "quedemos con next.js react y tpescript, me iamginoq api de python cierto? los agentes estaran contruido de langhp? o como sera su contrucion?". Panel y lienzo en Next.js + React + TypeScript; API Python/FastAPI; LangGraph solo para el turno de conversación, armado por negocio desde la configuración publicada. Dos planos: control (Factory) y ejecución (motor). Contrato de nodo como fuente única. Nodo del lienzo ≠ nodo de LangGraph.

S5. Método. Owner: "usamos gnelte ia? usamos solid? tdd? odd? evaluaciones? que skill ncestiamos? como esta el archivo agente?". Docs dicen: Gentle AI con ODD por defecto, TDD RED→GREEN, SOLID pragmático (SRP + DIP con puertos), evals en tres niveles (rubro, nodo, calidad de venta), skills por área. `AGENTS.md` reescrito como entrada corta.

S6. Lienzo con React Flow como ADR. Owner, textual: "aceotp el ard 25 haces commiot". ADR-025 aceptado.

S7. Sin links rotos dentro de `docs/`, `odd/`, `AGENTS.md`, `README.md` y la regla del proyecto.

## Tasks

- [x] T1 — Mapa del motor (ADR-001..016, 02, 03). Route: delegated explorer (Mapping trigger: 16 ADR + 2 docs exceden el presupuesto inline).
- [x] T2 — `docs/motor.md` + borrar ADR-001..016 + corregir referencias (ADR-000, 017, 018, render.yaml). Cubre S2, S3, S7. Route: inline. Commit: —.
- [x] T3 — `docs/00` visión + estado de fases + «Qué falta» verificado contra el código. Cubre S1, S2. Route: inline. Commit: —.
- [x] T4 — `docs/01`, `02`, `03` reescritos; niveles de autonomía y puertos citados con los nombres del código. Cubre S4, S5. Route: inline. Commit: —.
- [x] T5 — ADR-025 lienzo con React Flow (aceptado por el owner). Cubre S6. Route: inline. Commit: —.
- [x] T6 — `AGENTS.md`, `README.md`, regla del proyecto. Cubre S5. Route: inline. Commit: —.
- [x] T7 — `odd/README` solo Factory; borradas 78 tareas `v2-*`, `informe-prompts-y-draft`, `legacy-carry`. Cubre S3, S7. Route: inline. Commit: —.
- [x] T8 — Links: 25 archivos, 0 rotos. pytest: 650 passed, 19 skipped, 2 failed ajenos a docs. Skill registry: 64 skills. Cubre S7. Route: inline.

## Log

L1. 2026-11-19. "hay camboiar eso eso no es roap map, antes de nuevamente modifcir la doc quiero q me digas que estamos conturyendo cual es  vision ?? definemlo. tambine modifiqutdo la doc sacaremos loq no aporte a la contrucuion y tambien los doc de arutectu stac, en resumen toda la domentacion"

L2. 2026-11-19. "esta bien, la diea es fabrica de agentes para negocios empenderores, pyms y medanas empresas, permitirles crear flujo conn los nodos q tengamos, actualmetne tenemos dos engfocios apra empezar q es arpam cafeterias y rtenda de ropa pesnado en sesto tendremos nodos o modulos apra este rubros. como uquedaria el stack? arquitectura? diseño? usamos gnelte ia? usamos solid? tdd? odd? evaluaciones? que skill ncestiamos? como esta el archivo agente?"

L3. 2026-11-19. "y q tl seria astro?" → Astro no para panel/lienzo; solo para una web pública futura.

L4. 2026-11-19. "quedemos con next.js react y tpescript, me iamginoq api de python cierto? los agentes estaran contruido de langhp? o como sera su contrucion?"

L5. 2026-11-19. "arranca". Code docstrings citan ADR-003/004/009/010/011/012/015/016 como etiqueta: `docs/motor.md` conserva esos números como secciones para que sigan resolviendo.

L6. 2026-11-19. Hallazgos al verificar «Qué falta»: `TenantConfig.modules` no lo lee el panel ni los endpoints, y `/operator/flow` usa una lista fija; ninguna parte del runtime ejecuta las reglas publicadas; autonomía real = `never|recommend|approval|within_limits`; puertos = `pedido|pago_confirmado|aviso|aprobacion`.

L7. 2026-11-19. pytest: 2 fallos previos, ajenos a docs (el diff de código es solo el título de FastAPI y cabeceras de OpenRouter). `test_ledger_export_csv_and_pdf` espera 400 para `xlsx`, pero el export ya acepta `xlsx`. `test_manual_cash_order_persists_confirmed_payment_and_sold_variant` espera que la variante quede no disponible tras una venta en efectivo, pero con stock por cantidad la variante solo se apaga en cero. Quedan para una tarea aparte. Cierre: sin commit hasta pedido del owner.
