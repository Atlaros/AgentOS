# Flujo completo — transferencia Stellar Testnet

**Objetivo MVP:** un agente externo consulta wallet → solicita pago → (policy) → ejecuta en Testnet → queda auditado.

## Actores

- **Consumer:** Agent-IA u otro agente vía REST/MCP  
- **AgentOS API:** auth, policy, ledger  
- **StellarTestnetAdapter:** horizon testnet + submit  
- **Human approver:** si policy `require_human`  
- **Signer path (MVP):** material de firma **fuera** de Postgres (env del adapter en lab / proceso externo). Ver ADR-004.

## Secuencia (caso con aprobación)

```text
Consumer                AgentOS                 Policy          Adapter           Horizon
   |                       |                      |               |                 |
   |-- POST payment-req -->|                      |               |                 |
   |                       |-- evaluate --------->|               |                 |
   |                       |<- require_human -----|               |                 |
   |<- 201 pending_approval|                      |               |                 |
   |                       |                      |               |                 |
   |  (humano aprueba)     |                      |               |                 |
   |-- POST approve ------>|                      |               |                 |
   |                       |-- ledger approval    |               |                 |
   |-- POST transfer ----->|                      |               |                 |
   |                       |-- evaluate --------->| allow         |                 |
   |                       |-- submit --------------------------->|                 |
   |                       |                      |               |-- tx ---------->|
   |                       |                      |               |<- hash ---------|
   |                       |-- ledger submitted   |               |                 |
   |                       |-- confirm (poll) ------------------->| get tx          |
   |                       |-- ledger confirmed   |               |                 |
   |<- 200 confirmed ------|                      |               |                 |
```

## Caso auto-allow (monto bajo)

Policy `allow` si `amount <= limit` y scope `transfers:execute` → sin paso humano; mismo submit/confirm/ledger.

## Pasos internos (detalle)

1. **Auth:** API key → application/agent + org context + scopes.  
2. **Validate:** amount > 0, asset conocido en network `testnet`, `to_address` válido StrKey.  
3. **Idempotency:** misma key + mismo body → misma respuesta; body distinto → `409`.  
4. **Policy:** match por amount, asset, subject_type, network.  
5. **Build intent:** TransferIntent `queued`.  
6. **Adapter.submit:** construye payment op Stellar; firma vía signer path; POST a Horizon Testnet.  
7. **Persist:** `network_tx_id` (hash); status `submitted`.  
8. **Confirm:** poll/stream hasta success o timeout → `confirmed` | `failed`.  
9. **Ledger:** append entries en cada transición (sin secretos en `payload`).

## Criterios de aceptación del flujo

- [ ] Fake adapter: E2E unit sin red.  
- [ ] Testnet: una transferencia real XLM (o asset acordado) entre dos cuentas de lab.  
- [ ] Policy bloquea sin scope / sin aprobación.  
- [ ] Replay idempotente no doble-gasta.  
- [ ] Cross-org: org B no ve wallet/tx de org A.  
- [ ] Ninguna fila con secret key.

## Fuera de este flujo

Friendbot ops documentadas solo en runbook de lab · Mainnet · Multi-sig complejo · Path payments / DEX.
