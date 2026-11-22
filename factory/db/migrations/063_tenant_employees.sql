-- Per-business digital employee roster (ADR-026). Catalog roles seed here;
-- clones are rows with is_clone = true. Operator console may list all tenants.

CREATE TABLE tenant_employees (
    tenant_id uuid NOT NULL REFERENCES tenants (id),
    employee_key text NOT NULL,
    base_role text NOT NULL,
    display_name text NOT NULL,
    style text NOT NULL DEFAULT '',
    enabled boolean NOT NULL DEFAULT true,
    is_clone boolean NOT NULL DEFAULT false,
    archived boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, employee_key),
    CHECK (length(btrim(employee_key)) > 0),
    CHECK (length(btrim(base_role)) > 0),
    CHECK (length(btrim(display_name)) > 0),
    CHECK (
        base_role IN (
            'sales',
            'collections',
            'ops',
            'postventa',
            'inventory',
            'catalog_admin',
            'accounting',
            'analyst',
            'suppliers'
        )
    )
);

CREATE INDEX tenant_employees_tenant_enabled_idx
    ON tenant_employees (tenant_id)
    WHERE enabled AND NOT archived;
