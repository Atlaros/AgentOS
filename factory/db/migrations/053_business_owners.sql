-- Signup owner credentials. Only the hash is stored. Sessions stay in process
-- memory. No RLS: login looks up the email before a tenant session exists.

CREATE TABLE business_owners (
    tenant_id uuid PRIMARY KEY REFERENCES tenants (id),
    email text NOT NULL,
    secret_salt text NOT NULL,
    secret_hash text NOT NULL,
    UNIQUE (email),
    CHECK (position('@' in email) > 1),
    CHECK (length(btrim(secret_salt)) > 0),
    CHECK (length(btrim(secret_hash)) > 0)
);
