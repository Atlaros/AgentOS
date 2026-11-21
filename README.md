# AgentOS

Independent financial infrastructure for agents and applications.

**Not** Factory Agent OS. **Not** Agent-IA. Those products may consume AgentOS later; they are not dependencies of this repository.

## Status

Phase 1 architecture is documented under [`docs/`](docs/). Implementation scaffolding starts after the open decisions in [`docs/riesgos-y-decisiones.md`](docs/riesgos-y-decisiones.md) are approved.

## MVP heart

An external agent can: query a wallet → request a transfer → execute it under authorization policy (human approval when required), audited, via REST and MCP.

First network: **Stellar Testnet**. No private keys stored in the application database.

## Local path

```text
~/Documentos/GitHub/AgentOS
```

Sibling of `Factory Agent OS`. Do not modify Factory from this repo.
