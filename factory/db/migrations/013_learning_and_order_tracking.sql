-- 013 learning loop + public order number + delivery confirmation (owner UI).

-- Public order ref for the customer (tracking / follow-up).
ALTER TABLE orders
    ADD COLUMN IF NOT EXISTS public_number text,
    ADD COLUMN IF NOT EXISTS delivered_at timestamptz,
    ADD COLUMN IF NOT EXISTS delivered_by text;

CREATE UNIQUE INDEX IF NOT EXISTS orders_tenant_public_number
    ON orders (tenant_id, public_number)
    WHERE public_number IS NOT NULL;

-- Backfill existing rows with a stable short public number from id.
UPDATE orders
SET public_number = 'AC-' || upper(substr(replace(id::text, '-', ''), 1, 8))
WHERE public_number IS NULL;

-- Conversation outcome + acquisition source (for continuous improvement / future training).
ALTER TABLE conversations
    ADD COLUMN IF NOT EXISTS outcome text,
    ADD COLUMN IF NOT EXISTS outcome_reason text,
    ADD COLUMN IF NOT EXISTS source_kind text,
    ADD COLUMN IF NOT EXISTS live_code text,
    ADD COLUMN IF NOT EXISTS closed_at timestamptz;

COMMENT ON COLUMN conversations.outcome IS
    'success|abandoned|failed|human_takeover — set when the thread closes for learning';
COMMENT ON COLUMN conversations.source_kind IS
    'live|organic|unknown — how the customer arrived';
COMMENT ON COLUMN conversations.live_code IS
    'Exact live/product code if the thread started from a live code';

-- Owner feedback (thumbs / note) for continuous improvement.
CREATE TABLE IF NOT EXISTS conversation_feedback (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants (id),
    conversation_id uuid NOT NULL REFERENCES conversations (id),
    rating smallint NOT NULL CHECK (rating IN (-1, 1)),
    note text,
    created_by text NOT NULL DEFAULT 'owner',
    created_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE conversation_feedback ENABLE ROW LEVEL SECURITY;
ALTER TABLE conversation_feedback FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS conversation_feedback_tenant ON conversation_feedback;
CREATE POLICY conversation_feedback_tenant ON conversation_feedback
    USING (tenant_id = current_setting('app.tenant_id')::uuid)
    WITH CHECK (tenant_id = current_setting('app.tenant_id')::uuid);

CREATE INDEX IF NOT EXISTS conversation_feedback_conversation
    ON conversation_feedback (tenant_id, conversation_id, created_at DESC);

-- Turn-level quality signals for later eval / training (complement agent_trace).
CREATE TABLE IF NOT EXISTS conversation_learning_events (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants (id),
    conversation_id uuid NOT NULL REFERENCES conversations (id),
    event_type text NOT NULL,
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE conversation_learning_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE conversation_learning_events FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS conversation_learning_events_tenant ON conversation_learning_events;
CREATE POLICY conversation_learning_events_tenant ON conversation_learning_events
    USING (tenant_id = current_setting('app.tenant_id')::uuid)
    WITH CHECK (tenant_id = current_setting('app.tenant_id')::uuid);

CREATE INDEX IF NOT EXISTS conversation_learning_events_conv
    ON conversation_learning_events (tenant_id, conversation_id, created_at DESC);
CREATE INDEX IF NOT EXISTS conversation_learning_events_type
    ON conversation_learning_events (tenant_id, event_type, created_at DESC);
