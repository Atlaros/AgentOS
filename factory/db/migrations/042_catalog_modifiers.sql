-- Catalog price extras and the selection stored on an order line.

ALTER TABLE order_items
    ADD COLUMN IF NOT EXISTS options jsonb NOT NULL DEFAULT '[]'::jsonb;

CREATE TABLE IF NOT EXISTS catalog_modifiers (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants (id),
    name text NOT NULL,
    price_delta numeric(12, 2) NOT NULL,
    currency text NOT NULL DEFAULT 'BOB',
    created_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE catalog_modifiers ENABLE ROW LEVEL SECURITY;
ALTER TABLE catalog_modifiers FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS catalog_modifiers_tenant ON catalog_modifiers;
CREATE POLICY catalog_modifiers_tenant ON catalog_modifiers
    USING (tenant_id = current_setting('app.tenant_id')::uuid)
    WITH CHECK (tenant_id = current_setting('app.tenant_id')::uuid);
