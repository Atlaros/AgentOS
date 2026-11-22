-- 046 entity media links for order / purchase-order attachments (ADR-015 Fase E).

ALTER TABLE media_assets DROP CONSTRAINT IF EXISTS media_assets_origin_check;
ALTER TABLE media_assets ADD CONSTRAINT media_assets_origin_check
    CHECK (
        origin IN (
            'catalog',
            'chat_inbound',
            'chat_outbound',
            'receipt',
            'cash_attachment',
            'order_attachment',
            'purchase_attachment'
        )
    );

CREATE TABLE entity_media (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants (id),
    entity_type text NOT NULL,
    entity_id uuid NOT NULL,
    asset_id uuid NOT NULL REFERENCES media_assets (id) ON DELETE CASCADE,
    filename text NOT NULL,
    kind text NOT NULL,
    mime text NOT NULL,
    size_bytes integer NOT NULL,
    note text,
    uploaded_by text,
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (entity_type IN ('order', 'purchase_order')),
    CHECK (kind IN ('image', 'document')),
    CHECK (size_bytes > 0),
    CHECK (length(btrim(filename)) > 0),
    CHECK (length(btrim(mime)) > 0)
);

CREATE INDEX IF NOT EXISTS entity_media_entity_idx
    ON entity_media (tenant_id, entity_type, entity_id, created_at);

ALTER TABLE entity_media ENABLE ROW LEVEL SECURITY;
ALTER TABLE entity_media FORCE ROW LEVEL SECURITY;
CREATE POLICY entity_media_tenant ON entity_media
    USING (tenant_id = current_setting('app.tenant_id')::uuid)
    WITH CHECK (tenant_id = current_setting('app.tenant_id')::uuid);
