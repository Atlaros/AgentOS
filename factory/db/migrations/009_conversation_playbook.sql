-- Conversation playbook (behavior hints). Separate from product_embeddings / shop_knowledge.
-- Examples never become catalog or policy facts.
CREATE TABLE IF NOT EXISTS conversation_playbook (
    tenant_id uuid NOT NULL REFERENCES tenants (id),
    pattern_id text NOT NULL,
    intent text NOT NULL,
    situation text NOT NULL,
    next_action text NOT NULL,
    skill text NOT NULL,
    capability text NOT NULL,
    payload jsonb NOT NULL,
    embed_text text NOT NULL,
    embedding vector(1024) NOT NULL,
    content_sha text NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, pattern_id)
);

CREATE INDEX IF NOT EXISTS conversation_playbook_cosine_hnsw
    ON conversation_playbook USING hnsw (embedding vector_cosine_ops);

ALTER TABLE conversation_playbook ENABLE ROW LEVEL SECURITY;
ALTER TABLE conversation_playbook FORCE ROW LEVEL SECURITY;
CREATE POLICY conversation_playbook_tenant ON conversation_playbook
    USING (tenant_id = current_setting('app.tenant_id')::uuid)
    WITH CHECK (tenant_id = current_setting('app.tenant_id')::uuid);
