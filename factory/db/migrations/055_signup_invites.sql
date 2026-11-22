-- One-time public signup codes. No RLS: the operator mints them before a
-- tenant exists. Used codes stay for audit. Only unused ones unlock signup.

CREATE TABLE signup_invites (
    code text PRIMARY KEY,
    created_at timestamptz NOT NULL DEFAULT now(),
    used_at timestamptz,
    CHECK (length(btrim(code)) > 0)
);

CREATE INDEX signup_invites_unused ON signup_invites (code) WHERE used_at IS NULL;
