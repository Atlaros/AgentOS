-- Open owner panel sessions. The bearer token is stored so a restart can
-- restore the same session. No RLS: lookup happens before a tenant session.

CREATE TABLE owner_sessions (
    token text PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES tenants (id),
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (length(btrim(token)) > 0)
);

CREATE INDEX owner_sessions_tenant ON owner_sessions (tenant_id);
