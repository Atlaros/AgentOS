# Modelo de datos inicial — AgentOS

**Estado:** propuesto · schema nuevo (no migraciones Factory)

## Entidades MVP

```
organizations
  id uuid PK
  slug text UNIQUE
  name text
  created_at timestamptz

users
  id uuid PK
  email text UNIQUE
  created_at

memberships
  organization_id → organizations
  user_id → users
  role text  -- owner | admin | operator | viewer
  PK (organization_id, user_id)

applications
  id uuid PK
  organization_id → organizations
  name text
  status text  -- active | revoked
  created_at

api_credentials
  id uuid PK
  application_id → applications
  key_prefix text
  key_hash text
  scopes text[]
  expires_at timestamptz NULL
  revoked_at timestamptz NULL

agent_identities
  id uuid PK
  organization_id → organizations
  application_id → applications
  name text
  scopes text[]
  status text

wallets
  id uuid PK
  organization_id → organizations
  provider text  -- stellar | fake
  network text   -- testnet | public | fake
  public_address text
  label text
  link_status text  -- linked | disabled
  UNIQUE (organization_id, provider, network, public_address)

assets
  id uuid PK
  organization_id → organizations  -- o catálogo global + org enablement
  code text
  issuer text NULL  -- Stellar asset issuer; NULL = native
  network text
  decimals int

wallet_assets  -- opcional cache
  wallet_id → wallets
  asset_id → assets
  balance_cached numeric
  as_of timestamptz

payment_requests
  id uuid PK
  organization_id
  created_by_subject_type text  -- user|application|agent
  created_by_subject_id uuid
  from_wallet_id → wallets NULL
  to_address text
  asset_id → assets
  amount numeric
  memo text NULL
  status text  -- draft|pending_approval|approved|rejected|expired
  idempotency_key text
  UNIQUE (organization_id, idempotency_key)

transfer_intents
  id uuid PK
  organization_id
  payment_request_id → payment_requests NULL
  from_wallet_id → wallets
  to_address text
  asset_id → assets
  amount numeric
  status text  -- queued|submitted|confirmed|failed|cancelled
  network_tx_id text NULL
  idempotency_key text
  UNIQUE (organization_id, idempotency_key)

policy_rules
  id uuid PK
  organization_id
  name text
  effect text  -- allow|deny|require_human
  match jsonb  -- scopes, amount_max, asset, network, subject_type
  priority int
  enabled bool

approvals
  id uuid PK
  organization_id
  payment_request_id → payment_requests
  decided_by_user_id → users
  decision text  -- approved|rejected
  reason text NULL
  created_at

ledger_entries
  id uuid PK
  organization_id
  entry_type text  -- payment_requested|policy_decision|transfer_submitted|transfer_confirmed|…
  ref_type text
  ref_id uuid
  payload jsonb  -- sin secretos
  created_at
  -- append-only; sin UPDATE de payload
```

## RLS

Todas las tablas con `organization_id` (excepto `users` global):

```sql
-- conceptual
CREATE POLICY org_isolation ON <table>
  USING (organization_id = current_setting('app.organization_id')::uuid)
  WITH CHECK (organization_id = current_setting('app.organization_id')::uuid);
```

## Fuera de alcance del schema MVP

`orders`, `products`, `stock`, `conversations`, `canvas_nodes`, `whatsapp_*`, plan de cuentas comercial.

## Decisiones abiertas (datos)

1. ¿Assets globales compartidos vs por-org?
2. ¿Balances solo on-chain (read-through) o cache + TTL?
3. ¿Soft-delete de wallets o solo `link_status=disabled`?
