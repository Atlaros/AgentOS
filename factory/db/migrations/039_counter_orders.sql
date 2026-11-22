-- Counter sales are orders with origin=counter. Chat orders stay origin=agent.
-- Open tables keep a label. The ticket points at the order it charged.

ALTER TABLE orders
  ADD COLUMN IF NOT EXISTS origin text NOT NULL DEFAULT 'agent',
  ADD COLUMN IF NOT EXISTS table_label text NOT NULL DEFAULT '';

ALTER TABLE orders DROP CONSTRAINT IF EXISTS orders_origin_check;
ALTER TABLE orders
  ADD CONSTRAINT orders_origin_check CHECK (origin IN ('agent', 'counter'));

ALTER TABLE cash_sale_tickets
  ADD COLUMN IF NOT EXISTS order_id uuid REFERENCES orders (id);
