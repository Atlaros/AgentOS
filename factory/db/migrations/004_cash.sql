-- 004 cash drawer (caja). Not customer QR payments.

CREATE TABLE cash_movements (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants (id),
    direction text NOT NULL,
    amount numeric(12, 2) NOT NULL,
    currency text NOT NULL DEFAULT 'BOB',
    reason text NOT NULL DEFAULT '',
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (direction IN ('in', 'out')),
    CHECK (amount > 0)
);

ALTER TABLE cash_movements ENABLE ROW LEVEL SECURITY;
ALTER TABLE cash_movements FORCE ROW LEVEL SECURITY;
CREATE POLICY cash_movements_tenant ON cash_movements
    USING (tenant_id = current_setting('app.tenant_id')::uuid)
    WITH CHECK (tenant_id = current_setting('app.tenant_id')::uuid);
