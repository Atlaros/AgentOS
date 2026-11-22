-- Double-entry journal (ADR-011). Separate from ledger_entries facts feed.

CREATE TABLE chart_accounts (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants (id),
    code text NOT NULL,
    name text NOT NULL,
    account_type text NOT NULL,
    is_system boolean NOT NULL DEFAULT true,
    active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (account_type IN ('asset', 'liability', 'equity', 'equity_draw', 'income', 'expense')),
    UNIQUE (tenant_id, code)
);

CREATE TABLE journal_entries (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants (id),
    entry_at timestamptz NOT NULL,
    origin_source text NOT NULL,
    origin_id uuid NOT NULL,
    kind text NOT NULL,
    memo text NOT NULL DEFAULT '',
    reverses_entry_id uuid REFERENCES journal_entries (id),
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (origin_source IN ('cash', 'payment', 'purchase')),
    CHECK (kind IN ('post', 'reverse')),
    UNIQUE (tenant_id, origin_source, origin_id, kind)
);

CREATE TABLE journal_lines (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants (id),
    entry_id uuid NOT NULL REFERENCES journal_entries (id) ON DELETE CASCADE,
    account_id uuid NOT NULL REFERENCES chart_accounts (id),
    direction text NOT NULL,
    amount numeric(12, 2) NOT NULL,
    currency text NOT NULL DEFAULT 'BOB',
    CHECK (direction IN ('debit', 'credit')),
    CHECK (amount > 0)
);

CREATE INDEX journal_lines_entry_idx ON journal_lines (tenant_id, entry_id);
CREATE INDEX journal_entries_origin_idx ON journal_entries (tenant_id, origin_source, origin_id);

ALTER TABLE chart_accounts ENABLE ROW LEVEL SECURITY;
ALTER TABLE chart_accounts FORCE ROW LEVEL SECURITY;
CREATE POLICY chart_accounts_tenant ON chart_accounts
    USING (tenant_id = current_setting('app.tenant_id')::uuid)
    WITH CHECK (tenant_id = current_setting('app.tenant_id')::uuid);

ALTER TABLE journal_entries ENABLE ROW LEVEL SECURITY;
ALTER TABLE journal_entries FORCE ROW LEVEL SECURITY;
CREATE POLICY journal_entries_tenant ON journal_entries
    USING (tenant_id = current_setting('app.tenant_id')::uuid)
    WITH CHECK (tenant_id = current_setting('app.tenant_id')::uuid);

ALTER TABLE journal_lines ENABLE ROW LEVEL SECURITY;
ALTER TABLE journal_lines FORCE ROW LEVEL SECURITY;
CREATE POLICY journal_lines_tenant ON journal_lines
    USING (tenant_id = current_setting('app.tenant_id')::uuid)
    WITH CHECK (tenant_id = current_setting('app.tenant_id')::uuid);
