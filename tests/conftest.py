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


# ---------------------------------------------------------------------------
# DuckDB execution fixtures
# ---------------------------------------------------------------------------
try:
    import duckdb
except ImportError:
    duckdb = None


@pytest.fixture
def duck():
    """In-memory DuckDB connection with RAW_DB and DV catalogs attached."""
    if duckdb is None:
        pytest.skip("duckdb not installed (pip install datavault4sqlglot[test])")
    conn = duckdb.connect(":memory:")
    for db in ("RAW_DB", "DV"):
        conn.execute(f"ATTACH ':memory:' AS {db}")
    yield conn
    conn.close()


@pytest.fixture
def seed(duck):
    """seed('RAW_DB.STAGE.STG_X', [{'col': 'val', ...}, ...]) — DDL + INSERT."""
    def _seed(fqtn: str, rows: list[dict]) -> None:
        if not rows:
            raise ValueError("seed() needs at least one row to infer schema")
        parts = fqtn.split(".")
        if len(parts) == 3:
            db, schema, _ = parts
            duck.execute(f"CREATE SCHEMA IF NOT EXISTS {db}.{schema}")
        elif len(parts) == 2:
            schema, _ = parts
            duck.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")
        cols_ddl = ", ".join(f'"{k}" VARCHAR' for k in rows[0])
        duck.execute(f"CREATE OR REPLACE TABLE {fqtn} ({cols_ddl})")
        ph = ", ".join(["?"] * len(rows[0]))
        duck.executemany(
            f"INSERT INTO {fqtn} VALUES ({ph})",
            [tuple(r.values()) for r in rows],
        )
    return _seed


@pytest.fixture
def run_select(duck):
    """Execute SQL and return rows as a list of dicts keyed by column name."""
    def _run(sql: str) -> list[dict]:
        cur = duck.execute(sql)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]
    return _run


@pytest.fixture
def dump(duck):
    """
    Pretty-print a table or arbitrary query for debugging.

        dump("RAW_DB.STAGE.STG_SAP_ORDERS")            # full table
        dump("SELECT * FROM hub_result", label="hub")  # arbitrary SQL

    ASCII-only output — visible when pytest is run with -s.
    """
    def _dump(target: str, label: str | None = None) -> None:
        is_query = target.lstrip().lower().startswith(("select", "with"))
        sql = target if is_query else f"SELECT * FROM {target}"
        cur = duck.execute(sql)
        cols = [d[0] for d in cur.description]
        rows = [tuple("" if v is None else str(v) for v in r) for r in cur.fetchall()]
        widths = [max(len(c), *(len(r[i]) for r in rows), 0) for i, c in enumerate(cols)] \
                 if rows else [len(c) for c in cols]

        def _fmt(values: tuple[str, ...]) -> str:
            return "| " + " | ".join(v.ljust(w) for v, w in zip(values, widths)) + " |"

        sep = "+" + "+".join("-" * (w + 2) for w in widths) + "+"
        banner = label or target
        print(f"\n--- {banner} " + "-" * max(0, 60 - len(banner)))
        print(sep)
        print(_fmt(tuple(cols)))
        print(sep)
        for r in rows:
            print(_fmt(r))
        print(sep)
        print(f"({len(rows)} row{'s' if len(rows) != 1 else ''})")
    return _dump


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
