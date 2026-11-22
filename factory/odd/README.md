# Tareas ODD

Cada cambio de Factory es una tarea `odd/tasks/<feature>.md`: specs con las palabras del owner, tareas con su ruta y su commit, y un log. El estado por fase está en [`docs/00-vision-y-estado.md`](../docs/00-vision-y-estado.md); el alcance, en [ADR-017](../docs/adr/ADR-017-vision-y-alcance-factory-agent-os.md).

Las tareas del motor (antes `v2-*`) salieron del repo; siguen en el historial de git. Lo que el motor da hoy está en [`docs/motor.md`](../docs/motor.md).

## Tareas

| Tarea | Fase | Estado |
| --- | --- | --- |
| [factory-isolation](tasks/factory-isolation.md) | 1 · aislamiento ([ADR-018](../docs/adr/ADR-018-aislamiento-de-negocios.md)) | cerrada |
| [factory-provisioning](tasks/factory-provisioning.md) | 2 · aprovisionamiento ([ADR-019](../docs/adr/ADR-019-aprovisionamiento-desde-plantilla.md)) | cerrada |
| [factory-template-evals](tasks/factory-template-evals.md) | 3 · evals por plantilla ([ADR-020](../docs/adr/ADR-020-evals-por-plantilla.md)) | cerrada |
| [factory-operator-console](tasks/factory-operator-console.md) | 4 · consola ([ADR-021](../docs/adr/ADR-021-consola-del-operador.md)) | cerrada |
| [factory-build-out](tasks/factory-build-out.md) | 4–7 · huecos de ADR-017: consola, procesos, lienzo, autoservicio | primeros cortes en código |
| [factory-docs-rewrite](tasks/factory-docs-rewrite.md) | documentación | en curso |

## Qué sigue

La lista de huecos está en [00 · Qué falta](../docs/00-vision-y-estado.md#qué-falta). Cada uno entra como tarea nueva con su test antes del código.

## Cómo se trabaja

- Gentle AI con ODD. SDD solo si el owner lo pide.
- Test primero: RED, luego GREEN. Un nodo nuevo trae sus tests de barandas y el eval del rubro.
- Entrega `stacked-to-main`, en commits de unidad de trabajo. Sin push hasta que el owner lo pida.
- El negocio vivo no se toca: no se aplican migraciones a su base ni se reinicia su proceso.
- Al cerrar una tarea, se actualiza la fila de la fase en 00 en el mismo cambio.

## Plantilla

```markdown
# <feature>

Objetivo en una línea. Rama, entrega y runner.

## Specs
S1. Pedido del owner, textual: "...".

## Tasks
- [ ] T1 — ... Cubre S1. Ruta: inline. Commit: —.

## Log
L1. Pedido original, textual.
```
