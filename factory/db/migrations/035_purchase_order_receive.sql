-- ADR-012 T4: link receipts to purchase orders and track what was paid

ALTER TABLE purchase_receipts
    ADD COLUMN IF NOT EXISTS purchase_order_id uuid NULL REFERENCES purchase_orders (id);

CREATE INDEX IF NOT EXISTS purchase_receipts_purchase_order_idx
    ON purchase_receipts (purchase_order_id);

ALTER TABLE purchase_orders
    ADD COLUMN IF NOT EXISTS payment_status text NOT NULL DEFAULT 'unpaid';

ALTER TABLE purchase_orders
    DROP CONSTRAINT IF EXISTS purchase_orders_payment_status_check;

ALTER TABLE purchase_orders
    ADD CONSTRAINT purchase_orders_payment_status_check
    CHECK (payment_status IN ('unpaid', 'partial', 'paid'));

ALTER TABLE purchase_orders
    ADD COLUMN IF NOT EXISTS amount_paid numeric(12, 2) NOT NULL DEFAULT 0;

ALTER TABLE purchase_orders
    DROP CONSTRAINT IF EXISTS purchase_orders_amount_paid_check;

ALTER TABLE purchase_orders
    ADD CONSTRAINT purchase_orders_amount_paid_check
    CHECK (amount_paid >= 0);

-- Transfer settlements post origin supplier_payment (CxP / Banco) without a cash drawer row
ALTER TABLE journal_entries DROP CONSTRAINT IF EXISTS journal_entries_origin_source_check;

ALTER TABLE journal_entries
    ADD CONSTRAINT journal_entries_origin_source_check
    CHECK (origin_source IN ('cash', 'payment', 'purchase', 'cogs', 'adjustment', 'supplier_payment'));
