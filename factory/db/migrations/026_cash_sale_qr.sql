-- 026 walk-in QR tickets (mostrador Baneco/fake). pending_qr until adapter confirms (ADR-009 T7).

ALTER TABLE cash_sale_tickets
    ADD COLUMN IF NOT EXISTS payment_id uuid REFERENCES payments (id),
    ADD COLUMN IF NOT EXISTS provider_ref text;

ALTER TABLE cash_sale_tickets
    DROP CONSTRAINT IF EXISTS cash_sale_tickets_status_check;

ALTER TABLE cash_sale_tickets
    ADD CONSTRAINT cash_sale_tickets_status_check
    CHECK (status IN ('recorded', 'voided', 'pending_qr'));

CREATE INDEX IF NOT EXISTS cash_sale_tickets_payment_id_idx
    ON cash_sale_tickets (tenant_id, payment_id)
    WHERE payment_id IS NOT NULL;
