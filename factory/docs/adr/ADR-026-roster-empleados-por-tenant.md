# ADR-026 — Roster de empleados por tenant y clones

**Estado:** aceptado (22/11/2026). Cumple la enmienda de ADR-005 en [ADR-017](ADR-017-vision-y-alcance-factory-agent-os.md) §8 (“agregar empleado digital desde la UI”), sin constructor libre de tools.
**Relación:** usa el catálogo de [`employees.py`](../../packages/contracts/factory_os/contracts/employees.py), el aprovisionamiento de [ADR-019](ADR-019-aprovisionamiento-desde-plantilla.md) y la autonomía de plantilla. No toca el deploy del café vivo.

---

## 1. Contexto

El runtime ya tiene empleados fijos (Adri, Cobros, Ops, …). El dueño pedía plantilla predeterminada **y** poder tener una lista por empresa, más crear los suyos para tareas distintas, sin romper las barandas de plata y stock.

## 2. Decisión

### Catálogo vs roster

- **Catálogo (código):** `EMPLOYEE_REGISTRY`, `ROLE_PERMISSIONS`, BBE y skills. Quién puede existir y qué tools tiene.
- **Roster (datos por `tenant_id`):** filas en `tenant_employees`: `employee_key`, `base_role`, `display_name`, `style`, `enabled`, `is_clone`, `archived`.

Al aprovisionar un negocio se siembran las filas del catálogo con runtime (no el Coordinador). Un backfill idempotente siembra el piloto si faltan filas.

### Slice A — plantilla por negocio

- Activar / desactivar, renombrar y estilo por fila.
- **No se puede desactivar** `sales` ni `collections`: el camino WhatsApp → pedido → Cobros no puede quedar mudo.
- El Coordinador no entra al roster: no se clona ni se apaga.
- Autonomía sigue en `tenant_autonomy` (solo apretar el piso).

### Slice B — clones

- Crear empleado = clonar un `base_role` del catálogo. `POST` con `base_role` + `display_name` (+ `style` opcional).
- Permisos, BBE y skills = **solo** los del `base_role` (nunca un superconjunto). Skills no conceden permisos. No hay tools nuevas.
- Soft-delete de clones (`archived` + `enabled=false`). Las filas de plantilla no se borran.
- El turno mapea el clone al `EmployeeRole` base para tools; el nombre visible es `display_name`.

### Runtime

`choose_employee` / `constrain_role` solo eligen roles **enabled** del roster del tenant. Un rol apagado no atiende WhatsApp.

## 3. Fuera

- Constructor libre de roles o tools.
- Aflojar el piso de autonomía.
- Marketplace de agentes.
- Apuntar migraciones o arranque a la base o Render del café vivo.

## 4. Cómo se prueba

Tests de dominio (memory + Postgres de lab): seed al provisionar, disable de ops bloquea WHO, rename en identity, clone sin tools extra, sales/collections no se apagan. Evals café/ropa: empleado apagado no atiende; golden de pago intacto. Smoke local Factory + AgentOS; nunca la cafetería viva.
