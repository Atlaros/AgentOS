# ADR-025 — Lienzo con React Flow

**Estado:** aceptado (19/11/2026).
**Relación:** implementación de la pantalla de [ADR-023](ADR-023-lienzo-con-barandas.md). No cambia sus barandas.

---

## 1. Contexto

El lienzo de `/operator/flow` está hecho a mano: `flow-board.tsx` (535 líneas) resuelve arrastre, posiciones, puertos y resaltado de destinos con eventos de drag nativos. Funciona para el primer corte, pero lo que sigue (zoom, paneo, aristas dibujadas, selección, panel de propiedades, minimapa, accesibilidad de teclado) es trabajo de librería, no de producto.

## 2. Decisión

Usar [React Flow](https://reactflow.dev) (`@xyflow/react`, licencia MIT) solo como capa de dibujo e interacción.

| Lo hace React Flow | Lo sigue haciendo Factory |
| --- | --- |
| nodos y aristas en pantalla, zoom, paneo, selección, minimapa | qué nodos existen (`palette` del `flow-map`) |
| asas por puerto en cada nodo | qué puertos tiene cada nodo y cuáles son compatibles (`compatible`) |
| impedir en pantalla una conexión inválida | validar en el servidor al guardar y al publicar |
| marcar nodos y aristas como no borrables | qué es el núcleo bloqueado (`locked`) |

La validación del servidor manda. Lo que React Flow impide en pantalla es solo comodidad: el API rechaza lo mismo aunque el cliente lo deje pasar.

## 3. Alternativas

| Opción | A favor | En contra |
| --- | --- | --- |
| Seguir a mano | sin dependencia | cada función nueva es código propio de canvas |
| React Flow | estándar en editores de flujo, React nativo, MIT | una dependencia más; hay que adaptar estilos a los tokens del panel |
| Rete.js, JointJS | potentes | más pesados o con licencia comercial para lo que necesitamos |

## 4. Fuera

- Nodos libres, código o SQL desde el lienzo.
- Ejecutar flujos en el navegador.
- Cambiar el contrato del `flow-map` o de las reglas.

## 5. Cómo se prueba

- Los tests de `tests/test_flow_canvas.py` siguen verdes sin cambios.
- Un test del panel (requiere el runner de `apps/web`) prueba que una conexión entre puertos distintos no se dibuja y que el núcleo no se borra.
- La pantalla usa los tokens del panel en tema claro y oscuro.
