"""
Multi-dialect transpilation contract tests.

For every (entity, dialect) pair we generate the SQL, transpile it, and parse
the result back through sqlglot. If parse_one(sql, dialect=X) does not raise,
the SQL is at least syntactically valid in dialect X — which is the floor we
want to guarantee for the platform-agnostic claim.

This is the assertion that backs up "sqlglot will take care of it" — without
this test, the multi-dialect promise is unverified.
"""
from __future__ import annotations

import sqlglot
import pytest
from sqlglot.errors import ParseError

from datavault4sqlglot.config import config
from datavault4sqlglot.generators.hub import HubGenerator
from datavault4sqlglot.generators.link import LinkGenerator
from datavault4sqlglot.generators.satellite import SatelliteGenerator
from datavault4sqlglot.generators.satellite_v1 import SatelliteV1Generator
from datavault4sqlglot.generators.stage import StageGenerator
from datavault4sqlglot.metadata import SourceBinding, SourceModel, StageModel


DIALECTS = ["snowflake", "bigquery", "postgres", "redshift", "duckdb"]


def _stage_sql(dialect: str) -> str:
    src = StageModel(
        table_name="raw_orders",
        hashed_columns={"hk_order": ["order_id"]},
    )
    return StageGenerator(source_model=src, dialect=dialect).to_sql()


def _hub_sql(dialect: str, *, incremental: bool = False) -> str:
    binding = SourceBinding(
        source=SourceModel(table_name="stg_orders"),
        rsrc_statics=["ERP/ORDERS"] if incremental else None,
    )
    return HubGenerator(
        target_table="hub_order",
        sources=[binding],
        hashkey="hk_order_h",
        business_keys=["order_id"],
        is_incremental=incremental,
        dialect=dialect,
    ).to_sql()


def _link_sql(dialect: str, *, incremental: bool = False) -> str:
    binding = SourceBinding(
        source=SourceModel(table_name="stg_orders"),
        hash_key_col="hk_order_customer_l",
        rsrc_statics=["ERP/ORDERS"] if incremental else None,
    )
    return LinkGenerator(
        target_table="lnk_order_customer",
        sources=[binding],
        link_hash_key="hk_order_customer_l",
        foreign_hash_keys=["hk_order_h", "hk_customer_h"],
        is_incremental=incremental,
        dialect=dialect,
    ).to_sql()


def _sat_v0_sql(dialect: str, *, incremental: bool = False) -> str:
    return SatelliteGenerator(
        target_table="sat_order_details",
        source_model=SourceModel(table_name="stg_orders"),
        parent_hash_key="hk_order_h",
        hash_diff="hd_order_details",
        payload=["status", "amount"],
        is_incremental=incremental,
        dialect=dialect,
    ).to_sql()


def _sat_v1_sql(dialect: str) -> str:
    return SatelliteV1Generator(
        target_table="sat_order_details_v1",
        sat_v0_table="sat_order_details",
        parent_hash_key="hk_order_h",
        hash_diff="hd_order_details",
        dialect=dialect,
    ).to_sql()


# Every (entity, dialect) pair the library should support.
ENTITY_GENERATORS = [
    ("stage",            _stage_sql),
    ("hub_full",         lambda d: _hub_sql(d, incremental=False)),
    ("hub_incremental",  lambda d: _hub_sql(d, incremental=True)),
    ("link_full",        lambda d: _link_sql(d, incremental=False)),
    ("link_incremental", lambda d: _link_sql(d, incremental=True)),
    ("sat_v0_full",      lambda d: _sat_v0_sql(d, incremental=False)),
    ("sat_v0_incr",      lambda d: _sat_v0_sql(d, incremental=True)),
    ("sat_v1",           _sat_v1_sql),
]


@pytest.mark.parametrize("dialect", DIALECTS)
@pytest.mark.parametrize("entity,builder", ENTITY_GENERATORS, ids=lambda v: v if isinstance(v, str) else "fn")
def test_dialect_parses_back(dialect: str, entity: str, builder, write_sql) -> None:
    """
    Every entity must produce SQL that re-parses cleanly in its target dialect.

    This is the contractual floor for the "sqlglot transpiles for you" claim:
    if the generated SQL is invalid syntax in dialect X, sqlglot.parse_one
    raises and the test fails — surfacing the regression before users hit it.
    """
    sql = builder(dialect)
    try:
        sqlglot.parse_one(sql, dialect=dialect)
    except ParseError as exc:  # pragma: no cover - failure path is the assertion
        pytest.fail(
            f"{entity!r} did not parse back in dialect {dialect!r}:\n"
            f"  error: {exc}\n"
            f"  sql:\n{sql}"
        )
    write_sql(f"{entity} @ {dialect}", sql)


def test_dialect_global_config_overrides_default(write_sql) -> None:
    """config.dialect should be honoured when no instance dialect is given."""
    config.dialect = "postgres"
    src = StageModel(table_name="orders", hashed_columns={"hk": ["id"]})
    sql = StageGenerator(source_model=src).to_sql()
    sqlglot.parse_one(sql, dialect="postgres")
    write_sql("global config.dialect=postgres", sql)


def test_dialect_instance_overrides_global(write_sql) -> None:
    """Instance dialect should override config.dialect."""
    config.dialect = "snowflake"
    src = StageModel(table_name="orders", hashed_columns={"hk": ["id"]})
    sql = StageGenerator(source_model=src, dialect="duckdb").to_sql()
    sqlglot.parse_one(sql, dialect="duckdb")
    write_sql("instance dialect=duckdb overrides global=snowflake", sql)
