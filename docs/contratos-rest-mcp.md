# Contratos REST y herramientas MCP (MVP)

**Estado:** propuesto · misma capa de autorización para ambas superficies.

## Auth

```
Authorization: Bearer <api_key>
X-Organization-Id: <uuid>   # o org embebida en el token
Idempotency-Key: <string>   # obligatorio en POST de writes
```

Scopes: `orgs:read`, `wallets:read`, `wallets:link`, `balances:read`, `payments:create`, `transfers:execute`, `approvals:decide`, `audit:read`, `policies:read`.

## REST — recursos iniciales

| Método | Path | Scope | Descripción |
| --- | --- | --- | --- |
| POST | `/v1/organizations` | (bootstrap / owner) | Crear org |
| GET | `/v1/organizations/me` | `orgs:read` | Org actual |
| POST | `/v1/applications` | admin | Crear application + credential |
| POST | `/v1/agents` | admin | Registrar AgentIdentity |
| POST | `/v1/wallets/link` | `wallets:link` | Vincular wallet externa |
| GET | `/v1/wallets` | `wallets:read` | Listar |
| GET | `/v1/wallets/{id}/balances` | `balances:read` | Balances (adapter) |
| POST | `/v1/payment-requests` | `payments:create` | Crear solicitud |
| GET | `/v1/payment-requests/{id}` | `payments:create` o read | Estado |
| POST | `/v1/payment-requests/{id}/approve` | `approvals:decide` | Aprobación humana |
| POST | `/v1/payment-requests/{id}/reject` | `approvals:decide` | Rechazo |
| POST | `/v1/transfers` | `transfers:execute` | Ejecutar transfer (desde request aprobado o auto-allow) |
| GET | `/v1/transfers/{id}` | `transfers:execute` o read | Estado + `network_tx_id` |
| GET | `/v1/ledger` | `audit:read` | Audit trail paginado |
| GET | `/v1/policies` | `policies:read` | Reglas activas |

### Errores canónicos

`401 unauthorized` · `403 forbidden` · `404 not_found` · `409 conflict` (idempotency mismatch) · `422 validation` · `429 rate_limited` · `502 adapter_error`

### Estados

PaymentRequest: `draft` → `pending_approval` → `approved` | `rejected` | `expired`  
TransferIntent: `queued` → `submitted` → `confirmed` | `failed`

## MCP — tools iniciales

Cada tool = caso de uso REST; **no** SQL.

| Tool | Maps to | Notas |
| --- | --- | --- |
| `list_wallets` | GET `/v1/wallets` | |
| `get_balances` | GET balances | |
| `create_payment_request` | POST payment-requests | Puede devolver `pending_approval` |
| `get_payment_request` | GET | |
| `execute_transfer` | POST transfers | Falla si policy/no aprobado |
| `get_transfer` | GET | |
| `list_ledger_entries` | GET ledger | |

Tools **no** incluidos en MVP: custodia, firmar arbitrario, exportar secrets, bypass policy.

## MCP Client (post-MVP)

AgentOS como consumidor. No es un tool del server `agentos-mcp` y no pasa por policy ni por el libro.

```python
from mcp.client.stdio import StdioServerParameters
from agentos_mcp.client import connect_mcp

async with connect_mcp(StdioServerParameters(command="agentos-mcp", args=[])) as session:
    names = await session.list_tool_names()
    text = await session.call_tool("list_wallets", {})
```

También acepta una URL Streamable HTTP (`http://host/mcp`) o un `MCPServer` in-process.

## Post-MVP — seams de laboratorio

Todavía no están cerrados. No hay cobro, ni Baneco, ni mainnet, ni custodia.

| Método | Ruta | Auth | Nota |
| --- | --- | --- | --- |
| GET | `/console` | no | HTML. No embebe secretos. |
| GET | `/v1/billing/plan` | `orgs:read` | `code=lab`, `payment_provider=null`, `charges=false` |
| GET | `/v1/connections` | `orgs:read` | `baneco_api_unverified`, `mainnet_denied`, EVM `not_connected` salvo `AGENTOS_EVM_RPC_URL` |
| GET | `/v1/ramps/routes` | `orgs:read` | Lista rutas Pollar. Puede venir vacía aunque un quote sí cotice. |
| POST | `/v1/ramps/quotes` | `payments:create` | Cotiza onramp/offramp. `stellar_address` opcional vincula wallet EXTERNAL antes. No crea la orden. |
| PUT | `/v1/ramps/wallets` | `payments:create` | Vincula una wallet EXTERNAL en Pollar para el `customer_id` (default: org). |
| POST | `/v1/fiat-settlements` | `payments:create` | Factory avisa un pago fiat ya confirmado. `Idempotency-Key` = `provider_ref`. No mueve una wallet. |

## SDK (Python) — superficie mínima

```python
client = AgentOS(base_url=..., api_key=..., organization_id=...)
client.wallets.list()
client.wallets.balances(wallet_id)
client.payments.create(...)
client.transfers.execute(payment_request_id=..., idempotency_key=...)
```
