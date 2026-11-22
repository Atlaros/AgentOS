-- ADR-014 slice C: who downloaded which report, and for which period.

CREATE TABLE IF NOT EXISTS report_download_log (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants (id),
    report_id text NOT NULL,
    period_id text NOT NULL DEFAULT '',
    date_from timestamptz,
    date_to timestamptz,
    format text NOT NULL,
    actor_name text NOT NULL,
    actor_user_id uuid,
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (length(btrim(report_id)) > 0),
    CHECK (length(btrim(format)) > 0),
    CHECK (length(btrim(actor_name)) > 0)
);

CREATE INDEX IF NOT EXISTS report_download_log_tenant_created
    ON report_download_log (tenant_id, created_at DESC);

ALTER TABLE report_download_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE report_download_log FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS report_download_log_tenant ON report_download_log;
CREATE POLICY report_download_log_tenant ON report_download_log
    USING (tenant_id = current_setting('app.tenant_id')::uuid)
    WITH CHECK (tenant_id = current_setting('app.tenant_id')::uuid);
