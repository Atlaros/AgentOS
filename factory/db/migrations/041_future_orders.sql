-- Agent orders for a later day. Stock stays until fulfill_on.
ALTER TABLE orders
  ADD COLUMN IF NOT EXISTS fulfill_on date,
  ADD COLUMN IF NOT EXISTS stock_applied boolean NOT NULL DEFAULT false;
