-- ADR-011 Fase 3: COGS/adjustment origins + purchase payment_method

ALTER TABLE journal_entries DROP CONSTRAINT IF EXISTS journal_entries_origin_source_check;

ALTER TABLE journal_entries
    ADD CONSTRAINT journal_entries_origin_source_check
    CHECK (origin_source IN ('cash', 'payment', 'purchase', 'cogs', 'adjustment'));

ALTER TABLE purchase_receipts
    ADD COLUMN IF NOT EXISTS payment_method text NOT NULL DEFAULT 'cash';

ALTER TABLE purchase_receipts DROP CONSTRAINT IF EXISTS purchase_receipts_payment_method_check;

ALTER TABLE purchase_receipts
    ADD CONSTRAINT purchase_receipts_payment_method_check
    CHECK (payment_method IN ('cash', 'credit'));
