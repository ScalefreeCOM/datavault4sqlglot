"""
Stage SQL generation — all parameter combinations.
Run with:  pytest tests/test_stage.py -v -s
"""
from __future__ import annotations

import pytest

from datavault4sqlglot.config import config
from datavault4sqlglot.generators.stage import StageGenerator
from datavault4sqlglot.metadata import StageModel


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
def test_stage_full_load_complete(write_sql):
    src = StageModel(**BASE_SRC)
    sql = StageGenerator(source_model=src).to_sql()
    write_sql("Full Load — hashkeys + hashdiff + derived_columns", sql)
    assert "derived_columns_cte" in sql
    assert "HK_ORDER_H" in sql
    assert "HD_ORDER_DETAILS" in sql


# ---------------------------------------------------------------------------
# 2. Hashkeys only — no derived columns (simpler CTE structure)
# ---------------------------------------------------------------------------
def test_stage_hashkeys_only_no_derived(write_sql):
    src = StageModel(
        table_name="ORDERS",
        hashed_columns={
            "HK_ORDER_H":    ["O_ORDERKEY"],
            "HK_CUSTOMER_H": ["O_CUSTKEY"],
        },
    )
    sql = StageGenerator(source_model=src).to_sql()
    write_sql("Hashkeys Only — no derived_columns (no extra CTE)", sql)
    assert "derived_columns_cte" not in sql
    assert "HK_ORDER_H" in sql


# ---------------------------------------------------------------------------
# 3. include_source_columns=False — only hash columns projected
# ---------------------------------------------------------------------------
def test_stage_exclude_source_columns(write_sql):
    src = StageModel(
        table_name="ORDERS",
        include_source_columns=False,
        hashed_columns={"HK_ORDER_H": ["O_ORDERKEY"]},
        derived_columns={"LOAD_DATE": "CURRENT_TIMESTAMP()"},
    )
    sql = StageGenerator(source_model=src).to_sql()
    write_sql("include_source_columns=False — only hash + derived columns", sql)
    assert "HK_ORDER_H" in sql
    assert "MD5" in sql


# ---------------------------------------------------------------------------
# 4. Incremental — HWM WHERE ldts > MAX(ldts) filter
# ---------------------------------------------------------------------------
def test_stage_incremental_hwm(write_sql):
    src = StageModel(**BASE_SRC)
    sql = StageGenerator(source_model=src, is_incremental=True).to_sql()
    write_sql("Incremental — HWM WHERE ldts > MAX(ldts) from target", sql)
    assert "MAX" in sql
    assert config.ldts_alias in sql


# ---------------------------------------------------------------------------
# 5. Case sensitivity — hashkey UPPER (default)
# ---------------------------------------------------------------------------
def test_stage_case_insensitive_hash(write_sql):
    src = StageModel(
        table_name="ORDERS",
        hashed_columns={"HK_ORDER_H": ["O_ORDERKEY"]},
        case_sensitivity=False,
    )
    sql = StageGenerator(source_model=src).to_sql()
    write_sql("case_sensitivity=False — UPPER applied on hashkey input (default)", sql)
    assert "UPPER" in sql


# ---------------------------------------------------------------------------
# 8. Case sensitivity — no UPPER when case_sensitive=True
# ---------------------------------------------------------------------------
def test_stage_case_sensitive_hash(write_sql):
    src = StageModel(
        table_name="ORDERS",
        hashed_columns={"HK_ORDER_H": ["O_ORDERKEY"]},
        case_sensitivity=True,
    )
    sql = StageGenerator(source_model=src).to_sql()
    write_sql("case_sensitivity=True — no UPPER on hashkey input", sql)
    assert "UPPER" not in sql


# ---------------------------------------------------------------------------
# 9. Trim — TRIM applied when use_rtrim=True
# ---------------------------------------------------------------------------
def test_stage_use_rtrim_true(write_sql):
    src = StageModel(
        table_name="ORDERS",
        hashed_columns={"HK_ORDER_H": ["O_ORDERKEY"]},
        use_rtrim=True,
    )
    sql = StageGenerator(source_model=src).to_sql()
    write_sql("use_rtrim=True — TRIM applied before hashing", sql)
    assert "TRIM" in sql


# ---------------------------------------------------------------------------
# 10. Trim — no TRIM when use_rtrim=False
# ---------------------------------------------------------------------------
def test_stage_use_rtrim_false(write_sql):
    src = StageModel(
        table_name="ORDERS",
        hashed_columns={"HK_ORDER_H": ["O_ORDERKEY"]},
        use_rtrim=False,
    )
    sql = StageGenerator(source_model=src).to_sql()
    write_sql("use_rtrim=False — no TRIM before hashing", sql)
    assert "TRIM" not in sql


# ---------------------------------------------------------------------------
# 11. Per-column overrides (case_sensitivity + use_rtrim in dict form)
# ---------------------------------------------------------------------------
def test_stage_per_column_overrides(write_sql):
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
    write_sql("Per-column overrides — HK: no UPPER + no TRIM; HD: default hashdiff settings", sql)
    assert "HK_ORDER_H" in sql
    assert "HD_DETAILS" in sql


# ---------------------------------------------------------------------------
# 12. SHA256 hash algorithm — SHA2 expression
# ---------------------------------------------------------------------------
def test_stage_sha256(write_sql):
    config.hash = "SHA256"
    src = StageModel(**BASE_SRC)
    sql = StageGenerator(source_model=src).to_sql()
    write_sql("SHA256 — SHA2 hash expression", sql)
    assert "SHA2" in sql or "SHA256" in sql


# ---------------------------------------------------------------------------
# 13. missing_columns — CAST(NULL AS dtype) for schema evolution
# ---------------------------------------------------------------------------
def test_stage_missing_columns(write_sql):
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
    write_sql("missing_columns — CAST(NULL AS dtype) for schema evolution", sql)
    assert "LEGACY_FLAG" in sql
    assert "REGION_CODE" in sql
    assert "DISCOUNT_RATE" in sql
    assert "NULL" in sql


# ---------------------------------------------------------------------------
# 14. sequence — ROW_NUMBER() OVER ()
# ---------------------------------------------------------------------------
def test_stage_sequence(write_sql):
    src = StageModel(
        table_name="ORDERS",
        hashed_columns={"HK_ORDER_H": ["O_ORDERKEY"]},
        sequence="SEQ_NUM",
    )
    sql = StageGenerator(source_model=src).to_sql()
    write_sql("sequence=SEQ_NUM — ROW_NUMBER() OVER () column", sql)
    assert "SEQ_NUM" in sql
    assert "ROW_NUMBER" in sql


# ---------------------------------------------------------------------------
# 15. NULL sentinel — COALESCE with ^^ in every hash expression
# ---------------------------------------------------------------------------
def test_stage_null_sentinel_in_hash(write_sql):
    sql = _sql(_basic_src())
    write_sql("Null sentinel — COALESCE with ^^ in hash expression", sql)
    assert "^^" in sql
    assert "COALESCE" in sql


# ---------------------------------------------------------------------------
# 16. REGEXP_REPLACE for whitespace normalization in hash
# ---------------------------------------------------------------------------
def test_stage_newline_removal_regexp(write_sql):
    sql = _sql(_basic_src())
    write_sql("REGEXP_REPLACE — whitespace normalization before hashing", sql)
    assert "REGEXP_REPLACE" in sql


# ---------------------------------------------------------------------------
# 17. Custom ldts_alias used in incremental HWM filter
# ---------------------------------------------------------------------------
def test_stage_custom_ldts_alias_in_hwm(write_sql):
    config.ldts_alias = "load_ts"
    sql = _sql(_basic_src(), is_incremental=True)
    write_sql("custom ldts_alias=load_ts in incremental HWM filter", sql)
    assert "load_ts" in sql


# ---------------------------------------------------------------------------
# 18. All features combined
# ---------------------------------------------------------------------------
def test_stage_all_features_combined(write_sql):
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
    sql = StageGenerator(source_model=src).to_sql()
    write_sql(
        "All Features Combined — hashkeys + hashdiff + derived + missing_columns + sequence",
        sql,
    )
    assert "HK_ORDER_H" in sql
    assert "HD_ORDER_DETAILS" in sql
    assert "LEGACY_REGION" in sql
    assert "SEQ_NUM" in sql


# ---------------------------------------------------------------------------
# 19. Ghost record — basic: unknown_values + error_values + ghost_records CTEs
# ---------------------------------------------------------------------------
def test_stage_ghost_record_basic(write_sql):
    src = StageModel(
        table_name="STG_CUSTOMERS",
        schema="STAGE",
        load_date_col="ldts",
        record_source_col="rsrc",
        ghost_record_types={
            "ldts":        "TIMESTAMP",
            "rsrc":        "VARCHAR",
            "customer_id": "VARCHAR",
        },
        hashed_columns={"hk_h_customer": ["customer_id"]},
    )
    sql = StageGenerator(source_model=src).to_sql()
    write_sql("Ghost Record — unknown_values + error_values + ghost_records CTEs", sql)
    assert "unknown_values" in sql
    assert "error_values" in sql
    assert "ghost_records" in sql
    assert "UNION ALL" in sql.upper()
    # Hash column appears in main SELECT (computed) and ghost CTEs (sentinel literal)
    assert "hk_h_customer" in sql
    # Sentinel values for hash columns
    assert "00000000000000000000000000000000" in sql   # unknown key
    assert "ffffffffffffffffffffffffffffffff" in sql   # error key
    # ldts ghost values
    assert config.beginning_of_all_times in sql
    assert config.end_of_all_times in sql
    # rsrc ghost values
    assert config.ghost_record_rsrc in sql
    assert config.ghost_record_error_rsrc in sql
    # Type-aware string values
    assert "(unknown)" in sql
    assert "(error)" in sql


# ---------------------------------------------------------------------------
# 20. Ghost record — incremental (HWM in main SELECT, ghost CTEs are unfiltered)
# ---------------------------------------------------------------------------
def test_stage_ghost_record_incremental(write_sql):
    src = StageModel(
        table_name="STG_CUSTOMERS",
        schema="STAGE",
        load_date_col="ldts",
        record_source_col="rsrc",
        ghost_record_types={
            "ldts":        "TIMESTAMP",
            "rsrc":        "VARCHAR",
            "customer_id": "VARCHAR",
        },
        hashed_columns={"hk_h_customer": ["customer_id"]},
    )
    sql = StageGenerator(source_model=src, is_incremental=True).to_sql()
    write_sql("Ghost Record — incremental (HWM in main SELECT, ghost CTEs unfiltered)", sql)
    assert "unknown_values" in sql
    assert "error_values" in sql
    assert "ghost_records" in sql
    assert "UNION ALL" in sql.upper()
    assert "MAX" in sql


# ---------------------------------------------------------------------------
# 21. Ghost record + derived columns — derived CTE before ghost CTEs
# ---------------------------------------------------------------------------
def test_stage_ghost_record_with_derived(write_sql):
    src = StageModel(
        table_name="STG_CUSTOMERS",
        schema="STAGE",
        ghost_record_types={
            "ldts":        "TIMESTAMP",
            "rsrc":        "VARCHAR",
            "customer_id": "VARCHAR",
        },
        hashed_columns={"hk_h_customer": ["customer_id"]},
        derived_columns={"RECORD_SOURCE": "'ERP/CUSTOMERS'"},
    )
    sql = StageGenerator(source_model=src).to_sql()
    write_sql("Ghost Record + derived_columns — derived CTE then ghost CTEs", sql)
    assert "derived_columns_cte" in sql
    assert "unknown_values" in sql
    assert "error_values" in sql
    assert "ghost_records" in sql
    assert "UNION ALL" in sql.upper()
    assert "RECORD_SOURCE" in sql


# ---------------------------------------------------------------------------
# 22. No ghost record — ghost_record_types=None keeps original behaviour
# ---------------------------------------------------------------------------
def test_stage_no_ghost_record_by_default(write_sql):
    src = StageModel(
        table_name="STG_CUSTOMERS",
        hashed_columns={"hk_h_customer": ["customer_id"]},
    )
    sql = StageGenerator(source_model=src).to_sql()
    write_sql("No Ghost Record — ghost_record_types=None keeps original path", sql)
    assert "UNION" not in sql.upper()
    assert "unknown_values" not in sql
    assert "error_values" not in sql
    assert "ghost_records" not in sql
