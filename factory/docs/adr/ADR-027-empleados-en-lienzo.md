# ADR-027 — Empleados del roster en el lienzo

**Estado:** aceptado (22/11/2026). Primer corte: colocar y asignar empleados del roster a módulos del negocio en el lienzo, sin billeteras ni tools libres.  
**Relación:** extiende [ADR-023](ADR-023-lienzo-con-barandas.md), [ADR-025](ADR-025-lienzo-con-react-flow.md) y [ADR-026](ADR-026-roster-empleados-por-tenant.md). No abre constructor libre de nodos ni de permisos financieros AgentOS.

---

## 1. Contexto

El lienzo solo mostraba módulos de negocio. El roster (empleados prederminados y clones) vivía en otra pestaña. El dueño no podía ver el equipo digital en el mapa del negocio, así que el lienzo no se sentía como fábrica de agentes.

## 2. Decisión

### Dos familias en el mismo mapa

| Familia | Origen | Qué hace en el lienzo |
| --- | --- | --- |
| Módulo | `NODE_CATALOG` | Capacidades del negocio (WhatsApp, Pedido, Cobros, …) |
| Empleado | Roster del tenant (ADR-026) | Quién atiende ese módulo; id `emp:{employee_key}` |

- Puerto nuevo: `equipo`. El empleado solo emite `equipo`; el módulo lo recibe.
- Un empleado solo se conecta a módulos permitidos por su `base_role` (`CANVAS_MODULES_BY_ROLE`). Nunca gana tools nuevas.
- Solo empleados **enabled** y no archivados entran a la paleta Equipo.
- Publicar sigue exigiendo `pedido` + `cobros` en los **módulos**. El equipo se guarda aparte (`team` en el mapa publicado).
- Deshabilitar un empleado después de publicarlo no inventa permisos; el turno no lo elige (ADR-026).

### Fuera de este corte

- Billeteras, AgentOS Identity como nodo, gasto libre, tools arbitrarias.
- Inventar nodos de negocio desde la UI.
- Aflojar `confirm_payment` o el camino canal → pedido → Cobros.

## 3. Runtime (primer corte)

El mapa publicado de módulos sigue gobernando el grafo de turno. Las asignaciones `team` orientan WHO: si hay un empleado asignado a un módulo del camino activo y está enabled, se prefiere ese `employee_key` (mapeado a su `base_role` para tools).

## 4. Cómo se prueba

Dominio: place/assign, puerto `equipo`, rechazo de módulo fuera del rol, rechazo de disabled, publish con `team`. API flow-map + publish. UI: paleta Equipo y nodo empleado. Eval: empleado en lienzo no confirma pagos; disabled no queda en equipo publicable.
