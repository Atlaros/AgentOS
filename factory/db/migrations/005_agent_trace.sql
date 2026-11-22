-- Agent harness observability. No RLS: service writes for ops audit.
CREATE TABLE IF NOT EXISTS agent_trace_events (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id uuid,
    employee text,
    role text,
    operation text NOT NULL,
    provider text,
    model text,
    created_at timestamptz NOT NULL DEFAULT now(),
    latency_ms integer,
    used_fallback boolean,
    prompt text,
    raw_response text,
    parsed_action text,
    parsed_skill text,
    error text,
    payload jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS agent_trace_events_conversation_created_idx
    ON agent_trace_events (conversation_id, created_at);

CREATE INDEX IF NOT EXISTS agent_trace_events_operation_created_idx
    ON agent_trace_events (operation, created_at);

CREATE INDEX IF NOT EXISTS agent_trace_events_employee_created_idx
    ON agent_trace_events (employee, created_at);
