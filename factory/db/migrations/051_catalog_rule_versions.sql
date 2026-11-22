-- Published catalog rules keep a version that can be restored.
-- No RLS: the operator console lists every business, same as catalog_rules.

ALTER TABLE catalog_rules
    ADD COLUMN version integer NOT NULL DEFAULT 1 CHECK (version > 0);

CREATE TABLE catalog_rule_versions (
    rule_id uuid NOT NULL REFERENCES catalog_rules (id),
    version integer NOT NULL CHECK (version > 0),
    when_event text NOT NULL,
    if_threshold text NOT NULL,
    then_action text NOT NULL,
    PRIMARY KEY (rule_id, version),
    CHECK (length(btrim(when_event)) > 0),
    CHECK (length(btrim(if_threshold)) > 0),
    CHECK (length(btrim(then_action)) > 0)
);
