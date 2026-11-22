from pathlib import Path

from evals.template_exit import checklist_paths_exist, exit_checks, known_templates


def test_template_exit_lists_ropa_and_cafe() -> None:
    assert "ropa" in known_templates()
    assert "cafe" in known_templates()
    assert exit_checks("closet") == exit_checks("ropa")
    assert any("cafe_golden" in node for node in exit_checks("cafe"))
    assert any("closet_golden" in node for node in exit_checks("ropa"))


def test_template_exit_files_exist() -> None:
    missing = checklist_paths_exist(Path(__file__).resolve().parents[1])
    assert missing == []
