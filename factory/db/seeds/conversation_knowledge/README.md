# Agent V2 — Conversation Knowledge Base

Conocimiento conversacional condensado para el **Conversation RAG** de Adri V2 (agente vendedor digital para PyMEs por WhatsApp).

Este paquete es el resultado de la **fase de ingeniería de conocimiento** solicitada: analizar dos datasets fuente, condensarlos en patrones reutilizables, y diseñar el conjunto de patrones y anti-patrones específicos de Adri. No incluye ni toca código del repositorio Agent IA V2.

---

## 1. Fuentes utilizadas

| Fuente | Archivo | Registros originales | Qué es |
|---|---|---|---|
| ConvRec | `convrec_shopping_mar2026_study_final.json` | 3.534 conversaciones (calzado/footwear) | Estudio con evaluación humana de 11 "personalidades" experimentales de asistente de compras, con feedback cualitativo y cuantitativo turno a turno |
| Bitext | `Bitext_Sample_Customer_Support_Training_Dataset_27K_responses-v11.csv` | 26.872 registros | Dataset genérico de entrenamiento de soporte al cliente, 27 intents en 11 categorías |

**Ninguno de los dos datasets contiene información real de ningún negocio.** Son material de entrenamiento/estudio: patrones de conversación y taxonomía de intención, no catálogo, precios ni políticas reales.

---

## 2. Qué se extrajo de cada fuente

- **ConvRec →** 18 patrones conversacionales generales (`01_convrec_patterns.json`) + un bloque de `experiment_insights` con las métricas reales de satisfacción de las 11 personalidades del estudio (calculadas sobre el campo `ratings` de cada turno) y las lecciones que se desprenden de cada una.
- **Bitext →** una taxonomía de 27 intents agrupados en 11 categorías (`02_bitext_intent_taxonomy.json`), con señales del cliente, objetivo conversacional, comportamiento recomendado y posibles próximas acciones para cada intent. Se conservaron las 27 distinciones originales (no se fusionaron intents para no perder matices importantes).
- **Adri V2 (diseño propio) →** 46 patrones específicos (`03_adri_business_patterns.json`) que cubren todos los escenarios pedidos: descubrimiento, catálogo, información comercial, conversación, conversión y postventa/soporte.
- **Anti-patrones →** 22 reglas de comportamiento a evitar (`04_anti_patterns.json`), varias de ellas con evidencia directa del estudio ConvRec (ej. por qué evitar el upsell agresivo o el tono inseguro).

## 3. Qué se descartó deliberadamente

- Las **3.534 conversaciones completas** de ConvRec y los **26.872 registros completos** de Bitext no se almacenan ni se indexarán tal cual — solo los patrones condensados.
- Las **respuestas literales** (`response`) del CSV de Bitext no se guardaron como texto: son ejemplos de redacción de un dataset genérico, no conocimiento empresarial real.
- Las personalidades de ConvRec que resultaron en **malas prácticas** (upseller agresivo, ramblear en exceso, interpretar todo literalmente, sonar inseguro, inventar tendencias) se documentaron como advertencia (`experiment_insights` y `04_anti_patterns.json`), pero **no** se convirtieron en reglas de comportamiento de Adri.
- No se generó código de integración: ese es el objetivo del archivo `CURSOR_INTEGRATION_SPEC.md`, para una fase posterior.

## 4. Qué significa cada archivo

```
agent-v2-conversation-knowledge/
├── README.md                          → este documento
├── 01_convrec_patterns.json           → patrones de comportamiento conversacional (18) + insights del experimento
├── 02_bitext_intent_taxonomy.json     → taxonomía de intents de soporte/venta (27)
├── 03_adri_business_patterns.json     → patrones específicos de Adri V2 (46), cubren todo el ciclo de conversación
├── 04_anti_patterns.json              → comportamientos a evitar siempre (22)
├── conversation_knowledge_bundle.json → los cuatro componentes anteriores consolidados en un solo archivo
└── CURSOR_INTEGRATION_SPEC.md         → instrucciones para integrar este conocimiento al repo existente (fase 2, para Cursor)
```

Cada registro de cada archivo incluye un bloque `metadata` (`source`, `domain`, `intent`, `situation`, `priority`, `version`) pensado para que cada patrón pueda indexarse razonablemente como un documento/chunk independiente en pgvector.

## 5. Cómo debe utilizarse este conocimiento

- El **Conversation RAG** responde: *"¿qué situación conversacional está ocurriendo y cómo debería manejarla Adri?"*
- Cada patrón indica **qué detectar → qué recuperar → qué decidir → qué acción ejecutar**, nunca una respuesta final prefabricada.
- El campo `recommended_next_action` / `next_action` de cada patrón es una instrucción para el **Agentic Reasoning**, no texto para copiar y pegar al cliente.
- Los anti-patrones son **reglas duras**: deben aplicarse como guardrails, no como sugerencias opcionales.

## 6. Qué NO debe hacer el Conversation RAG

- No debe usarse como fuente de catálogo, precios, stock o políticas — eso es responsabilidad exclusiva del **Business RAG**.
- No debe devolver texto literal de los datasets fuente como respuesta al cliente.
- No debe tratarse como una base de respuestas para copiar y pegar.
- No debe usarse para justificar afirmaciones sobre el negocio real (ver sección 10, alucinaciones).

## 7. Diferencia entre Business RAG y Conversation RAG

| | Business RAG | Conversation RAG |
|---|---|---|
| Responde | ¿Qué tiene realmente este negocio? | ¿Qué situación está ocurriendo y cómo se maneja? |
| Contiene | Catálogo, precios, stock, políticas, FAQ reales | Patrones, intenciones, situaciones, estrategias, anti-patrones |
| Fuente de verdad para | Hechos del negocio | Comportamiento conversacional |
| Este paquete es | ❌ No | ✅ Sí |

## 8. Cómo debería utilizarlo Agentic Reasoning

Arquitectura conceptual:

```text
Customer Message
       ↓
Intent / Situation Detection      (usa 02_bitext_intent_taxonomy + 03_adri_business_patterns)
       ↓
Conversation RAG                  (recupera el patrón relevante, incluyendo qué evitar)
       ↓
Relevant Pattern
       ↓
Business RAG                      (obtiene la evidencia real del negocio necesaria)
       ↓
Real Business Evidence
       ↓
Agentic Reasoning                 (decide la próxima acción combinando patrón + evidencia real)
       ↓
Next Action
       ↓
Response
```

El patrón conversacional **nunca reemplaza** la consulta al Business RAG cuando la situación requiere datos reales (precio, stock, existencia de producto, políticas). El patrón solo informa *cómo* comportarse mientras se obtiene y comunica esa información.

## 9. Advertencias sobre alucinaciones

Todos los anti-patrones relacionados con "inventar" (`anti_001` a `anti_005`, `04_anti_patterns.json`) existen porque el mayor riesgo de un Conversation RAG mal usado es que sus **ejemplos** (que son ficticios, de estudio) se confundan con **hechos reales del negocio**. Reglas duras:

1. Ningún dato de producto, precio, stock, característica o política puede originarse en `01_convrec_patterns.json`, `02_bitext_intent_taxonomy.json` o `03_adri_business_patterns.json` — esos archivos solo definen comportamiento.
2. Todo dato factual debe originarse en el Business RAG real de Agent IA V2, consultado en tiempo real.
3. Si el Business RAG no tiene la información, Adri debe decirlo explícitamente (`anti_022`), nunca completar el vacío con una suposición plausible.

## 10. Informe final

| Métrica | Valor |
|---|---|
| Patrones ConvRec obtenidos | 18 (+ bloque de insights del experimento sobre 11 personalidades) |
| Intents Bitext | 27 (11 categorías) |
| Patrones específicos de Adri | 46 |
| Anti-patrones | 22 |
| Conversaciones ConvRec analizadas (agregado, no almacenadas literalmente) | 3.534 |
| Registros Bitext analizados (agregado, no almacenados literalmente) | 26.872 |

**Posibles duplicados / solapamientos a revisar:**
- Algunos patrones de `01_convrec_patterns.json` y `03_adri_business_patterns.json` cubren la misma situación desde ángulos distintos (ej. `cliente_indeciso`, `cliente_rechaza_recomendacion`, `producto_mencionado_anteriormente`). Esto es intencional — ConvRec documenta el patrón *general* observado en el estudio, Adri lo adapta al flujo específico de venta por WhatsApp — pero conviene revisarlos juntos antes de indexar en pgvector para evitar chunks redundantes.
- `check_refund_policy` (Bitext) y `return_request` (Adri) se solapan parcialmente; se dejaron separados porque uno es "informar política" y el otro "gestionar una devolución en curso".

**Limitaciones del proceso:**
- El estudio ConvRec es de un solo dominio (calzado). Los patrones se generalizaron deliberadamente para cualquier catálogo de PyME, pero conviene validar con datos propios de Adri una vez en producción.
- Los `experiment_insights` (ratios de satisfacción) se calcularon sobre datos agregados reales del dataset, pero el tamaño de muestra por personalidad (~300-330 conversaciones) es moderado; tratarlos como evidencia direccional, no como benchmark definitivo.
- Bitext no incluye ningún escenario de venta/recomendación de producto (es soporte post-venta genérico); todo lo relacionado a descubrimiento y catálogo en `03_adri_business_patterns.json` es diseño propio informado por ConvRec, no por Bitext.
- No se validó este conocimiento contra el repositorio real de Agent IA V2 — ver `CURSOR_INTEGRATION_SPEC.md` para los pasos de inspección previos a integrar.

**Qué información debería obtenerse del repositorio Agent IA V2 antes de implementar el RAG:** ver sección "Antes de escribir código" de `CURSOR_INTEGRATION_SPEC.md`.
