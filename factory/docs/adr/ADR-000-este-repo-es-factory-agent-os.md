# ADR-000 — Este repo es Factory Agent OS

**Estado:** aceptado (16/11/2026)

## Decisión

Esta carpeta es **Factory Agent OS**, la capa de plataforma de este checkout. El remoto `origin` es `https://github.com/Atlaros/Factory-Agent-OS-next`. En GitHub solo está `main`.

El número 000 evita chocar con la serie de la base. Esos archivos viven ahora en esta carpeta.

## Cómo se leen los ADR

Factory es la plataforma. ADR-001 a ADR-016 son las decisiones del motor (módulos, agentes y la cafetería), condensadas en [motor](../motor.md). No son el plan de Factory. El deploy de ese negocio no es trabajo de este repo.

Los ADR de Factory empiezan en [ADR-017](ADR-017-vision-y-alcance-factory-agent-os.md). Si Factory cambia una frase del legado, lo dice en un ADR propio y nombra la frase. No se borra el acta.

## Consecuencias

- El remote `origin` de esta carpeta es `Factory-Agent-OS-next`.
- `https://github.com/Atlaros/Factory-Agent-OS` es otro código (último push 2026-09-20). No se pisa con este árbol.
- La identidad de este checkout está en `AGENTS.md`, en la regla `.cursor/rules/00-project-core.mdc` y en la sección de identidad de `docs/00-vision-y-estado.md`.
- Un chat de este workspace no abre otra carpeta ni otro repo.
