-- Per-business autonomy overrides. Only levels at or below the template floor.
-- No RLS: the operator console reads every business the same way as tenants.

CREATE TABLE tenant_autonomy (
    tenant_id uuid NOT NULL REFERENCES tenants (id),
    action text NOT NULL,
    level text NOT NULL,
    PRIMARY KEY (tenant_id, action),
    CHECK (length(btrim(action)) > 0),
    CHECK (level IN ('never', 'recommend', 'approval', 'within_limits'))
);
