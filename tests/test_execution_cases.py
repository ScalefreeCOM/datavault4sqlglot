"""
Data-driven execution tests: one parametrized test per YAML case file.

Thin adapter — all logic lives in ``cases/dv_case_runner.py``. Case ids become
pytest ids, so the spec hierarchy stays addressable:

    python -m pytest tests/test_execution_cases.py -v
    python -m pytest "tests/test_execution_cases.py::test_execution_case[2.2.2.3]"
"""
from __future__ import annotations

import pytest

from cases.case_loader import load_all_cases
from cases.dv_case_runner import run_case

_CASES = load_all_cases()


@pytest.mark.parametrize("case", _CASES, ids=[c.id for c in _CASES])
def test_execution_case(case, seed, run_select, dump):
    run_case(case, seed=seed, run_select=run_select, dump=dump)
