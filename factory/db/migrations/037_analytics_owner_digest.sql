-- ADR-013 T3: opt-in owner WhatsApp digest, one row per La Paz calendar day.

ALTER TABLE analytics_thresholds
    ADD COLUMN IF NOT EXISTS digest_whatsapp_enabled boolean NOT NULL DEFAULT false;

CREATE TABLE IF NOT EXISTS analytics_owner_digest_log (
    tenant_id uuid NOT NULL REFERENCES tenants (id),
    business_date date NOT NULL,
    sent_at timestamptz NOT NULL DEFAULT now(),
    alert_type_count integer NOT NULL,
    PRIMARY KEY (tenant_id, business_date),
    CHECK (alert_type_count >= 0)
);

ALTER TABLE analytics_owner_digest_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE analytics_owner_digest_log FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS analytics_owner_digest_log_tenant ON analytics_owner_digest_log;
CREATE POLICY analytics_owner_digest_log_tenant ON analytics_owner_digest_log
    USING (tenant_id = current_setting('app.tenant_id')::uuid)
    WITH CHECK (tenant_id = current_setting('app.tenant_id')::uuid);
