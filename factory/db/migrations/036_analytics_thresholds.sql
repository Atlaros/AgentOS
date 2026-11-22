-- ADR-013 T1: tenant clocks for Analítica alerts.
-- Stock-low stays on product_variants.reorder_threshold (per variant).

CREATE TABLE IF NOT EXISTS analytics_thresholds (
    tenant_id uuid PRIMARY KEY REFERENCES tenants (id),
    qr_pending_hours integer NOT NULL DEFAULT 24,
    inactive_days integer NOT NULL DEFAULT 30,
    updated_at timestamptz NOT NULL DEFAULT now(),
    CHECK (qr_pending_hours >= 1 AND qr_pending_hours <= 720),
    CHECK (inactive_days >= 1 AND inactive_days <= 3650)
);

ALTER TABLE analytics_thresholds ENABLE ROW LEVEL SECURITY;
ALTER TABLE analytics_thresholds FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS analytics_thresholds_tenant ON analytics_thresholds;
CREATE POLICY analytics_thresholds_tenant ON analytics_thresholds
    USING (tenant_id = current_setting('app.tenant_id')::uuid)
    WITH CHECK (tenant_id = current_setting('app.tenant_id')::uuid);
