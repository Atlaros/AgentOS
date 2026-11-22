-- Ticket discount is one amount per charge. Line prices stay catalog prices.
ALTER TABLE cash_sale_tickets
    ADD COLUMN IF NOT EXISTS discount_amount numeric(12, 2) NOT NULL DEFAULT 0;
