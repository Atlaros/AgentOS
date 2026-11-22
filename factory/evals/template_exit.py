"""Exit checklist per Factory industry template (ADR-020)."""

from __future__ import annotations

from pathlib import Path

# Node ids relative to the repo root. A template is ready only when all pass.
TEMPLATE_EXIT: dict[str, tuple[str, ...]] = {
    "ropa": (
        "evals/test_closet_golden.py::test_closet_vertical_golden",
        "evals/test_shop_rubro.py::test_other_rubro_faq_does_not_confirm_payment_or_change_price",
    ),
    "cafe": (
        "evals/test_cafe_golden.py::test_cafe_browse_and_text_does_not_confirm_payment",
    ),
}


def known_templates() -> tuple[str, ...]:
    return tuple(sorted(TEMPLATE_EXIT))


def exit_checks(industry: str) -> tuple[str, ...]:
    key = (industry or "").strip().lower()
    if key == "closet":
        key = "ropa"
    if key not in TEMPLATE_EXIT:
        raise KeyError(f"unknown_template:{industry}")
    return TEMPLATE_EXIT[key]


def checklist_paths_exist(repo_root: Path | None = None) -> list[str]:
    """Return missing node-id file paths (before ::). Empty list means all files exist."""
    root = repo_root or Path(__file__).resolve().parents[1]
    missing: list[str] = []
    for nodes in TEMPLATE_EXIT.values():
        for node in nodes:
            rel = node.split("::", 1)[0]
            if not (root / rel).is_file():
                missing.append(rel)
    return missing
