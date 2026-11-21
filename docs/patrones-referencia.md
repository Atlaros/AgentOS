# Patrones de referencia (extracción selectiva)

**Regla:** estudiar y reimplementar. **No** copiar módulos, migraciones ni dependencias.

Procedencia = Factory Agent OS (`Factory-Agent-OS-next`), solo como referencia conceptual.

| Patrón AgentOS | Qué aprender | Procedencia aproximada (Factory) | Qué NO copiar |
| --- | --- | --- | --- |
| RLS por organización | `SET LOCAL app.organization_id`; policies `USING`/`WITH CHECK`; rol app sin `BYPASSRLS` | `migrations/versions/002_rls.sql`, conexión con tenant | Schema `tenants` de comercio, 60 migraciones |
| Autorización + autonomía | Capas: permiso tipado → policy → piso humano no relajable por el dueño más allá del floor | `AutonomyFloor`, policies de write, ADR autonomía | Skills como permiso; guion de venta |
| Ports de pago | Interface abstracta; Fake en tests; adapter real aparte | Puertos Cobros / payment adapters | Baneco asumido; webhooks Meta |
| Idempotencia | Clave de idempotencia en writes; replay seguro | Dedup / idempotency keys en writes | Redis como fuente de verdad de negocio |
| Audit / journal | Append-only de hechos de ops; refs externas | Journal / asientos (idea) | Contabilidad gerencial café; plan de cuentas comercial |
| Secrets fuera del prompt/DB | Credenciales solo en env/secret store | Invariante “no DATABASE_URL al LLM” | Cualquier prompt o graph |
| Tests con Fake | Unit sin red/Docker; integration opt-in | `MODEL_PROVIDER=fake`, Fake adapters | Catálogo Closet/café |

## Artefactos a producir en el repo nuevo (no en Factory)

1. `docs/patterns/rls.md` — diagrama + checklist de tests cross-org.
2. `docs/patterns/policy-engine.md` — modelo de decisión (allow / deny / require_human).
3. `packages/adapters/README.md` — contrato `NetworkAdapter`.
4. Golden tests: “cross-org = 0”, “sin policy no transfer”, “idempotent replay”.

## Checklist anti-copia

- [ ] Ningún `from factory_os…`
- [ ] Ninguna migración numerada reusada
- [ ] Ninguna dependencia LangGraph / Meta / Next del panel Factory
- [ ] Ledger con entidades wallet/asset/tx, no `orders`/`stock`
