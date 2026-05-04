"""
Session-level fixtures and post-run SQL index for tests/.

After any test run that writes SQL files, a grouped index is printed
so all generated SQL is easy to locate.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from datavault4sqlglot.config import DataVaultConfig, config

_DEFAULTS = DataVaultConfig()

_OUT_DIR = Path(__file__).parent.parent / "temp_sql"

_GROUPS: list[tuple[str, str]] = [
    ("STAGE",     "test_stage_"),
    ("HUB",       "test_hub_"),
    ("LINK",      "test_link_"),
    ("SAT v0/v1", "test_sat_"),
    ("MA-SAT",    "test_ma_sat_"),
    ("EFF-SAT",   "test_eff_sat_"),
    ("NH-LINK",   "test_nh_link_"),
    ("NH-SAT",    "test_nh_sat_"),
    ("REC-TRACK", "test_rec_track_"),
    ("PIT",       "test_pit_"),
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
