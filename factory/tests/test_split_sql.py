"""Migration SQL splitter must not treat `;` inside `--` comments as separators."""

from factory_os.domain.postgres import split_sql


def test_split_sql_keeps_semicolon_inside_line_comment() -> None:
    sql = """
-- Used codes stay for audit; only unused ones unlock signup.
CREATE TABLE signup_invites (code text PRIMARY KEY);
CREATE INDEX signup_invites_unused ON signup_invites (code);
"""
    parts = split_sql(sql)
    assert len(parts) == 2
    assert "CREATE TABLE signup_invites" in parts[0]
    assert "CREATE INDEX" not in parts[0]
    assert parts[1].lstrip().startswith("CREATE INDEX signup_invites_unused")
    # The buggy splitter used to emit a bare statement starting with "only".
    assert not any(part.lstrip().lower().startswith("only ") for part in parts)


def test_split_sql_preserves_dollar_quoted_bodies() -> None:
    sql = """
CREATE FUNCTION f() RETURNS void AS $$
BEGIN
  PERFORM 1;
END;
$$ LANGUAGE plpgsql;
"""
    parts = split_sql(sql)
    assert len(parts) == 1
    assert "PERFORM 1;" in parts[0]
