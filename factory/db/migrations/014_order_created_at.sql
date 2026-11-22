-- When the order was opened. Unpaid orders older than the hold window are deleted.

ALTER TABLE orders
    ADD COLUMN IF NOT EXISTS created_at timestamptz NOT NULL DEFAULT now();
