-- WhatsApp inbound claims are unique per tenant. Pilot fills any legacy nulls.
-- Pilot tenant id matches packages/domain PILOT_TENANT_ID.

INSERT INTO tenants (id, name)
VALUES ('dddddddd-dddd-dddd-dddd-dddddddddddd', 'Pilot')
ON CONFLICT (id) DO NOTHING;

UPDATE whatsapp_inbound_events
SET tenant_id = 'dddddddd-dddd-dddd-dddd-dddddddddddd'
WHERE tenant_id IS NULL;

ALTER TABLE whatsapp_inbound_events
    ALTER COLUMN tenant_id SET NOT NULL;

ALTER TABLE whatsapp_inbound_events DROP CONSTRAINT whatsapp_inbound_events_pkey;

ALTER TABLE whatsapp_inbound_events
    ADD PRIMARY KEY (tenant_id, message_id);

ALTER TABLE whatsapp_inbound_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE whatsapp_inbound_events FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS whatsapp_inbound_events_tenant ON whatsapp_inbound_events;
CREATE POLICY whatsapp_inbound_events_tenant ON whatsapp_inbound_events
    USING (tenant_id = current_setting('app.tenant_id')::uuid)
    WITH CHECK (tenant_id = current_setting('app.tenant_id')::uuid);

CREATE INDEX IF NOT EXISTS whatsapp_inbound_events_message
    ON whatsapp_inbound_events (message_id);
