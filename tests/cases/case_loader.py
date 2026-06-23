"""
Discovery + parsing of YAML case files under ``tests/cases/**/*.yml``.

Runs at pytest collection time. Parses each file into a validated ``Case`` and
hard-fails on any parse/validation error (a broken case must surface as a loud
collection error, never a silent skip). Does NOT touch the global config.
"""
from __future__ import annotations

from pathlib import Path

import yaml

from cases.case_schema import Case

_CASES_DIR = Path(__file__).parent


def load_all_cases() -> list[Case]:
    """Load and validate every ``*.yml`` case file, sorted by path."""
    cases: list[Case] = []
    for path in sorted(_CASES_DIR.glob("**/*.yml")):
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        try:
            cases.append(Case.model_validate(data))
        except Exception as exc:  # noqa: BLE001 — re-raise with the file path attached
            raise ValueError(f"Invalid case file {path}: {exc}") from exc
    return cases
