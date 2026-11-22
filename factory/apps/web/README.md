# apps/web — panel del dueño

Next.js 15 (App Router). Habla con la API en `:8000`.

## Correr

```bash
# terminal 1 — API
docker compose up -d db
# o uvicorn / factory-os-api

# terminal 2 — web
cd apps/web
npm install
API_INTERNAL_URL=http://localhost:8000 \
OWNER_DASHBOARD_TOKEN=your-owner-token \
npm run dev
```

Abrí http://localhost:3000

La clave se ingresa en `/login`. Configura `OWNER_DASHBOARD_TOKEN` para la API y
el servidor Next.js; Next.js crea una cookie `HttpOnly` y realiza las llamadas al
API desde el servidor. No uses una variable `NEXT_PUBLIC_*` para la clave.

## Rutas

| Ruta | Qué |
| --- | --- |
| `/` | lista de chats |
| `/chats/[id]` | mensajes, takeover, reply |
| `/orders` | pedidos |
| `/catalog` | catálogo (alta + vendido/disponible) |
| `/cash` | Contabilidad: caja interna |
| `/suppliers` | Proveedores: ingreso stock + alerta baja |
| `/metrics` | Analítica (ADR-013 T1): período 7d vs 7 prev, Δ%, alertas tipadas, umbrales tenant; owner/supervisor |
