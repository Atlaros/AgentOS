-- 023 cash movement metadata: category, method, actor, soft void (ADR-009 T2).

ALTER TABLE cash_movements
    ADD COLUMN IF NOT EXISTS category text NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS method text NOT NULL DEFAULT 'cash',
    ADD COLUMN IF NOT EXISTS status text NOT NULL DEFAULT 'recorded',
    ADD COLUMN IF NOT EXISTS recorded_by_name text NOT NULL DEFAULT 'sistema',
    ADD COLUMN IF NOT EXISTS recorded_by_id uuid REFERENCES panel_users (id),
    ADD COLUMN IF NOT EXISTS void_reason text,
    ADD COLUMN IF NOT EXISTS voided_by_name text,
    ADD COLUMN IF NOT EXISTS voided_by_id uuid REFERENCES panel_users (id),
    ADD COLUMN IF NOT EXISTS voided_at timestamptz;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'cash_movements_status_check'
    ) THEN
        ALTER TABLE cash_movements
            ADD CONSTRAINT cash_movements_status_check
            CHECK (status IN ('recorded', 'voided'));
    END IF;
END $$;
