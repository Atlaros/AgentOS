-- Conversation summary columns. customer_preferences already exists (001).
ALTER TABLE conversations
    ADD COLUMN IF NOT EXISTS summary_text text,
    ADD COLUMN IF NOT EXISTS summary_msg_count integer NOT NULL DEFAULT 0;

CREATE UNIQUE INDEX IF NOT EXISTS customer_preferences_tenant_customer_key
    ON customer_preferences (tenant_id, customer_id, key);
