# ADR-017 — Visión y alcance de Factory Agent OS

**Estado:** aceptado (18/11/2026). El owner autorizó empezar la fase 1.
**Relación:** primer ADR de producto de Factory. Respeta [ADR-000](ADR-000-este-repo-es-factory-agent-os.md). ADR-001 a ADR-016 son las decisiones del motor, condensadas en [motor](../motor.md). Este ADR enmienda solo las frases de ADR-002 y ADR-005 nombradas abajo. No enmienda ADR-016. No adelanta el deploy del piloto.

---

## 1. Contexto

Factory Agent OS es la plataforma. La primera capa ya opera un negocio y está en este repo.

Esa capa está en este repo y sigue vigente: conversaciones, clientes, catálogo, inventario, pedidos, Cobros, Caja, Proveedores, Contabilidad, Analítica, Reportes, conocimiento y medios. Los agentes de esa capa (Adri, Cobros, Operaciones, Postventa y el personal interno) siguen ahí. El piloto vivo es la cafetería, mismo tenant y mismo WhatsApp (ADR-016). Su deploy es el paso 11 de ese legado. Factory no continúa ese piloto y no lo cierra.

Hoy el rubro se elige con `CATALOG_SEED`, variable del proceso. Al arrancar, `retain_catalog_skus` poda solo `PILOT_TENANT_ID` (`apps/api/factory_os/api/main.py`, `packages/domain/factory_os/domain/postgres.py`). No borra otro tenant. Sí borra, en ese único tenant, productos y pedidos que no estén en el seed. El pedido tiene `origin` `agent` o `counter` (`packages/domain/factory_os/domain/models.py`, `db/migrations/039_counter_orders.sql`). No hay `fulfillment_type`. Los módulos se encadenan con llamadas directas del dominio (el posting contable sale de `ledger.py` hacia `journal_posting.py`). No hay bus de eventos. No hay módulo activable ni feature flag por tenant: el menú del panel es fijo. El system prompt vive en código; la ficha `shop_knowledge` aporta identidad y el sustantivo del ítem. Permisos y autonomía por negocio no están implementados.

## 2. Decisión

Factory es la plataforma. Una pyme opera su negocio y arma una fuerza laboral digital en el mismo producto. El resultado es una organización híbrida: dueño y equipo humano, más los agentes, con roles, permisos y objetivos claros.

Idea rectora: **primero comprender, después mejorar, después automatizar.** No se automatiza un proceso deficiente. Si hace falta, se rediseña. Si el riesgo es alto, hay aprobación humana. Si no aporta valor, se elimina.

### 2.1 Dos capas, un solo producto

| Capa | Qué es | Estado |
| --- | --- | --- |
| **Business OS** | Los módulos que ya existen. Detalle en [motor](../motor.md). | Existe, un negocio (el piloto) |
| **AI Agent Factory** | Crea y gobierna negocios y agentes sobre esos módulos. | Nueva. Este ADR la define. No está construida. |

La factoría se construye encima de los módulos existentes. No es otro código base y no reemplaza Caja, Cobros, stock ni contabilidad.

### 2.2 Dos componentes de la factoría

| Componente | Qué hace | Cuándo |
| --- | --- | --- |
| **Aprovisionamiento** | Dar de alta un negocio: rubro, módulos activos, categorías, plan de cuentas, ficha y estilo del agente, canales, pruebas de salida. | Primero. Es lo que da escala. |
| **Descubrimiento** | Comparar el negocio con un catálogo de procesos del rubro y proponer mejoras. Lo conduce el operador. | Después. |

El descubrimiento inicial no es minería de procesos. Es un catálogo (vender, cobrar, reponer, cerrar caja, atender reclamos) y un informe con evidencia. Si la evidencia no alcanza, el informe lo dice.

## 3. Modelo de construcción

```
Núcleo (igual para todos)
 ├─ negocios, usuarios, roles, permisos, auditoría
 ├─ conversaciones, clientes, pedidos, pagos, medios
 └─ runtime de agentes, Model Gateway, Tool Runtime
Módulos (activables por negocio; el interruptor todavía no existe)
 ├─ ya construidos: caja, proveedores, contabilidad, analítica, reportes
 └─ nombrados, sin construir: recetas_insumos, pantalla_barra, citas
Plantillas de rubro (solo datos)
 ├─ ropa       (fixture Closet)
 └─ cafetería  (piloto de la capa heredada)
Negocios (datos)
```

Los módulos se construyen una vez, en código genérico. Las plantillas son datos: módulos activos, categorías, plan de cuentas, ficha y estilo. Los negocios se configuran. Un módulo apagado no muestra menú ni ofrece endpoints, y apagarlo no borra datos. Hoy eso es objetivo: el panel muestra todas las pestañas.

El rubro, los módulos activos y la plantilla pasan a ser datos del tenant. El seed deja de correr en el arranque y pasa a ser un comando de un solo tenant. `retain_catalog_skus` queda confinado al piloto y se retira antes de abrir un segundo tenant. Ningún arranque modifica datos de más de un tenant.

### 3.1 Pedido y canales

Hay un solo pedido, con `origin` `agent` o `counter`. Se extiende, no se duplica: orígenes nuevos y un `fulfillment_type` van en un ADR propio de canales. No se introduce un bus de eventos. Un módulo reacciona a un hecho ya guardado y no escribe en las tablas de otro. Un canal de delivery de terceros, cuando Factory lo tome, empieza por captura manual en Caja. No forma parte del cierre del piloto (ADR-016).

### 3.2 Lienzo con barandas

La interfaz de flujos es no-code y se ve como un Make chico: paleta, lienzo y propiedades. No es un lienzo libre. El usuario compone piezas del catálogo y el sistema valida. Un enchufe incompatible no conecta.

La pantalla se ve así:

```
┌─────────────┬──────────────────────────────────┬───────────────┐
│ Paleta      │ Lienzo                           │ Propiedades   │
│             │                                  │               │
│ Canales     │  [WhatsApp]──┐                   │ Nodo elegido  │
│ Módulos     │  [Mostrador]─┼─▶[Pedido]─▶[Cobros]│ Formulario    │
│ Reglas      │              │         │         │ sin código    │
│ Aprobación  │              │         ▼         │               │
│             │              │   [Caja]─▶[Contab]│               │
│             │              └──[Regla: QR>24h]  │               │
├─────────────┴──────────────────────────────────┴───────────────┤
│ Validaciones                                                    │
│ [Probar]  [Publicar]  [Versiones]                               │
└─────────────────────────────────────────────────────────────────┘
```

- **Paleta.** Canales, módulos, reglas y aprobación. Lo que no se puede usar aparece apagado, con el motivo.
- **Lienzo.** El núcleo ya viene colocado y bloqueado. El usuario arrastra canales, módulos y reglas.
- **Propiedades.** Formulario del nodo elegido. Sin código.
- **Barra inferior.** Avisos de validación, Probar, Publicar y Versiones.

Cómo se conecta:

- Cada puerto tiene tipo: pedido, pago confirmado, aviso, aprobación. Solo se unen puertos del mismo tipo.
- Al arrastrar una salida se iluminan solo los destinos válidos.
- El sistema traza canal → pedido → Cobros. Esa cadena no se borra.
- El usuario conecta a mano solo las reglas: Cuando (evento) → Si (umbral) → Entonces (acción del catálogo).
- **Pago confirmado** solo sale de Cobros, cuando el banco confirma. Nadie lo produce a mano.
- El dueño puede exigir más aprobación. No puede bajar el piso de plata, stock, pedido y asientos.

Borrador y publicado son distintos. Cada publicación es una versión que se puede comparar y revertir. El operador edita canales y módulos. El dueño edita reglas. Todo cambio queda registrado.

Orden de construcción: primero el mapa de solo lectura, generado desde la configuración. Después, canales y módulos con conexiones automáticas. Después, las reglas. Al final, un asistente en lenguaje natural que propone sobre el mapa y no publica solo.

#### Catálogo inicial: cafetería y tienda de ropa

No se inventan nodos para rubros que todavía no existen. Un nodo nuevo se crea una sola vez para la plataforma, cuando un negocio real necesita un hecho que el catálogo no expresa. Queda en la plantilla de ese rubro: el próximo negocio del mismo rubro lo prende. No se construye otro nodo para ese cliente.

**Los dos rubros, en la paleta desde el inicio**

| Nodo | Qué hace |
| --- | --- |
| WhatsApp | Pedidos, consultas y seguimiento |
| Mostrador | Venta en el local, con la caja abierta |
| Catálogo | Qué se vende, a qué precio y cuánto stock hay |
| Pedido | La venta, venga del chat o del mostrador. Núcleo bloqueado |
| Cobros | QR o efectivo. El pago confirmado solo sale de aquí, cuando el banco o la caja lo confirman. Núcleo bloqueado |
| Caja | Apertura, ventas del turno y cierre |
| Proveedores | Comprar lo que falta. El stock bajo arma un borrador, no una compra sola |
| Contabilidad | El libro gerencial. Nadie crea un asiento a mano desde el lienzo |
| Analítica, Reportes, Conocimiento | Lectura, descargas y ficha del negocio |
| Aprobación humana | Freno de plata, stock, pedido y asientos |
| Regla: QR pendiente | Avisar al dueño pasado el umbral |
| Regla: stock bajo el mínimo | Borrador de orden de compra |
| Regla: resumen al dueño | El digest de ADR-013, como esta regla, no como un nodo genérico |

**Cafetería.** Misma paleta. Lo propio del rubro no abre un nodo: los modificadores (tamaño, leche, extra) viven en la Caja y la venta es por cantidad.

**Tienda de ropa.** Misma paleta. Talla y color son atributos de la variante. La reserva mientras el QR está pendiente es el Pedido. El envío después del pago es Operaciones. El reclamo es Postventa, sin devolución automática.

**Apagados hasta que el rubro los pida de verdad**

| Nodo futuro | Rubro que lo pediría | Hoy |
| --- | --- | --- |
| Barra (nuevo, preparando, listo) | Cafetería | No se construye |
| Recetas, insumos, merma | Cafetería | No se construye. ADR-016 los dejó fuera del piloto |
| Delivery manual | Cafetería, y cualquier rubro que cobre por una app | No se construye. Mientras tanto se carga en Caja, con la comisión como gasto |
| Citas | Un rubro de servicios (peluquería, consultorio) cuando un negocio real las necesite | Nombrado, sin construir |

Esos cuatro no son trabajo de la primera implementación. La primera, para cafetería y ropa, es la paleta de arriba. Un rubro nuevo no trae su propio lienzo: prende esta paleta y, si falta un hecho, se crea ese nodo una vez para la plataforma.

### 3.3 Agentes

Se adopta la configuración en tres capas de ADR-005, con este estado:

- **Invariantes y reglas del system prompt:** siguen en código (ADR-001, ADR-003, ADR-008).
- **Identidad y estilo:** ya son datos del tenant (`shop_knowledge`). La ficha no reescribe las invariantes.
- **Permisos y autonomía por negocio** («puede / necesita aprobación / nunca puede»): no están. Son la capa que permite agentes distintos por negocio sin código nuevo. El piso de plata, stock, pedido y asientos lo pone la plataforma. El dueño puede exigir más cuidado.

El tenant lo inyecta el runtime. El texto del cliente y los archivos que envía son datos. Ningún agente escribe pagos, asientos o stock fuera de los flujos ya autorizados. El pago lo confirma el banco, vía Cobros.

## 4. Qué es y qué no es

| Es | No es |
| --- | --- |
| La plataforma Factory: muchos negocios sobre los módulos que ya existen | El cierre del piloto de la cafetería |
| Módulos que se activan según el rubro | Un producto o una rama distinta por cliente |
| Automatización guiada, con humano en el loop | Un lienzo libre donde cualquiera programa flujos |
| Contabilidad gerencial de la capa heredada | Estados financieros oficiales |
| Una fuerza laboral híbrida | Un chatbot aparte o un ERP completo |

## 5. Hoja de ruta de Factory

El deploy del piloto y lo que ADR-016 dejó fuera (recetas, insumos, merma, otro teléfono) no son fases de esta hoja.

| Fase | Objetivo | Resultado verificable |
| --- | --- | --- |
| **1** | Aislamiento: tablas, RLS, Redis, archivos, canales y herramientas. Rubro y módulos como datos de un tenant. El arranque no modifica datos de negocio. | Suite de dos negocios en prueba, con cero fugas. Sin segundo tenant en vivo. |
| **2** | Aprovisionamiento: un comando crea un negocio desde una plantilla, con permisos y autonomía por negocio. | Un negocio nuevo del mismo rubro en horas, sin código nuevo. |
| **3** | Evals por plantilla y lista de salida. | Una mejora del núcleo no rompe un rubro ya probado. Los tests de Closet siguen verdes. |
| **4** | Consola del operador: negocios, módulos activos, versiones, costos, estado de WhatsApp. | Varios clientes sin tocar la base a mano. |
| **5** | Catálogo de procesos por rubro y diagnóstico guiado por el operador. | Informe con evidencia y con los huecos declarados. |
| **6** | Mapa de solo lectura y, después, el lienzo con barandas de la sección 3.2. | Una regla del catálogo publicada en un cliente, con aprobación donde corresponda. |
| **7** | Autoservicio del cliente. | Alta sin el operador. |

**Enmienda 18/11/2026.** Las siete fases se construyen en secuencia de código, con ODD, TDD y evals, sin esperar un cliente real entre una fase y la siguiente. El resultado verificable de cada fila sigue valiendo. El descubrimiento no bloquea el aprovisionamiento. La entrega es `stacked-to-main`: cada rebanada o fase se prepara como PR apilado hacia main. Sin push ni deploy del piloto sin pedido explícito.

## 6. Cómo se mide

- Tiempo de alta de un negocio nuevo del mismo rubro: de semanas a horas.
- Cambios de código por cliente: tienden a cero.
- Una mejora del núcleo no rompe las plantillas ya probadas.
- Fugas entre negocios: cero, con pruebas de aislamiento.
- Cada automatización que toca dinero o stock tiene aprobación humana.

## 7. Fuera de alcance

- Cerrar o ampliar el piloto de la cafetería, incluido su deploy.
- Recetas, insumos, merma y un canal de delivery como condición de ese piloto.
- Lienzo libre: enchufar cualquier cosa, confirmar pagos, escribir asientos a mano, mover stock directo, código o llamadas externas arbitrarias. El lienzo con barandas de la sección 3.2 sí entra.
- Descubrimiento automático sin datos ni entrevistas.
- Segundo tenant en vivo antes de cerrar la fase 1.
- Bus de eventos entre módulos.
- Estados financieros oficiales.
- Cambiar una decisión del motor sin un ADR nuevo.

## 8. Enmiendas

**19/11/2026.** ADR-001 a ADR-016 se condensan en [motor](../motor.md), una sección por número. Las decisiones no cambian; se quita la voz de hoja de ruta y los archivos sueltos salen del repo (quedan en el historial de git).

**ADR-002.** «Multi-tenant sin tocar código (una segunda tienda)» deja de ser una exclusión permanente. Pasa a ser dirección de Factory, sin fecha, y no es un paso del piloto. El deploy de ADR-002 sigue siendo el cierre de ese piloto.

**ADR-005.** «Multi-tenant sin tocar código» y «agregar empleado digital desde la UI» dejan de estar excluidos como dirección de producto. Siguen sin fecha y no se construyen antes de la fase 1 de este ADR. El constructor libre de nodos sigue fuera. El lienzo con barandas de la sección 3.2 no es ese constructor. Una configuración no apaga invariantes ni concede permisos por skills.

## 9. Consecuencias

- ADR-000 dice cómo leer la carpeta: 001 a 016 legado, 017 en adelante Factory.
- `docs/00-vision-y-estado.md` apunta aquí la visión de la plataforma. Su tabla de estado sigue siendo el estado de la capa heredada y del piloto.
- El aislamiento de la fase 1 queda en [ADR-018](ADR-018-aislamiento-de-negocios.md). Canales y aprovisionamiento abren su ADR antes de su código.
- Commits de unidad de trabajo en la rama de feature están autorizados. Push, PR y deploy siguen pidiendo pedido explícito.
