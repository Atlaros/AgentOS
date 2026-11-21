# ADR-001 — Estrategia de extracción

**Estado:** propuesto (pendiente aprobación)  
**Fecha:** 2026-11-20

## Contexto

AgentOS nace a partir de una auditoría de Factory Agent OS. No debe convertirse en un fork que arrastre WhatsApp, LangGraph, lienzo ni comercio.

## Decisión propuesta

**Alternativa B: repositorio nuevo + extracción selectiva de patrones + reconstrucción del dominio financiero.**

- No clonar Factory para “borrar lo que sobra”.
- No modificar Factory ni Agent-IA V2.
- No copiar las ~60 migraciones de comercio.
- Estudiar patrones (RLS, autonomía, puertos de pago, idempotencia) y reimplementarlos en el dominio AgentOS.

## Consecuencias

- Más trabajo inicial de scaffolding.
- Independencia real de producto, deploy y schema.
- Factory/Agent-IA quedan como futuros *consumidores*, no como dependencias.

## Alternativas rechazadas

- **A Fork + delete:** velocidad falsa; deuda y acoplamiento.
- **C Monolito derivado en el mismo árbol:** riesgo de seguir siendo Factory.
