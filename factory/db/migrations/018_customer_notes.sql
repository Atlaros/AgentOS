-- Owner notes on a customer. Purchases and chats stay in orders and conversations.

CREATE TABLE customer_notes (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants (id),
    customer_id uuid NOT NULL REFERENCES customers (id),
    body text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (length(btrim(body)) > 0)
);

ALTER TABLE customer_notes ENABLE ROW LEVEL SECURITY;
ALTER TABLE customer_notes FORCE ROW LEVEL SECURITY;
CREATE POLICY customer_notes_tenant ON customer_notes
    USING (tenant_id = current_setting('app.tenant_id')::uuid)
    WITH CHECK (tenant_id = current_setting('app.tenant_id')::uuid);
