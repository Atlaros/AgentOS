-- Owner reminder notices. A notice is not a payment and not a sale.

CREATE TABLE reminders (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants (id),
    customer_id uuid NOT NULL REFERENCES customers (id),
    kind text NOT NULL,
    body text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    sent_at timestamptz,
    CHECK (kind IN ('follow_up', 'repurchase', 'collections')),
    CHECK (length(btrim(body)) > 0)
);

CREATE UNIQUE INDEX reminders_open_kind
    ON reminders (tenant_id, customer_id, kind)
    WHERE sent_at IS NULL;

ALTER TABLE reminders ENABLE ROW LEVEL SECURITY;
ALTER TABLE reminders FORCE ROW LEVEL SECURITY;
CREATE POLICY reminders_tenant ON reminders
    USING (tenant_id = current_setting('app.tenant_id')::uuid)
    WITH CHECK (tenant_id = current_setting('app.tenant_id')::uuid);
