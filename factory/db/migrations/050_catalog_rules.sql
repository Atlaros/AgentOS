-- Operator catalog rules. No RLS: the console lists every business, same as tenants.

CREATE TABLE catalog_rules (
    id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES tenants (id),
    when_event text NOT NULL,
    if_threshold text NOT NULL,
    then_action text NOT NULL,
    status text NOT NULL DEFAULT 'draft',
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (status IN ('draft', 'published')),
    CHECK (length(btrim(when_event)) > 0),
    CHECK (length(btrim(if_threshold)) > 0),
    CHECK (length(btrim(then_action)) > 0)
);

CREATE INDEX catalog_rules_tenant ON catalog_rules (tenant_id);
