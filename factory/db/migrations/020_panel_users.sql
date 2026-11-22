-- Humans of the owner panel. Distinct from digital employees and from agent trace.

CREATE TABLE panel_users (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants (id),
    name text NOT NULL,
    email text NOT NULL,
    role text NOT NULL,
    secret_salt text NOT NULL,
    secret_hash text NOT NULL,
    active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (role IN ('owner', 'staff')),
    CHECK (length(btrim(name)) > 0),
    CHECK (position('@' in email) > 1),
    UNIQUE (tenant_id, email)
);

CREATE TABLE human_audit_events (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants (id),
    actor_id uuid REFERENCES panel_users (id),
    actor_name text NOT NULL,
    actor_role text NOT NULL,
    method text NOT NULL,
    path text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (actor_role IN ('owner', 'staff')),
    CHECK (length(btrim(actor_name)) > 0)
);

ALTER TABLE panel_users ENABLE ROW LEVEL SECURITY;
ALTER TABLE panel_users FORCE ROW LEVEL SECURITY;
CREATE POLICY panel_users_tenant ON panel_users
    USING (tenant_id = current_setting('app.tenant_id')::uuid)
    WITH CHECK (tenant_id = current_setting('app.tenant_id')::uuid);

ALTER TABLE human_audit_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE human_audit_events FORCE ROW LEVEL SECURITY;
CREATE POLICY human_audit_events_tenant ON human_audit_events
    USING (tenant_id = current_setting('app.tenant_id')::uuid)
    WITH CHECK (tenant_id = current_setting('app.tenant_id')::uuid);
