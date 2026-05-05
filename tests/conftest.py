"""
Session-level fixtures and post-run SQL index for tests/.

Provides:
- `reset_config`: per-test reset of the global DataVault config to defaults so
  config.json or earlier tests do not leak settings.
- `write_sql`: shared fixture that writes generated SQL to ../temp_sql/<test>.sql
  and prints it. Use it in any test that wants to capture its SQL on disk.

After any test run that writes SQL files, a grouped index is printed
so all generated SQL is easy to locate.
"""
from __future__ import annotations

import inspect
from pathlib import Path
from typing import Callable

import pytest
from datavault4sqlglot.config import DataVaultConfig, config

_DEFAULTS = DataVaultConfig()

_OUT_DIR = Path(__file__).parent.parent / "temp_sql"

_GROUPS: list[tuple[str, str]] = [
    ("STAGE",     "test_stage_"),
    ("HUB",       "test_hub_"),
    ("LINK",      "test_link_"),
    ("SAT v0/v1", "test_sat_"),
    ("DIALECTS", "test_dialect_"),
    ("EXECUTION", "test_execution_"),
]

_W = 74


@pytest.fixture(autouse=True)
def reset_config():
    """Reset global config to defaults before each test so config.json does not leak."""
    for field in DataVaultConfig.model_fields:
        setattr(config, field, getattr(_DEFAULTS, field))
    yield
    for field in DataVaultConfig.model_fields:
        setattr(config, field, getattr(_DEFAULTS, field))


@pytest.fixture
def write_sql() -> Callable[[str, str], None]:
    """
    Returns a function `write_sql(label, sql)` that writes the SQL to
    ../temp_sql/<calling_test_name>.sql and prints a banner.

    Banner format mirrors the prefix → group mapping used by the post-run index.
    """
    def _write(label: str, sql: str) -> None:
        _OUT_DIR.mkdir(parents=True, exist_ok=True)
        caller = inspect.currentframe().f_back.f_code.co_name
        # Resolve a short banner tag from the test name prefix.
        prefix_to_tag = {
            "test_stage_": "STAGE",
            "test_hub_":   "HUB",
            "test_link_":  "LINK",
            "test_sat_v0": "SAT v0",
            "test_sat_v1": "SAT v1",
            "test_dialect_": "DIALECT",
            "test_execution_": "EXECUTION",
        }
        tag = next((v for k, v in prefix_to_tag.items() if caller.startswith(k)), "TEST")
        (_OUT_DIR / f"{caller}.sql").write_text(
            f"-- {tag} -- {label}\n\n{sql}\n", encoding="utf-8"
        )
        print(f"\n{'='*70}\n{tag} -- {label}\n{'='*70}\n{sql}\n")
    return _write


def pytest_sessionfinish(session: object, exitstatus: object) -> None:
    if not _OUT_DIR.exists():
        return
    files = sorted(_OUT_DIR.glob("*.sql"))
    if not files:
        return

    sep = "=" * _W
    print(f"\n{sep}")
    print(f"  Generated SQL  ->  {_OUT_DIR}")
    print(sep)

    assigned: set[str] = set()
    for label, prefix in _GROUPS:
        group = [f for f in files if f.name.startswith(prefix)]
        if not group:
            continue
        bar = "-" * (_W - 6 - len(label))
        print(f"\n  -- {label} {bar}")
        for f in group:
            assigned.add(f.name)
            name = f.stem[len(prefix):].replace("_", " ")
            print(f"    {name:<52}  {f.stat().st_size:>5} B")

    other = [f for f in files if f.name not in assigned]
    if other:
        print(f"\n  -- OTHER {'-' * (_W - 11)}")
        for f in other:
            print(f"    {f.stem:<52}  {f.stat().st_size:>5} B")

    total = sum(f.stat().st_size for f in files)
    print(f"\n  {len(files)} files  .  {total:,} B total")
    print(f"{sep}\n")
