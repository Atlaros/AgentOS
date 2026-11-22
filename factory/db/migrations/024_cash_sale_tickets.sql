-- 024 walk-in cash sale tickets (mostrador). Ticket is not a chat Order (ADR-009 T3).

CREATE TABLE cash_sale_tickets (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants (id),
    number text NOT NULL,
    status text NOT NULL DEFAULT 'recorded',
    method text NOT NULL DEFAULT 'cash',
    total numeric(12, 2) NOT NULL,
    currency text NOT NULL DEFAULT 'BOB',
    lines jsonb NOT NULL DEFAULT '[]'::jsonb,
    session_id uuid REFERENCES cash_sessions (id),
    movement_id uuid,
    recorded_by_name text NOT NULL DEFAULT 'sistema',
    recorded_by_id uuid REFERENCES panel_users (id),
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (status IN ('recorded', 'voided')),
    CHECK (total > 0),
    CHECK (length(btrim(number)) > 0),
    UNIQUE (tenant_id, number)
);

ALTER TABLE cash_movements
    ADD COLUMN IF NOT EXISTS ticket_id uuid;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'cash_movements_ticket_id_fkey'
    ) THEN
        ALTER TABLE cash_movements
            ADD CONSTRAINT cash_movements_ticket_id_fkey
            FOREIGN KEY (ticket_id) REFERENCES cash_sale_tickets (id);
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'cash_sale_tickets_movement_id_fkey'
    ) THEN
        ALTER TABLE cash_sale_tickets
            ADD CONSTRAINT cash_sale_tickets_movement_id_fkey
            FOREIGN KEY (movement_id) REFERENCES cash_movements (id);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS cash_sale_tickets_tenant_created_idx
    ON cash_sale_tickets (tenant_id, created_at DESC);

ALTER TABLE cash_sale_tickets ENABLE ROW LEVEL SECURITY;
ALTER TABLE cash_sale_tickets FORCE ROW LEVEL SECURITY;
CREATE POLICY cash_sale_tickets_tenant ON cash_sale_tickets
    USING (tenant_id = current_setting('app.tenant_id')::uuid)
    WITH CHECK (tenant_id = current_setting('app.tenant_id')::uuid);
