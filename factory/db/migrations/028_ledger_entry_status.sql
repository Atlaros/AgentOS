-- 028 ledger entry status: soft-voided cash stays auditable but stops counting (ADR-010).

ALTER TABLE ledger_entries
    ADD COLUMN IF NOT EXISTS status text NOT NULL DEFAULT 'recorded';

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'ledger_entries_status_check'
    ) THEN
        ALTER TABLE ledger_entries
            ADD CONSTRAINT ledger_entries_status_check
            CHECK (status IN ('recorded', 'voided'));
    END IF;
END $$;
