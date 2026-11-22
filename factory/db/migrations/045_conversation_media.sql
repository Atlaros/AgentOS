-- 045 conversation media links (ADR-015 Fase C).

CREATE TABLE conversation_media (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants (id),
    conversation_id uuid NOT NULL REFERENCES conversations (id) ON DELETE CASCADE,
    asset_id uuid REFERENCES media_assets (id) ON DELETE SET NULL,
    provider_ref text,
    message_index integer,
    direction text NOT NULL,
    status text NOT NULL DEFAULT 'ready',
    kind text NOT NULL,
    mime text,
    filename text,
    size_bytes integer,
    error text,
    uploaded_by text,
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (direction IN ('inbound', 'outbound')),
    CHECK (status IN ('pending', 'ready', 'failed')),
    CHECK (kind IN ('image', 'audio', 'video', 'document'))
);

CREATE INDEX IF NOT EXISTS conversation_media_conversation_idx
    ON conversation_media (tenant_id, conversation_id, created_at);

CREATE UNIQUE INDEX IF NOT EXISTS conversation_media_provider_ref_uq
    ON conversation_media (tenant_id, provider_ref)
    WHERE provider_ref IS NOT NULL AND length(btrim(provider_ref)) > 0;

CREATE UNIQUE INDEX IF NOT EXISTS media_assets_provider_ref_uq
    ON media_assets (tenant_id, provider_ref)
    WHERE provider_ref IS NOT NULL AND length(btrim(provider_ref)) > 0;

ALTER TABLE conversation_media ENABLE ROW LEVEL SECURITY;
ALTER TABLE conversation_media FORCE ROW LEVEL SECURITY;
CREATE POLICY conversation_media_tenant ON conversation_media
    USING (tenant_id = current_setting('app.tenant_id')::uuid)
    WITH CHECK (tenant_id = current_setting('app.tenant_id')::uuid);
