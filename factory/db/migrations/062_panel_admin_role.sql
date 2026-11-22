-- 062 Support administrator may live in panel_users (hidden from the owner list).
-- Ported from Agent-IAv2 049_panel_admin_role.sql (Factory 049 already used).

ALTER TABLE panel_users DROP CONSTRAINT IF EXISTS panel_users_role_check;
ALTER TABLE panel_users
    ADD CONSTRAINT panel_users_role_check
    CHECK (role IN ('admin', 'owner', 'supervisor', 'staff'));
