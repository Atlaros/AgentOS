# ADR-023 — Lienzo con barandas

**Estado:** aceptado (18/11/2026). Autoriza la fase 6 de [ADR-017](ADR-017-vision-y-alcance-factory-agent-os.md) §3.2.
**Relación:** piezas del catálogo de [ADR-022](ADR-022-catalogo-de-procesos.md). No es un constructor libre de nodos.

---

## 1. Contexto

La fase 6 pide primero un mapa de solo lectura y después el lienzo con barandas. El núcleo canal → pedido → Cobros no se borra. El pago confirmado solo sale de Cobros.

## 2. Decisión

Primera rebanada:

1. **Mapa de solo lectura** generado desde los módulos activos: nodos y aristas tipadas. El camino WhatsApp/Mostrador → Pedido → Cobros queda `locked=true`.
2. **Reglas del catálogo** Cuando → Si → Entonces, en borrador o publicadas. Publicar una regla exige puertos compatibles y no puede inventar «pago confirmado».
3. API: `GET /api/operator/flow-map`, `GET /api/operator/rules`, `POST /api/operator/rules`, `POST /api/operator/rules/{id}/publish`.
4. Pantalla `/operator/flow`: el camino bloqueado se ve como un riel, y el operador guarda o publica una regla Cuando / Si / Entonces. Puede arrastrar un módulo sobre otro: el puerto elegido es la unión. Al arrastrar, el mapa `compatible` del `flow-map` ilumina solo los destinos válidos para ese puerto; un destino inválido no recibe el drop. El mismo puerto une, uno distinto no, y Pedido con Cobros no se puentea. Una regla publicada se puede reemplazar y volver a la versión anterior.

Los módulos salen colocados en un lienzo 2D (`positions` del `flow-map`); el operador los puede reposicionar. El `flow-map` también expone `palette` (solo piezas del catálogo). Arrastrar desde la paleta coloca un módulo que todavía no está en el lienzo; un kind desconocido no entra. El enlace sigue yendo por el puerto (asa Link) con destinos válidos iluminados. La validación manda.

Sin base, las reglas quedan en memoria del proceso y cada publicación guarda una versión a la que se puede volver. Con `database_runtime_url` se guardan en `catalog_rules` y cada publicación queda en `catalog_rule_versions` (`051_catalog_rule_versions.sql`), así se puede volver a una versión anterior después de reiniciar. Esa tabla no tiene RLS: la consola lee las reglas de todos los negocios, igual que `tenants`. No se aplica sola a la base del café que ya corre.

## 3. Fuera

- Nodos libres, SQL, APIs arbitrarias, confirmar pago a mano.
- Nodos futuros (barra, recetas, citas) sin construir.
