-- Rubro and enabled modules live on the tenant row. No UI in this phase.

ALTER TABLE tenants
    ADD COLUMN IF NOT EXISTS industry text NOT NULL DEFAULT 'closet';

ALTER TABLE tenants
    ADD COLUMN IF NOT EXISTS enabled_modules jsonb NOT NULL DEFAULT '[]'::jsonb;
