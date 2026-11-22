-- 022 cash drawer sessions (turno de caja). One open session per tenant.

CREATE TABLE cash_sessions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants (id),
    status text NOT NULL,
    opening_float numeric(12, 2) NOT NULL,
    currency text NOT NULL DEFAULT 'BOB',
    opened_by_name text NOT NULL,
    opened_by_id uuid REFERENCES panel_users (id),
    opened_at timestamptz NOT NULL DEFAULT now(),
    closed_at timestamptz,
    closed_by_name text,
    closed_by_id uuid REFERENCES panel_users (id),
    counted_cash numeric(12, 2),
    expected_cash numeric(12, 2),
    difference numeric(12, 2),
    close_note text,
    CHECK (status IN ('open', 'closed')),
    CHECK (opening_float >= 0),
    CHECK (length(btrim(opened_by_name)) > 0)
);

CREATE UNIQUE INDEX cash_sessions_one_open_per_tenant
    ON cash_sessions (tenant_id)
    WHERE status = 'open';

ALTER TABLE cash_movements
    ADD COLUMN session_id uuid REFERENCES cash_sessions (id);

ALTER TABLE cash_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE cash_sessions FORCE ROW LEVEL SECURITY;
CREATE POLICY cash_sessions_tenant ON cash_sessions
    USING (tenant_id = current_setting('app.tenant_id')::uuid)
    WITH CHECK (tenant_id = current_setting('app.tenant_id')::uuid);
