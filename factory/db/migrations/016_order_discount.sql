-- Discount and hold window live on the reservation, same numbers as the QR.
ALTER TABLE orders
    ADD COLUMN IF NOT EXISTS discount_amount numeric(12, 2) NOT NULL DEFAULT 0;

ALTER TABLE orders
    ADD COLUMN IF NOT EXISTS hold_minutes integer NOT NULL DEFAULT 15;
