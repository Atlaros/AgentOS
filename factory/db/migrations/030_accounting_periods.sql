-- Accounting period close (ADR-011 Fase 2). Blocks journal posts in closed ranges.

CREATE TABLE accounting_periods (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants (id),
    date_from date NOT NULL,
    date_to date NOT NULL,
    status text NOT NULL,
    closed_at timestamptz,
    closed_by_name text,
    CHECK (status IN ('open', 'closed')),
    CHECK (date_from <= date_to),
    UNIQUE (tenant_id, date_from, date_to)
);

CREATE INDEX accounting_periods_tenant_status_idx
    ON accounting_periods (tenant_id, status);

ALTER TABLE accounting_periods ENABLE ROW LEVEL SECURITY;
ALTER TABLE accounting_periods FORCE ROW LEVEL SECURITY;
CREATE POLICY accounting_periods_tenant ON accounting_periods
    USING (tenant_id = current_setting('app.tenant_id')::uuid)
    WITH CHECK (tenant_id = current_setting('app.tenant_id')::uuid);
