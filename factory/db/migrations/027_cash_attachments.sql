-- 027 cash movement attachments: metadata only, bytes on disk (ADR-009 T8).

CREATE TABLE cash_attachments (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants (id),
    movement_id uuid NOT NULL REFERENCES cash_movements (id),
    filename text NOT NULL,
    content_type text NOT NULL DEFAULT 'application/octet-stream',
    size_bytes integer NOT NULL,
    storage_key text NOT NULL,
    uploaded_by_name text NOT NULL DEFAULT 'sistema',
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (size_bytes > 0),
    CHECK (length(btrim(filename)) > 0),
    CHECK (length(btrim(storage_key)) > 0)
);

CREATE INDEX IF NOT EXISTS cash_attachments_movement_idx
    ON cash_attachments (tenant_id, movement_id, created_at DESC);

ALTER TABLE cash_attachments ENABLE ROW LEVEL SECURITY;
ALTER TABLE cash_attachments FORCE ROW LEVEL SECURITY;
CREATE POLICY cash_attachments_tenant ON cash_attachments
    USING (tenant_id = current_setting('app.tenant_id')::uuid)
    WITH CHECK (tenant_id = current_setting('app.tenant_id')::uuid);
