"""
Stage SQL generation — all parameter combinations.
Run with:  pytest tests/test_stage.py -v -s
"""
from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from datavault4sqlglot.config import config
from datavault4sqlglot.generators.stage import StageGenerator
from datavault4sqlglot.metadata import StageModel

_OUT_DIR = Path(__file__).parent.parent / "temp_sql"


def _print(label: str, sql: str) -> None:
    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    caller = inspect.currentframe().f_back.f_code.co_name
    (_OUT_DIR / f"{caller}.sql").write_text(
        f"-- STAGE -- {label}\n\n{sql}\n", encoding="utf-8"
    )
    print(f"\n{'='*70}\nSTAGE -- {label}\n{'='*70}\n{sql}\n")


def _sql(src: StageModel, **kwargs: object) -> str:
    return StageGenerator(source_model=src, **kwargs).generate_sql().sql()


def _basic_src(**kwargs: object) -> StageModel:
    return StageModel(
        table_name="raw.orders",
        hashed_columns={"hk_order": ["order_id"]},
        **kwargs,
    )


BASE_SRC = dict(
    database="RAW_DB",
    schema="RAW_SCHEMA",
    table_name="ORDERS",
    hashed_columns={
        "HK_ORDER_H":     ["O_ORDERKEY"],
        "HK_CUSTOMER_H":  ["O_CUSTKEY"],
        "HK_L_ORD_CUST":  ["O_ORDERKEY", "O_CUSTKEY"],
        "HD_ORDER_DETAILS": {
            "is_hashdiff": True,
            "columns": ["O_ORDERSTATUS", "O_ORDERPRIORITY", "O_SHIPPRIORITY"],
        },
    },
    derived_columns={
        "LOAD_DATE":     "CURRENT_TIMESTAMP()",
        "RECORD_SOURCE": "'ERP/ORDERS'",
    },
)


# ---------------------------------------------------------------------------
# 1. Full load — hashkeys + hashdiff + derived columns
# ---------------------------------------------------------------------------
def test_stage_full_load_complete():
    src = StageModel(**BASE_SRC)
    sql = StageGenerator(source_model=src).to_sql()
    _print("Full Load — hashkeys + hashdiff + derived_columns", sql)
    assert "derived_columns_cte" in sql
    assert "HK_ORDER_H" in sql
    assert "HD_ORDER_DETAILS" in sql


# ---------------------------------------------------------------------------
# 2. Hashkeys only — no derived columns (simpler CTE structure)
# ---------------------------------------------------------------------------
def test_stage_hashkeys_only_no_derived():
    src = StageModel(
        table_name="ORDERS",
        hashed_columns={
            "HK_ORDER_H":    ["O_ORDERKEY"],
            "HK_CUSTOMER_H": ["O_CUSTKEY"],
        },
    )
    sql = StageGenerator(source_model=src).to_sql()
    _print("Hashkeys Only — no derived_columns (no extra CTE)", sql)
    assert "derived_columns_cte" not in sql
    assert "HK_ORDER_H" in sql


# ---------------------------------------------------------------------------
# 3. include_source_columns=False — only hash columns projected
# ---------------------------------------------------------------------------
def test_stage_exclude_source_columns():
    src = StageModel(
        table_name="ORDERS",
        include_source_columns=False,
        hashed_columns={"HK_ORDER_H": ["O_ORDERKEY"]},
        derived_columns={"LOAD_DATE": "CURRENT_TIMESTAMP()"},
    )
    sql = StageGenerator(source_model=src).to_sql()
    _print("include_source_columns=False — only hash + derived columns", sql)
    assert "HK_ORDER_H" in sql
    assert "MD5" in sql


# ---------------------------------------------------------------------------
# 4. Incremental — HWM WHERE ldts > MAX(ldts) filter
# ---------------------------------------------------------------------------
def test_stage_incremental_hwm():
    src = StageModel(**BASE_SRC)
    sql = StageGenerator(source_model=src, is_incremental=True).to_sql()
    _print("Incremental — HWM WHERE ldts > MAX(ldts) from target", sql)
    assert "MAX" in sql
    assert config.ldts_alias in sql


# ---------------------------------------------------------------------------
# 5. Ghost records — UNION ALL with unknown (all-0) + error (all-f) rows
# ---------------------------------------------------------------------------
def test_stage_ghost_records():
    src = StageModel(**BASE_SRC)
    sql = StageGenerator(source_model=src, enable_ghost_records=True).to_sql()
    _print("Ghost Records — unknown (all-0) + error (all-f) rows via UNION ALL", sql)
    assert "UNION ALL" in sql
    assert "00000000000000000000000000000000" in sql
    assert "ffffffffffffffffffffffffffffffff" in sql


# ---------------------------------------------------------------------------
# 6. Ghost records skipped on incremental
# ---------------------------------------------------------------------------
def test_stage_ghost_records_skipped_on_incremental():
    src = StageModel(**BASE_SRC)
    sql = StageGenerator(source_model=src, enable_ghost_records=True, is_incremental=True).to_sql()
    _print("Ghost Records + Incremental — ghost rows suppressed (UNION ALL absent)", sql)
    assert "UNION ALL" not in sql


# ---------------------------------------------------------------------------
# 7. Case sensitivity — hashkey UPPER (default)
# ---------------------------------------------------------------------------
def test_stage_case_insensitive_hash():
    src = StageModel(
        table_name="ORDERS",
        hashed_columns={"HK_ORDER_H": ["O_ORDERKEY"]},
        case_sensitivity=False,
    )
    sql = StageGenerator(source_model=src).to_sql()
    _print("case_sensitivity=False — UPPER applied on hashkey input (default)", sql)
    assert "UPPER" in sql


# ---------------------------------------------------------------------------
# 8. Case sensitivity — no UPPER when case_sensitive=True
# ---------------------------------------------------------------------------
def test_stage_case_sensitive_hash():
    src = StageModel(
        table_name="ORDERS",
        hashed_columns={"HK_ORDER_H": ["O_ORDERKEY"]},
        case_sensitivity=True,
    )
    sql = StageGenerator(source_model=src).to_sql()
    _print("case_sensitivity=True — no UPPER on hashkey input", sql)
    assert "UPPER" not in sql


# ---------------------------------------------------------------------------
# 9. Trim — TRIM applied when use_rtrim=True
# ---------------------------------------------------------------------------
def test_stage_use_rtrim_true():
    src = StageModel(
        table_name="ORDERS",
        hashed_columns={"HK_ORDER_H": ["O_ORDERKEY"]},
        use_rtrim=True,
    )
    sql = StageGenerator(source_model=src).to_sql()
    _print("use_rtrim=True — TRIM applied before hashing", sql)
    assert "TRIM" in sql


# ---------------------------------------------------------------------------
# 10. Trim — no TRIM when use_rtrim=False
# ---------------------------------------------------------------------------
def test_stage_use_rtrim_false():
    src = StageModel(
        table_name="ORDERS",
        hashed_columns={"HK_ORDER_H": ["O_ORDERKEY"]},
        use_rtrim=False,
    )
    sql = StageGenerator(source_model=src).to_sql()
    _print("use_rtrim=False — no TRIM before hashing", sql)
    assert "TRIM" not in sql


# ---------------------------------------------------------------------------
# 11. Per-column overrides (case_sensitivity + use_rtrim in dict form)
# ---------------------------------------------------------------------------
def test_stage_per_column_overrides():
    src = StageModel(
        table_name="ORDERS",
        hashed_columns={
            "HK_ORDER_H": {
                "columns": ["O_ORDERKEY"],
                "case_sensitivity": True,
                "use_rtrim": False,
            },
            "HD_DETAILS": {
                "is_hashdiff": True,
                "columns": ["O_ORDERSTATUS", "O_TOTALPRICE"],
            },
        },
    )
    sql = StageGenerator(source_model=src).to_sql()
    _print("Per-column overrides — HK: no UPPER + no TRIM; HD: default hashdiff settings", sql)
    assert "HK_ORDER_H" in sql
    assert "HD_DETAILS" in sql


# ---------------------------------------------------------------------------
# 12. SHA256 hash algorithm — SHA2 expression + 64-char ghost strings
# ---------------------------------------------------------------------------
def test_stage_sha256():
    config.hash = "SHA256"
    src = StageModel(**BASE_SRC)
    sql = StageGenerator(source_model=src, enable_ghost_records=True).to_sql()
    _print("SHA256 — 64-char hash, ghost rows use 64-char hex strings", sql)
    assert "SHA2" in sql or "SHA256" in sql
    assert "0" * 64 in sql
    assert "f" * 64 in sql


# ---------------------------------------------------------------------------
# 13. missing_columns — CAST(NULL AS dtype) for schema evolution
# ---------------------------------------------------------------------------
def test_stage_missing_columns():
    src = StageModel(
        table_name="ORDERS",
        hashed_columns={"HK_ORDER_H": ["O_ORDERKEY"]},
        derived_columns={"LOAD_DATE": "CURRENT_TIMESTAMP()"},
        missing_columns={
            "LEGACY_FLAG":   "BOOLEAN",
            "REGION_CODE":   "VARCHAR",
            "DISCOUNT_RATE": "DECIMAL",
        },
    )
    sql = StageGenerator(source_model=src).to_sql()
    _print("missing_columns — CAST(NULL AS dtype) for schema evolution", sql)
    assert "LEGACY_FLAG" in sql
    assert "REGION_CODE" in sql
    assert "DISCOUNT_RATE" in sql
    assert "NULL" in sql


# ---------------------------------------------------------------------------
# 14. sequence — ROW_NUMBER() OVER ()
# ---------------------------------------------------------------------------
def test_stage_sequence():
    src = StageModel(
        table_name="ORDERS",
        hashed_columns={"HK_ORDER_H": ["O_ORDERKEY"]},
        sequence="SEQ_NUM",
    )
    sql = StageGenerator(source_model=src).to_sql()
    _print("sequence=SEQ_NUM — ROW_NUMBER() OVER () column", sql)
    assert "SEQ_NUM" in sql
    assert "ROW_NUMBER" in sql


# ---------------------------------------------------------------------------
# 15. NULL sentinel — COALESCE with ^^ in every hash expression
# ---------------------------------------------------------------------------
def test_stage_null_sentinel_in_hash():
    sql = _sql(_basic_src())
    _print("Null sentinel — COALESCE with ^^ in hash expression", sql)
    assert "^^" in sql
    assert "COALESCE" in sql


# ---------------------------------------------------------------------------
# 16. REGEXP_REPLACE for whitespace normalization in hash
# ---------------------------------------------------------------------------
def test_stage_newline_removal_regexp():
    sql = _sql(_basic_src())
    _print("REGEXP_REPLACE — whitespace normalization before hashing", sql)
    assert "REGEXP_REPLACE" in sql


# ---------------------------------------------------------------------------
# 17. Custom ldts_alias used in incremental HWM filter
# ---------------------------------------------------------------------------
def test_stage_custom_ldts_alias_in_hwm():
    config.ldts_alias = "load_ts"
    sql = _sql(_basic_src(), is_incremental=True)
    _print("custom ldts_alias=load_ts in incremental HWM filter", sql)
    assert "load_ts" in sql


# ---------------------------------------------------------------------------
# 18. Custom beginning_of_all_times in ghost record row
# ---------------------------------------------------------------------------
def test_stage_custom_beginning_of_all_times_in_ghost():
    src = StageModel(
        table_name="raw.orders",
        hashed_columns={"hk_order": ["order_id"]},
        derived_columns={"ldts": "CURRENT_TIMESTAMP()", "rsrc": "'SYS'"},
    )
    sql = _sql(src, enable_ghost_records=True, beginning_of_all_times="1800-01-01")
    _print("custom beginning_of_all_times=1800-01-01 in unknown ghost row", sql)
    assert "1800-01-01" in sql


# ---------------------------------------------------------------------------
# 19. Custom end_of_all_times in ghost record row + incremental HWM
# ---------------------------------------------------------------------------
def test_stage_custom_end_of_all_times():
    src = StageModel(
        table_name="raw.orders",
        hashed_columns={"hk_order": ["order_id"]},
        derived_columns={"ldts": "CURRENT_TIMESTAMP()", "rsrc": "'SYS'"},
    )
    sql = _sql(src, enable_ghost_records=True, end_of_all_times="2099-12-31")
    _print("custom end_of_all_times=2099-12-31 in error ghost row", sql)
    assert "2099-12-31" in sql


# ---------------------------------------------------------------------------
# 20. All features combined
# ---------------------------------------------------------------------------
def test_stage_all_features_combined():
    src = StageModel(
        database="RAW_DB",
        schema="RAW_SCHEMA",
        table_name="ORDERS",
        hashed_columns={
            "HK_ORDER_H": ["O_ORDERKEY"],
            "HK_CUSTOMER_H": ["O_CUSTKEY"],
            "HD_ORDER_DETAILS": {
                "is_hashdiff": True,
                "columns": ["O_ORDERSTATUS", "O_TOTALPRICE"],
            },
        },
        derived_columns={
            "LOAD_DATE":     "CURRENT_TIMESTAMP()",
            "RECORD_SOURCE": "'ERP/ORDERS'",
        },
        missing_columns={"LEGACY_REGION": "VARCHAR"},
        sequence="SEQ_NUM",
    )
    sql = StageGenerator(source_model=src, enable_ghost_records=True).to_sql()
    _print(
        "All Features Combined — hashkeys + hashdiff + derived + missing_columns + sequence + ghost",
        sql,
    )
    assert "HK_ORDER_H" in sql
    assert "HD_ORDER_DETAILS" in sql
    assert "LEGACY_REGION" in sql
    assert "SEQ_NUM" in sql
    assert "UNION ALL" in sql
