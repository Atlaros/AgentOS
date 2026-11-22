-- QR can exist before the order. The order is created when the bank confirms.

ALTER TABLE payments ALTER COLUMN order_id DROP NOT NULL;
ALTER TABLE payments ADD COLUMN IF NOT EXISTS variant_sku text;
ALTER TABLE payments ADD COLUMN IF NOT EXISTS customer_id uuid;
ALTER TABLE payments ADD COLUMN IF NOT EXISTS created_at timestamptz NOT NULL DEFAULT now();
