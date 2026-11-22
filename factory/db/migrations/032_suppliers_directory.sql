-- ADR-012 T1: supplier directory, variant preferred supplier, reorder threshold exposure

CREATE TABLE IF NOT EXISTS suppliers (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants (id),
    name text NOT NULL,
    contact_name text NOT NULL DEFAULT '',
    phone text NOT NULL DEFAULT '',
    whatsapp text NOT NULL DEFAULT '',
    email text NOT NULL DEFAULT '',
    notes text NOT NULL DEFAULT '',
    payment_terms text NOT NULL DEFAULT 'cash',
    lead_time_days integer NOT NULL DEFAULT 0,
    active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CHECK (length(btrim(name)) > 0),
    CHECK (lead_time_days >= 0)
);

ALTER TABLE suppliers ENABLE ROW LEVEL SECURITY;
ALTER TABLE suppliers FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS suppliers_tenant ON suppliers;
CREATE POLICY suppliers_tenant ON suppliers
    USING (tenant_id = current_setting('app.tenant_id')::uuid)
    WITH CHECK (tenant_id = current_setting('app.tenant_id')::uuid);

ALTER TABLE product_variants
    ADD COLUMN IF NOT EXISTS supplier_id uuid NULL REFERENCES suppliers (id);

ALTER TABLE inventory
    ADD COLUMN IF NOT EXISTS low_stock_threshold integer NOT NULL DEFAULT 1;

CREATE OR REPLACE VIEW agent_catalog_read AS
SELECT
    p.tenant_id,
    p.sku AS product_sku,
    v.sku AS variant_sku,
    p.name,
    p.description,
    c.name AS category,
    v.attributes,
    pr.amount AS price,
    pr.currency,
    i.quantity AS stock,
    v.attributes ->> 'codigo' AS codigo,
    i.low_stock_threshold AS reorder_threshold,
    v.supplier_id
FROM products p
JOIN product_variants v ON v.product_id = p.id AND v.tenant_id = p.tenant_id
JOIN prices pr ON pr.variant_id = v.id AND pr.tenant_id = p.tenant_id
JOIN inventory i ON i.variant_id = v.id AND i.tenant_id = p.tenant_id
LEFT JOIN categories c ON c.id = p.category_id AND c.tenant_id = p.tenant_id;

ALTER VIEW agent_catalog_read SET (security_invoker = true);
