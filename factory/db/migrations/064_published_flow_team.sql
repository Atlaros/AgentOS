-- Employee→module assignments on the published canvas (ADR-027).

ALTER TABLE published_flow_maps
    ADD COLUMN IF NOT EXISTS team jsonb NOT NULL DEFAULT '[]'::jsonb;
