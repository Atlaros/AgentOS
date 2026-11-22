-- Operating ledger and invoice documents. An issued invoice does not write payments.

CREATE TABLE ledger_entries (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants (id),
    source text NOT NULL,
    source_id uuid NOT NULL,
    direction text NOT NULL,
    amount numeric(12, 2) NOT NULL,
    currency text NOT NULL DEFAULT 'BOB',
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (source IN ('payment', 'cash', 'purchase')),
    CHECK (direction IN ('in', 'out')),
    CHECK (amount > 0),
    UNIQUE (tenant_id, source, source_id)
);

CREATE TABLE purchase_receipts (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants (id),
    variant_sku text NOT NULL,
    quantity integer NOT NULL,
    unit_cost numeric(12, 2) NOT NULL,
    currency text NOT NULL DEFAULT 'BOB',
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (quantity > 0),
    CHECK (unit_cost > 0)
);

CREATE TABLE invoice_documents (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants (id),
    order_id uuid REFERENCES orders (id),
    status text NOT NULL,
    amount numeric(12, 2) NOT NULL,
    currency text NOT NULL DEFAULT 'BOB',
    external_ref text NOT NULL DEFAULT '',
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (status IN ('draft', 'exported', 'issued', 'failed')),
    CHECK (amount >= 0)
);

ALTER TABLE ledger_entries ENABLE ROW LEVEL SECURITY;
ALTER TABLE ledger_entries FORCE ROW LEVEL SECURITY;
CREATE POLICY ledger_entries_tenant ON ledger_entries
    USING (tenant_id = current_setting('app.tenant_id')::uuid)
    WITH CHECK (tenant_id = current_setting('app.tenant_id')::uuid);

ALTER TABLE purchase_receipts ENABLE ROW LEVEL SECURITY;
ALTER TABLE purchase_receipts FORCE ROW LEVEL SECURITY;
CREATE POLICY purchase_receipts_tenant ON purchase_receipts
    USING (tenant_id = current_setting('app.tenant_id')::uuid)
    WITH CHECK (tenant_id = current_setting('app.tenant_id')::uuid);

ALTER TABLE invoice_documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE invoice_documents FORCE ROW LEVEL SECURITY;
CREATE POLICY invoice_documents_tenant ON invoice_documents
    USING (tenant_id = current_setting('app.tenant_id')::uuid)
    WITH CHECK (tenant_id = current_setting('app.tenant_id')::uuid);
