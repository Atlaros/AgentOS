# ADR-022 — Catálogo de procesos y diagnóstico guiado

**Estado:** aceptado (18/11/2026). Autoriza la fase 5 de [ADR-017](ADR-017-vision-y-alcance-factory-agent-os.md).
**Relación:** procesos por rubro sobre las plantillas de [ADR-019](ADR-019-aprovisionamiento-desde-plantilla.md). No es process mining automático.

---

## 1. Contexto

La fase 5 pide un catálogo de procesos por rubro y un diagnóstico guiado por el operador, con evidencia y huecos declarados.

## 2. Decisión

Un catálogo estático por plantilla (`cafe`, `ropa`) lista procesos del negocio (venta por WhatsApp, cobro QR, mostrador, reposición, etc.).

El diagnóstico recibe el rubro y los módulos activos del tenant. Devuelve:

- **cubierto**: el proceso tiene todos los módulos que necesita.
- **parcial**: falta algún módulo; se nombra el hueco.
- **hueco**: el proceso no se puede operar aún.

No se inventan procesos desde logs. El operador elige el rubro y lee el informe en `/operator`, debajo de la lista de negocios.

## 3. Fuera

- Lienzo editable (fase 6).
- Descubrimiento automático sin entrevista.
