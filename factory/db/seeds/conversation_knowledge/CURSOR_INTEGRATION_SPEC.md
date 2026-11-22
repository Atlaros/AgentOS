# Cursor Integration Spec — Conversation RAG (Adri V2)

Este documento es para **Cursor**, en el repositorio existente de **Agent IA V2**. Describe cómo integrar el conocimiento generado en esta carpeta (`agent-v2-conversation-knowledge/`) al proyecto. **No asume la arquitectura interna del repo** — el primer bloque de trabajo es de inspección, no de implementación.

No implementar nada de código todavía sin haber completado el paso 1.

---

## Paso 1 — Inspeccionar el repositorio antes de tocar nada

Antes de escribir una sola línea de integración, respondé estas preguntas revisando el código real del repo:

1. **Catálogo/RAG actual**: ¿cómo está implementado hoy el Business RAG (catálogo, precios, stock, políticas)? ¿Qué base vectorial o motor de búsqueda usa, si usa alguno?
2. **Detección de intents**: ¿existe ya algún mecanismo de clasificación de intención o detección de situación conversacional? ¿Dónde vive en el código?
3. **Flujo actual del agente**: ¿cuál es el pipeline real hoy — recibe mensaje → ¿qué pasos ocurre antes de generar una respuesta?
4. **Dónde se toman las decisiones**: ¿hay un módulo de "reasoning" o de decisión de próxima acción, o la lógica está embebida directamente en el prompt del LLM?
5. **Herramientas existentes**: ¿qué tools/functions ya están definidas (consultar stock, crear pedido, escalar a humano, etc.)?
6. **Vector store existente**: ¿ya existe pgvector u otro vector store configurado? ¿Qué esquema de tablas/colecciones usa?
7. **Manejo de contexto conversacional**: ¿cómo se persiste el historial de la conversación hoy (memoria de sesión, base de datos, ventana de contexto del LLM)?
8. **Convenciones del repo**: estructura de carpetas, lenguaje/framework, convenciones de nombres de archivos y de commits.

Documentá brevemente las respuestas (puede ser un comentario en el PR o un archivo temporal) antes de seguir al paso 2.

## Paso 2 — Regla de integración

**No crear una arquitectura paralela si ya existe una equivalente.** Si el repo ya tiene:

- Un vector store → usar ese, no crear uno nuevo. Solo agregar una colección/namespace nueva para el Conversation RAG si el existente ya separa por dominio, o fusionar con criterio si no lo hace.
- Un mecanismo de detección de intents → extender su taxonomía con `02_bitext_intent_taxonomy.json` y los `situation` de `03_adri_business_patterns.json`, no reemplazarlo.
- Un módulo de decisión de próxima acción → conectar el Conversation RAG como una fuente de contexto más para ese módulo, no bifurcar la lógica.

## Paso 3 — Qué representa cada archivo para la integración

| Archivo | Rol en el sistema | Cómo debería usarse |
|---|---|---|
| `01_convrec_patterns.json` | Patrones generales de comportamiento conversacional + evidencia de qué funciona/no funciona | Indexar cada `pattern` como un chunk (usar el campo `metadata`); `experiment_insights` puede usarse como documentación interna, no necesariamente indexado |
| `02_bitext_intent_taxonomy.json` | Taxonomía de intents de soporte/venta | Base para el clasificador de intents, o como chunks recuperables por intent detectado |
| `03_adri_business_patterns.json` | Patrones específicos del flujo de venta de Adri | Núcleo del Conversation RAG — el más consultado en producción |
| `04_anti_patterns.json` | Guardrails de comportamiento | Debería inyectarse como reglas duras (system prompt / validación post-generación), no solo como resultado de una búsqueda semántica opcional |
| `conversation_knowledge_bundle.json` | Los cuatro anteriores consolidados | Útil para carga inicial en bulk o para tests; no reemplaza indexar cada componente por separado |

## Paso 4 — Flujo de integración conceptual

```text
                 CUSTOMER MESSAGE
                        │
                        ↓
              Situation / Intent
                        │
                        ↓
               Conversation RAG
                        │
                        ↓
             Conversation Pattern
                        │
                        ↓
                Agentic Reasoning
                   /          \
                  /            \
                 ↓              ↓
        Business RAG         Tools
        catálogo/FAQ        acciones
                 \              /
                  \            /
                   ↓          ↓
                     RESPONSE
```

El Conversation RAG entrega **conocimiento de comportamiento** (`agent_behavior`, `recommended_next_action`, `avoid`) al módulo de razonamiento. Nunca debe sustituir a las herramientas (tools) que consultan datos reales o ejecutan acciones — ver `anti_012` en `04_anti_patterns.json`.

## Paso 5 — Indexación en pgvector (si aplica)

Para cada componente, el campo `metadata` de cada registro (`source`, `domain`, `intent`, `situation`, `priority`, `version`) está pensado para mapearse directamente a columnas o a un campo `jsonb` de metadata en la tabla de embeddings existente, siguiendo el esquema que el repo ya tenga para el Business RAG. Sugerencia de contenido a embeder por chunk:

- Para patrones (`01`, `03`): concatenar `situation`/`intent` + `goal` + `customer_signals` + `agent_behavior`.
- Para intents (`02`): concatenar `intent` + `description` + `customer_signals`.
- Para anti-patrones (`04`): concatenar `name` + `description` + `rule`.

## Paso 6 — Qué NO hacer en esta fase

- No generar catálogo, precios ni stock ficticios para probar la integración — usar los datos reales o mocks claramente marcados como tales.
- No mezclar los anti-patrones dentro del mismo índice que los patrones positivos sin poder diferenciarlos en la recuperación (deben poder consultarse/aplicarse independientemente como guardrail).
- No reemplazar el flujo de decisión existente del agente; conectar el Conversation RAG como una fuente de contexto adicional.

## Paso 7 — Entregable esperado de esta fase

Un PR (o rama) que:
1. Documente las respuestas del Paso 1.
2. Proponga (sin implementar aún, si el equipo lo prefiere revisar primero) dónde y cómo se indexarían estos cuatro archivos dentro de la arquitectura ya existente.
3. Señale explícitamente si algo de esta especificación no encaja con lo que ya existe en el repo, para decidir en conjunto antes de escribir código.
