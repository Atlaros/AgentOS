-- Idempotent Meta WhatsApp inbound (wamid). Global PK: Meta message ids are unique.
CREATE TABLE IF NOT EXISTS whatsapp_inbound_events (
    message_id text PRIMARY KEY,
    tenant_id uuid REFERENCES tenants (id),
    wa_number text,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS whatsapp_inbound_events_created
    ON whatsapp_inbound_events (created_at);
