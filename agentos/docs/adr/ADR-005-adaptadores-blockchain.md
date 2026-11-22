# ADR-005 — Adaptadores blockchain

**Estado:** propuesto (pendiente aprobación)  
**Fecha:** 2026-11-20

## Contexto

AgentOS debe ser agnóstico de red. Stellar Testnet es la primera integración.

## Decisión propuesta

Ports internos (interfaces), implementaciones detrás:

- `NetworkAdapter`: balances, submit tx, confirm tx, map assets.
- `PaymentRailAdapter` (futuro fiat): separado; Baneco **no** se asume ni se porta.

MVP: `StellarTestnetAdapter` + `FakeNetworkAdapter` (tests sin red).

EVM/Solana/custody = fuera del MVP.

## Consecuencias

- Dominio Ops habla en intents (`PaymentRequest`, `TransferIntent`), no en XDR/Stellar SDK.
- Cambiar de red = nuevo adapter, no reescribir el motor.

## Abierto

- Asset nativo XLM vs asset de confianza en el piloto.
