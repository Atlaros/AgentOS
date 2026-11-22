-- Successful public signup hits by client IP. No RLS: the cap is checked
-- before a tenant exists. Old rows outside the window are ignored by the app.

CREATE TABLE signup_rate_hits (
    id bigserial PRIMARY KEY,
    client_ip text NOT NULL,
    hit_at timestamptz NOT NULL DEFAULT now(),
    CHECK (length(btrim(client_ip)) > 0)
);

CREATE INDEX signup_rate_hits_ip_time ON signup_rate_hits (client_ip, hit_at);
