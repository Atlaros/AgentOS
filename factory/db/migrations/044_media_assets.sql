-- 044 media assets + product gallery links (ADR-015 Fase A).

CREATE TABLE media_assets (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants (id),
    kind text NOT NULL DEFAULT 'image',
    mime text NOT NULL,
    size_bytes integer NOT NULL,
    storage_key text NOT NULL,
    thumb_key text,
    medium_key text,
    origin text NOT NULL,
    uploaded_by text,
    provider_ref text,
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (kind IN ('image', 'audio', 'video', 'document')),
    CHECK (
        origin IN (
            'catalog',
            'chat_inbound',
            'chat_outbound',
            'receipt',
            'cash_attachment'
        )
    ),
    CHECK (size_bytes > 0),
    CHECK (length(btrim(storage_key)) > 0),
    CHECK (length(btrim(mime)) > 0)
);

CREATE INDEX IF NOT EXISTS media_assets_tenant_created_idx
    ON media_assets (tenant_id, created_at DESC);

CREATE TABLE product_media (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants (id),
    product_sku text NOT NULL,
    asset_id uuid NOT NULL REFERENCES media_assets (id) ON DELETE CASCADE,
    is_primary boolean NOT NULL DEFAULT false,
    sort_order integer NOT NULL DEFAULT 0,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, product_sku, asset_id),
    CHECK (length(btrim(product_sku)) > 0)
);

CREATE INDEX IF NOT EXISTS product_media_product_idx
    ON product_media (tenant_id, product_sku, sort_order, created_at);

-- At most one primary per product (partial unique).
CREATE UNIQUE INDEX IF NOT EXISTS product_media_one_primary_idx
    ON product_media (tenant_id, product_sku)
    WHERE is_primary;

ALTER TABLE media_assets ENABLE ROW LEVEL SECURITY;
ALTER TABLE media_assets FORCE ROW LEVEL SECURITY;
CREATE POLICY media_assets_tenant ON media_assets
    USING (tenant_id = current_setting('app.tenant_id')::uuid)
    WITH CHECK (tenant_id = current_setting('app.tenant_id')::uuid);

ALTER TABLE product_media ENABLE ROW LEVEL SECURITY;
ALTER TABLE product_media FORCE ROW LEVEL SECURITY;
CREATE POLICY product_media_tenant ON product_media
    USING (tenant_id = current_setting('app.tenant_id')::uuid)
    WITH CHECK (tenant_id = current_setting('app.tenant_id')::uuid);
