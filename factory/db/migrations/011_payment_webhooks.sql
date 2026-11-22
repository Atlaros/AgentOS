-- Idempotent payment webhook events (Baneco / fake).
CREATE TABLE IF NOT EXISTS payment_webhook_events (
    event_id text PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES tenants (id),
    provider text NOT NULL,
    provider_ref text NOT NULL,
    state text NOT NULL,
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE payment_webhook_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE payment_webhook_events FORCE ROW LEVEL SECURITY;
CREATE POLICY payment_webhook_events_tenant ON payment_webhook_events
    USING (tenant_id = current_setting('app.tenant_id')::uuid)
    WITH CHECK (tenant_id = current_setting('app.tenant_id')::uuid);

CREATE INDEX IF NOT EXISTS payment_webhook_events_ref
    ON payment_webhook_events (tenant_id, provider_ref);
