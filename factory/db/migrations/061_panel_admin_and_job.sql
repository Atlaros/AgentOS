-- 061 Administrator is a server actor, not a panel_users row.
-- Staff may carry a job title (cajero, almacén). Audit accepts the admin actor.
-- Ported from Agent-IAv2 048_panel_admin_and_job.sql (Factory 048 already used).

ALTER TABLE panel_users
    ADD COLUMN IF NOT EXISTS job_title text NOT NULL DEFAULT '';

ALTER TABLE human_audit_events DROP CONSTRAINT IF EXISTS human_audit_events_actor_role_check;
ALTER TABLE human_audit_events
    ADD CONSTRAINT human_audit_events_actor_role_check
    CHECK (actor_role IN ('admin', 'owner', 'supervisor', 'staff'));
