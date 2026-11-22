# Estructura del repositorio — AgentOS

**Nombre propuesto del repo:** `AgentOS` (org Atlaros o personal; **pendiente aprobación**).  
**Independiente** de `Factory-Agent-OS-next` y de Agent-IA V2.

## Árbol propuesto

```text
agentos/
├── README.md
├── AGENTS.md                 # invariantes para agentes de código
├── pyproject.toml            # uv workspace
├── uv.lock
├── .env.example              # solo nombres; sin secretos
├── docker-compose.yml        # postgres local (puerto distinto a Factory)
├── .github/workflows/ci.yml
├── docs/
│   ├── 00-vision.md
│   ├── 01-arquitectura.md
│   ├── 02-contratos.md
│   ├── adr/                  # ADR-001… (copiados/aprobados desde este store)
│   └── patterns/
├── apps/
│   ├── api/                  # FastAPI entrypoint
│   │   └── agentos_api/
│   └── mcp/                  # MCP server (mismo use-case layer)
│       └── agentos_mcp/
├── packages/
│   ├── agentos_domain/       # entidades + puertos (sin I/O)
│   ├── agentos_identity/
│   ├── agentos_orgs/
│   ├── agentos_wallets/
│   ├── agentos_ops/          # payment requests + transfers
│   ├── agentos_policy/
│   ├── agentos_ledger/
│   ├── agentos_adapters/     # stellar + fake
│   └── agentos_sdk/          # cliente Python thin
├── migrations/               # Alembic; numeración propia desde 001
└── tests/
    ├── unit/
    ├── integration/          # FACTORY_OS_* no; AGENTOS_TEST_DATABASE_URL
    └── golden/
```

## Reglas de dependencia

```
api / mcp  →  identity, orgs, wallets, ops, policy, ledger
ops        →  domain ports + policy + ledger ports
adapters   →  implementa ports de domain (stellar-sdk solo aquí)
sdk        →  solo HTTP; sin imports de api
```

Prohibido: `agentos_*` → cualquier paquete `factory_os` / Agent-IA.

## Tooling

| Herramienta | Uso |
| --- | --- |
| uv | deps + lock |
| pytest | unit (Fake) + integration opt-in |
| ruff + mypy | lint/types |
| Alembic | migraciones |
| Docker Compose | solo Postgres dev/test |

## Qué no incluir al crear el repo

- Next.js / apps/web de Factory
- LangGraph
- Seeds de catálogo café/ropa
- Scripts de Meta/WhatsApp
