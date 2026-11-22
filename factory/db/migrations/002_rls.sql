-- 002 row-level security. Tenant comes from SET app.tenant_id, never from the model.

DO $$
DECLARE
    t text;
BEGIN
    FOREACH t IN ARRAY ARRAY[
        'categories',
        'products',
        'product_variants',
        'prices',
        'inventory',
        'promotions',
        'product_embeddings',
        'customers',
        'customer_preferences',
        'conversations',
        'conversation_messages',
        'carts',
        'cart_items',
        'orders',
        'order_items',
        'payments',
        'deliveries'
    ]
    LOOP
        EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
        EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', t);
        EXECUTE format(
            'CREATE POLICY %I_tenant ON %I USING (tenant_id = current_setting(''app.tenant_id'')::uuid) WITH CHECK (tenant_id = current_setting(''app.tenant_id'')::uuid)',
            t,
            t
        );
    END LOOP;
END $$;
