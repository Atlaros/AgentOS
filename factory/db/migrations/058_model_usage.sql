-- Cumulative model token totals per business for the operator console.
-- No RLS: the operator list reads every business the same way as tenants.

CREATE TABLE model_usage (
    tenant_id uuid PRIMARY KEY REFERENCES tenants (id),
    tokens bigint NOT NULL DEFAULT 0,
    updated_at timestamptz NOT NULL DEFAULT now(),
    CHECK (tokens >= 0)
);
