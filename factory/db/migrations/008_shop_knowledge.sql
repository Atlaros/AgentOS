-- Tenant shop file: profile, FAQs, policies, voice. Not catalog prices.
CREATE TABLE shop_knowledge (
    tenant_id uuid PRIMARY KEY REFERENCES tenants (id),
    payload jsonb NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE shop_knowledge ENABLE ROW LEVEL SECURITY;
ALTER TABLE shop_knowledge FORCE ROW LEVEL SECURITY;
CREATE POLICY shop_knowledge_tenant ON shop_knowledge
    USING (tenant_id = current_setting('app.tenant_id')::uuid)
    WITH CHECK (tenant_id = current_setting('app.tenant_id')::uuid);
