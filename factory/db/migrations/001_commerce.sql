-- 001 commerce schema (greenfield). Local Compose mounts this directory as initdb.d.

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE tenants (
    id uuid PRIMARY KEY,
    name text NOT NULL
);

CREATE TABLE categories (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants (id),
    name text NOT NULL
);

CREATE TABLE products (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants (id),
    sku text NOT NULL,
    name text NOT NULL,
    description text NOT NULL DEFAULT '',
    category_id uuid REFERENCES categories (id),
    UNIQUE (tenant_id, sku)
);

CREATE TABLE product_variants (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants (id),
    product_id uuid NOT NULL REFERENCES products (id),
    sku text NOT NULL,
    attributes jsonb NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE (tenant_id, sku)
);

CREATE TABLE prices (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants (id),
    variant_id uuid NOT NULL REFERENCES product_variants (id),
    amount numeric(12, 2) NOT NULL,
    currency text NOT NULL DEFAULT 'BOB'
);

CREATE TABLE inventory (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants (id),
    variant_id uuid NOT NULL REFERENCES product_variants (id),
    quantity integer NOT NULL DEFAULT 0,
    low_stock_threshold integer NOT NULL DEFAULT 1
);

CREATE TABLE promotions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants (id),
    name text NOT NULL,
    rules jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE product_embeddings (
    variant_id uuid PRIMARY KEY REFERENCES product_variants (id),
    tenant_id uuid NOT NULL REFERENCES tenants (id),
    embedding vector(64)
);

CREATE TABLE customers (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants (id),
    wa_number text NOT NULL,
    name text,
    address text,
    UNIQUE (tenant_id, wa_number)
);

CREATE TABLE customer_preferences (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants (id),
    customer_id uuid NOT NULL REFERENCES customers (id),
    key text NOT NULL,
    value text NOT NULL
);

CREATE TABLE conversations (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants (id),
    customer_id uuid NOT NULL REFERENCES customers (id)
);

CREATE TABLE conversation_messages (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants (id),
    conversation_id uuid NOT NULL REFERENCES conversations (id),
    role text NOT NULL,
    body text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE carts (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants (id),
    customer_id uuid NOT NULL REFERENCES customers (id)
);

CREATE TABLE cart_items (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants (id),
    cart_id uuid NOT NULL REFERENCES carts (id),
    variant_id uuid NOT NULL REFERENCES product_variants (id),
    quantity integer NOT NULL DEFAULT 1
);

CREATE TABLE orders (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants (id),
    customer_id uuid NOT NULL REFERENCES customers (id),
    status text NOT NULL DEFAULT 'open'
);

CREATE TABLE order_items (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants (id),
    order_id uuid NOT NULL REFERENCES orders (id),
    variant_id uuid NOT NULL REFERENCES product_variants (id),
    name text NOT NULL,
    quantity integer NOT NULL,
    unit_price numeric(12, 2) NOT NULL,
    currency text NOT NULL
);

CREATE TABLE payments (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants (id),
    order_id uuid NOT NULL REFERENCES orders (id),
    provider text NOT NULL,
    provider_ref text NOT NULL,
    amount numeric(12, 2) NOT NULL,
    currency text NOT NULL,
    status text NOT NULL,
    qr_payload text NOT NULL,
    UNIQUE (tenant_id, provider_ref)
);

CREATE TABLE deliveries (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants (id),
    order_id uuid NOT NULL REFERENCES orders (id),
    address text NOT NULL,
    recipient_name text NOT NULL
);

CREATE VIEW agent_catalog_read AS
SELECT
    p.tenant_id,
    p.sku AS product_sku,
    v.sku AS variant_sku,
    p.name,
    p.description,
    c.name AS category,
    v.attributes,
    pr.amount AS price,
    pr.currency,
    i.quantity AS stock,
    v.attributes ->> 'codigo' AS codigo
FROM products p
JOIN product_variants v ON v.product_id = p.id AND v.tenant_id = p.tenant_id
JOIN prices pr ON pr.variant_id = v.id AND pr.tenant_id = p.tenant_id
JOIN inventory i ON i.variant_id = v.id AND i.tenant_id = p.tenant_id
LEFT JOIN categories c ON c.id = p.category_id AND c.tenant_id = p.tenant_id;
