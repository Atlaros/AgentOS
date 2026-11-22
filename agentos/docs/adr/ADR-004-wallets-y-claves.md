# ADR-004 — Wallets y claves

**Estado:** propuesto (pendiente aprobación)  
**Fecha:** 2026-11-20

## Contexto

AgentOS no debe custodiar claves en texto plano. El MVP debe demostrar valor sin HSM completo.

## Decisión propuesta (MVP)

1. **Solo wallets externas / conectadas** (el usuario o la app firman fuera de AgentOS, o se usa una cuenta Stellar de test cuya secret se inyecta solo en entorno de prueba controlado vía adapter, nunca en tablas de producto).
2. AgentOS almacena: `public_address`, `network`, `provider`, `link_status`, metadatos — **no** `secret_key`.
3. Custodia propia / managed wallets = **post-MVP** (ADR futuro + KMS/HSM).

## Consecuencias

- Transferencias en testnet: el adapter Stellar recibe material de firma desde secret store de entorno / proceso de firma externo, no desde Postgres de app.
- Claridad de amenaza: AgentOS autoriza y registra; no es vault de claves en el MVP.

## Abierto

- ¿El piloto usa una keypair de testnet solo en `.env` del adapter (dev) o un signer service mínimo?
