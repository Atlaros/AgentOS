-- Outbound replies for a reserved WhatsApp number. No RLS: the owner inbox
-- reads only its tenant after the session already resolved the business.

CREATE TABLE business_reserved_replies (
    id bigserial PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES tenants (id),
    wa_number text NOT NULL,
    body text NOT NULL,
    delivered boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (length(btrim(wa_number)) > 0),
    CHECK (length(btrim(body)) > 0)
);

CREATE INDEX business_reserved_replies_tenant ON business_reserved_replies (tenant_id, id);
