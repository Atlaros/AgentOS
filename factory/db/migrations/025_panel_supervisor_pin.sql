-- 025 panel supervisor role + optional PIN for privileged cash ops (ADR-009 T4).

ALTER TABLE panel_users
    ADD COLUMN IF NOT EXISTS pin_salt text,
    ADD COLUMN IF NOT EXISTS pin_hash text;

DO $$
DECLARE
    role_con text;
    audit_con text;
BEGIN
    SELECT conname INTO role_con
    FROM pg_constraint
    WHERE conrelid = 'panel_users'::regclass
      AND contype = 'c'
      AND pg_get_constraintdef(oid) ILIKE '%role%';
    IF role_con IS NOT NULL THEN
        EXECUTE format('ALTER TABLE panel_users DROP CONSTRAINT %I', role_con);
    END IF;

    SELECT conname INTO audit_con
    FROM pg_constraint
    WHERE conrelid = 'human_audit_events'::regclass
      AND contype = 'c'
      AND pg_get_constraintdef(oid) ILIKE '%actor_role%';
    IF audit_con IS NOT NULL THEN
        EXECUTE format('ALTER TABLE human_audit_events DROP CONSTRAINT %I', audit_con);
    END IF;
END $$;

ALTER TABLE panel_users
    ADD CONSTRAINT panel_users_role_check
    CHECK (role IN ('owner', 'supervisor', 'staff'));

ALTER TABLE human_audit_events
    ADD CONSTRAINT human_audit_events_actor_role_check
    CHECK (actor_role IN ('owner', 'supervisor', 'staff'));
