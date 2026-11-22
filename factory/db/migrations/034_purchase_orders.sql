-- ADR-012 T3: draft purchase orders + lines (receive/lifecycle in T4)

CREATE TABLE IF NOT EXISTS purchase_orders (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants (id),
    supplier_id uuid NOT NULL REFERENCES suppliers (id),
    status text NOT NULL DEFAULT 'draft',
    notes text NOT NULL DEFAULT '',
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CHECK (status IN ('draft', 'sent', 'partially_received', 'received', 'cancelled'))
);

CREATE TABLE IF NOT EXISTS purchase_order_lines (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants (id),
    purchase_order_id uuid NOT NULL REFERENCES purchase_orders (id) ON DELETE CASCADE,
    variant_sku text NOT NULL,
    quantity_ordered integer NOT NULL,
    quantity_received integer NOT NULL DEFAULT 0,
    unit_cost numeric(12, 2) NULL,
    currency text NOT NULL DEFAULT 'BOB',
    CHECK (quantity_ordered > 0),
    CHECK (quantity_received >= 0)
);

ALTER TABLE purchase_orders ENABLE ROW LEVEL SECURITY;
ALTER TABLE purchase_orders FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS purchase_orders_tenant ON purchase_orders;
CREATE POLICY purchase_orders_tenant ON purchase_orders
    USING (tenant_id = current_setting('app.tenant_id')::uuid)
    WITH CHECK (tenant_id = current_setting('app.tenant_id')::uuid);

ALTER TABLE purchase_order_lines ENABLE ROW LEVEL SECURITY;
ALTER TABLE purchase_order_lines FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS purchase_order_lines_tenant ON purchase_order_lines;
CREATE POLICY purchase_order_lines_tenant ON purchase_order_lines
    USING (tenant_id = current_setting('app.tenant_id')::uuid)
    WITH CHECK (tenant_id = current_setting('app.tenant_id')::uuid);
