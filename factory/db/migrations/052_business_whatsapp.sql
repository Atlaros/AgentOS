-- A business WhatsApp number and its own Meta token. No RLS: the webhook
-- resolves the tenant from the phone before a session exists. The process
-- token is refused before a row is written.

CREATE TABLE business_whatsapp (
    tenant_id uuid PRIMARY KEY REFERENCES tenants (id),
    phone_number_id text NOT NULL,
    access_token text NOT NULL DEFAULT '',
    UNIQUE (phone_number_id),
    CHECK (phone_number_id ~ '^[0-9]+$')
);
