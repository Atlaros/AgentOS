-- Published canvas kinds that drive the WhatsApp turn graph (docs/00 item 4).

CREATE TABLE IF NOT EXISTS published_flow_maps (
    tenant_id uuid PRIMARY KEY REFERENCES tenants (id),
    kinds jsonb NOT NULL,
    published_at timestamptz NOT NULL DEFAULT now()
);
