-- 003 conversation working state + seed uniqueness.

ALTER TABLE conversations
    ADD COLUMN IF NOT EXISTS working_state jsonb NOT NULL DEFAULT '{}'::jsonb;

CREATE UNIQUE INDEX IF NOT EXISTS categories_tenant_name ON categories (tenant_id, name);
CREATE UNIQUE INDEX IF NOT EXISTS prices_tenant_variant ON prices (tenant_id, variant_id);
CREATE UNIQUE INDEX IF NOT EXISTS inventory_tenant_variant ON inventory (tenant_id, variant_id);
