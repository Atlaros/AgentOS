-- ADR-012 T2: purchase receipt supplier link + optional received_at

ALTER TABLE purchase_receipts
    ADD COLUMN IF NOT EXISTS supplier_id uuid NULL REFERENCES suppliers (id);

ALTER TABLE purchase_receipts
    ADD COLUMN IF NOT EXISTS received_at timestamptz NOT NULL DEFAULT now();
