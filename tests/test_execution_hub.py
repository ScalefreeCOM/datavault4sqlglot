"""
DuckDB execution tests for HubGenerator — full Hub matrix.

Test numbering mirrors the test-spec hierarchy:

    2    Hub
    2.1      one source, one bk
    2.1.1      initial
    2.1.2      incremental
    2.2      two sources, two bks
    2.2.1      initial
    2.2.2      incremental

Conventions used across all tests:
- Hashkey column:    HK_ORDER_H
- Canonical BK col:  ORDER_ID  (hub-level — the name the hub will expose)
- Per-source BK:     SAP_ORDER_ID / WEB_ORDER_ID (physical staging cols),
                     mapped to the canonical name via SourceBinding.bk_columns.
- LDTS / RSRC names: read from config.ldts_alias / config.rsrc_alias —
                     the casing follows whatever the project configures,
                     it is not hardcoded here.
- Stage LDTS values are always >= 2026-01-03 so the global-HWM filter
  used by the single-source incremental path never accidentally drops them.

Run with:  pytest tests/test_execution_hub.py -v -s
"""
from __future__ import annotations

from typing import Optional

import pytest

from datavault4sqlglot.config import config
from datavault4sqlglot.generators.hub import HubGenerator
from datavault4sqlglot.metadata import SourceBinding, SourceModel


_LEADING_SOURCE_GAP = pytest.mark.xfail(
    reason=(
        "HubGenerator dedup orders by `ldts` only — there is no explicit "
        "source-ordinal tiebreaker. With tied LDTS values, the row that wins "
        "depends on engine internals (UNION-order + ROW_NUMBER tiebreak) and "
        "is non-deterministic across invocations on DuckDB. Fixing this "
        "requires injecting a `_source_ordinal` per per-source CTE and adding "
        "it to the dedup ORDER BY."
    ),
    strict=False,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _binding(
    table: str,
    *,
    source_col: Optional[str] = None,
) -> SourceBinding:
    """
    Build a SourceBinding for STG_<table>.

    `source_col` is the physical staging column. When set and different from
    the hub-level canonical name, the generator emits ``source_col AS <bk>``
    in the per-source CTE so multi-source UNIONs line up by name.
    """
    return SourceBinding(
        source=SourceModel(
            database="RAW_DB",
            schema="STAGE",
            table_name=table,
            load_date_col="LOAD_DATE",
            record_source_col="RECORD_SOURCE",
        ),
        bk_columns=[source_col] if source_col else None,
    )


def _hub(*sources: SourceBinding, incremental: bool) -> HubGenerator:
    return HubGenerator(
        target_database="DV",
        target_schema="RAW_VAULT",
        target_table="HUB_ORDER",
        sources=list(sources),
        hashkey="HK_ORDER_H",
        business_keys=["ORDER_ID"],
        is_incremental=incremental,
        dialect="duckdb",
    )


# ===========================================================================
# 2.1.1 — Initial load, one source, one BK
# ===========================================================================

def test_2_1_1_1_initial_same_bk_two_batches(seed, run_select, dump):
    """Same BK appears over two batches → only the earliest is inserted."""
    ldts, rsrc = config.ldts_alias, config.rsrc_alias

    seed("RAW_DB.STAGE.STG_ORDERS", [
        {"HK_ORDER_H": "h1", "ORDER_ID": "A1",
         "LOAD_DATE": "2026-01-03", "RECORD_SOURCE": "ERP/ORDERS"},
        {"HK_ORDER_H": "h1", "ORDER_ID": "A1",
         "LOAD_DATE": "2026-01-05", "RECORD_SOURCE": "ERP/ORDERS"},
    ])
    dump("RAW_DB.STAGE.STG_ORDERS", label="2.1.1.1 stage")

    sql = _hub(_binding("STG_ORDERS"), incremental=False).to_sql()
    rows = run_select(sql)
    dump(sql, label="2.1.1.1 result")

    assert len(rows) == 1
    assert rows[0]["HK_ORDER_H"] == "h1"
    assert rows[0][ldts] == "2026-01-03"


# ===========================================================================
# 2.1.2 — Incremental load, one source, one BK
# ===========================================================================

def test_2_1_2_1_incremental_existing_bk_in_incoming(seed, run_select, dump):
    """Existing BK appears in incoming batch → no inserts."""
    ldts, rsrc = config.ldts_alias, config.rsrc_alias

    seed("DV.RAW_VAULT.HUB_ORDER", [
        {"HK_ORDER_H": "h1", "ORDER_ID": "A1",
         ldts: "2026-01-01", rsrc: "ERP/ORDERS"},
    ])
    seed("RAW_DB.STAGE.STG_ORDERS", [
        {"HK_ORDER_H": "h1", "ORDER_ID": "A1",
         "LOAD_DATE": "2026-01-05", "RECORD_SOURCE": "ERP/ORDERS"},
    ])
    dump("DV.RAW_VAULT.HUB_ORDER",  label="2.1.2.1 target (existing)")
    dump("RAW_DB.STAGE.STG_ORDERS", label="2.1.2.1 stage")

    sql = _hub(_binding("STG_ORDERS"), incremental=True).to_sql()
    rows = run_select(sql)
    dump(sql, label="2.1.2.1 result")

    assert rows == []


def test_2_1_2_2_incremental_new_bk_two_batches(seed, run_select, dump):
    """New BK appears in two incoming batches → earliest is inserted."""
    ldts, rsrc = config.ldts_alias, config.rsrc_alias

    seed("DV.RAW_VAULT.HUB_ORDER", [
        {"HK_ORDER_H": "h_existing", "ORDER_ID": "EXIST",
         ldts: "2026-01-01", rsrc: "ERP/ORDERS"},
    ])
    seed("RAW_DB.STAGE.STG_ORDERS", [
        {"HK_ORDER_H": "h_new", "ORDER_ID": "NEW",
         "LOAD_DATE": "2026-01-05", "RECORD_SOURCE": "ERP/ORDERS"},
        {"HK_ORDER_H": "h_new", "ORDER_ID": "NEW",
         "LOAD_DATE": "2026-01-03", "RECORD_SOURCE": "ERP/ORDERS"},
    ])
    dump("RAW_DB.STAGE.STG_ORDERS", label="2.1.2.2 stage")

    sql = _hub(_binding("STG_ORDERS"), incremental=True).to_sql()
    rows = run_select(sql)
    dump(sql, label="2.1.2.2 result")

    assert len(rows) == 1
    assert rows[0]["HK_ORDER_H"] == "h_new"
    assert rows[0][ldts] == "2026-01-03"


def test_2_1_2_3_incremental_new_bk_one_batch(seed, run_select, dump):
    """New BK appears in one incoming batch → inserted."""
    ldts, rsrc = config.ldts_alias, config.rsrc_alias

    seed("DV.RAW_VAULT.HUB_ORDER", [
        {"HK_ORDER_H": "h_existing", "ORDER_ID": "EXIST",
         ldts: "2026-01-01", rsrc: "ERP/ORDERS"},
    ])
    seed("RAW_DB.STAGE.STG_ORDERS", [
        {"HK_ORDER_H": "h_new", "ORDER_ID": "NEW",
         "LOAD_DATE": "2026-01-05", "RECORD_SOURCE": "ERP/ORDERS"},
    ])
    dump("RAW_DB.STAGE.STG_ORDERS", label="2.1.2.3 stage")

    sql = _hub(_binding("STG_ORDERS"), incremental=True).to_sql()
    rows = run_select(sql)
    dump(sql, label="2.1.2.3 result")

    assert len(rows) == 1
    assert rows[0]["HK_ORDER_H"] == "h_new"
    assert rows[0][ldts] == "2026-01-05"


# ===========================================================================
# 2.2.1 — Initial load, two sources, two BKs
# ===========================================================================

def test_2_2_1_1_initial_same_bk_diff_ldts(seed, run_select, dump):
    """Same BK in both sources, different LDTS → earliest is inserted."""
    ldts, rsrc = config.ldts_alias, config.rsrc_alias

    seed("RAW_DB.STAGE.STG_SAP_ORDERS", [
        {"HK_ORDER_H": "h1", "SAP_ORDER_ID": "A1",
         "LOAD_DATE": "2026-01-05", "RECORD_SOURCE": "SAP/ORDERS"},
    ])
    seed("RAW_DB.STAGE.STG_WEB_ORDERS", [
        {"HK_ORDER_H": "h1", "WEB_ORDER_ID": "A1",
         "LOAD_DATE": "2026-01-03", "RECORD_SOURCE": "WEB/ORDERS"},
    ])
    dump("RAW_DB.STAGE.STG_SAP_ORDERS", label="2.2.1.1 SAP")
    dump("RAW_DB.STAGE.STG_WEB_ORDERS", label="2.2.1.1 WEB")

    sql = _hub(
        _binding("STG_SAP_ORDERS", source_col="SAP_ORDER_ID"),
        _binding("STG_WEB_ORDERS", source_col="WEB_ORDER_ID"),
        incremental=False,
    ).to_sql()
    rows = run_select(sql)
    dump(sql, label="2.2.1.1 result")

    assert len(rows) == 1
    assert rows[0]["ORDER_ID"] == "A1"
    assert rows[0][ldts] == "2026-01-03"
    assert rows[0][rsrc] == "WEB/ORDERS"


def test_2_2_1_2_initial_different_bks(seed, run_select, dump):
    """Each source has a different BK → both are inserted."""
    seed("RAW_DB.STAGE.STG_SAP_ORDERS", [
        {"HK_ORDER_H": "h_sap", "SAP_ORDER_ID": "S1",
         "LOAD_DATE": "2026-01-03", "RECORD_SOURCE": "SAP/ORDERS"},
    ])
    seed("RAW_DB.STAGE.STG_WEB_ORDERS", [
        {"HK_ORDER_H": "h_web", "WEB_ORDER_ID": "W1",
         "LOAD_DATE": "2026-01-03", "RECORD_SOURCE": "WEB/ORDERS"},
    ])
    dump("RAW_DB.STAGE.STG_SAP_ORDERS", label="2.2.1.2 SAP")
    dump("RAW_DB.STAGE.STG_WEB_ORDERS", label="2.2.1.2 WEB")

    sql = _hub(
        _binding("STG_SAP_ORDERS", source_col="SAP_ORDER_ID"),
        _binding("STG_WEB_ORDERS", source_col="WEB_ORDER_ID"),
        incremental=False,
    ).to_sql()
    rows = run_select(sql)
    dump(sql, label="2.2.1.2 result")

    assert {r["HK_ORDER_H"] for r in rows} == {"h_sap", "h_web"}
    assert {r["ORDER_ID"] for r in rows} == {"S1", "W1"}


@_LEADING_SOURCE_GAP
def test_2_2_1_3_initial_same_bk_same_ldts_leading_source_wins(
    seed, run_select, dump
):
    """Same BK in both sources, same LDTS → leading (first-listed) source wins."""
    rsrc = config.rsrc_alias

    seed("RAW_DB.STAGE.STG_SAP_ORDERS", [
        {"HK_ORDER_H": "h1", "SAP_ORDER_ID": "A1",
         "LOAD_DATE": "2026-01-03", "RECORD_SOURCE": "SAP/ORDERS"},
    ])
    seed("RAW_DB.STAGE.STG_WEB_ORDERS", [
        {"HK_ORDER_H": "h1", "WEB_ORDER_ID": "A1",
         "LOAD_DATE": "2026-01-03", "RECORD_SOURCE": "WEB/ORDERS"},
    ])
    dump("RAW_DB.STAGE.STG_SAP_ORDERS", label="2.2.1.3 SAP (leading)")
    dump("RAW_DB.STAGE.STG_WEB_ORDERS", label="2.2.1.3 WEB")

    # Sources passed in order: SAP first, so SAP is the leading system.
    sql = _hub(
        _binding("STG_SAP_ORDERS", source_col="SAP_ORDER_ID"),
        _binding("STG_WEB_ORDERS", source_col="WEB_ORDER_ID"),
        incremental=False,
    ).to_sql()
    rows = run_select(sql)
    dump(sql, label="2.2.1.3 result")

    assert len(rows) == 1
    assert rows[0][rsrc] == "SAP/ORDERS"


# ===========================================================================
# 2.2.2 — Incremental load, two sources, two BKs
# ===========================================================================

def test_2_2_2_1_incremental_existing_one_source_new_other(
    seed, run_select, dump
):
    """Existing BK in source A, new BK in source B → only the new BK inserted."""
    ldts, rsrc = config.ldts_alias, config.rsrc_alias

    seed("DV.RAW_VAULT.HUB_ORDER", [
        {"HK_ORDER_H": "h_existing", "ORDER_ID": "EXIST",
         ldts: "2026-01-01", rsrc: "SAP/ORDERS"},
    ])
    seed("RAW_DB.STAGE.STG_SAP_ORDERS", [
        {"HK_ORDER_H": "h_existing", "SAP_ORDER_ID": "EXIST",
         "LOAD_DATE": "2026-01-05", "RECORD_SOURCE": "SAP/ORDERS"},
    ])
    seed("RAW_DB.STAGE.STG_WEB_ORDERS", [
        {"HK_ORDER_H": "h_new", "WEB_ORDER_ID": "NEW",
         "LOAD_DATE": "2026-01-05", "RECORD_SOURCE": "WEB/ORDERS"},
    ])
    dump("DV.RAW_VAULT.HUB_ORDER",      label="2.2.2.1 target")
    dump("RAW_DB.STAGE.STG_SAP_ORDERS", label="2.2.2.1 SAP")
    dump("RAW_DB.STAGE.STG_WEB_ORDERS", label="2.2.2.1 WEB")

    sql = _hub(
        _binding("STG_SAP_ORDERS", source_col="SAP_ORDER_ID"),
        _binding("STG_WEB_ORDERS", source_col="WEB_ORDER_ID"),
        incremental=True,
    ).to_sql()
    rows = run_select(sql)
    dump(sql, label="2.2.2.1 result")

    assert len(rows) == 1
    assert rows[0]["HK_ORDER_H"] == "h_new"
    assert rows[0]["ORDER_ID"] == "NEW"
    assert rows[0][rsrc] == "WEB/ORDERS"


def test_2_2_2_2_incremental_existing_in_both(seed, run_select, dump):
    """Existing BK appears in both sources → no inserts."""
    ldts, rsrc = config.ldts_alias, config.rsrc_alias

    seed("DV.RAW_VAULT.HUB_ORDER", [
        {"HK_ORDER_H": "h1", "ORDER_ID": "A1",
         ldts: "2026-01-01", rsrc: "SAP/ORDERS"},
    ])
    seed("RAW_DB.STAGE.STG_SAP_ORDERS", [
        {"HK_ORDER_H": "h1", "SAP_ORDER_ID": "A1",
         "LOAD_DATE": "2026-01-05", "RECORD_SOURCE": "SAP/ORDERS"},
    ])
    seed("RAW_DB.STAGE.STG_WEB_ORDERS", [
        {"HK_ORDER_H": "h1", "WEB_ORDER_ID": "A1",
         "LOAD_DATE": "2026-01-05", "RECORD_SOURCE": "WEB/ORDERS"},
    ])
    dump("DV.RAW_VAULT.HUB_ORDER",      label="2.2.2.2 target")
    dump("RAW_DB.STAGE.STG_SAP_ORDERS", label="2.2.2.2 SAP")
    dump("RAW_DB.STAGE.STG_WEB_ORDERS", label="2.2.2.2 WEB")

    sql = _hub(
        _binding("STG_SAP_ORDERS", source_col="SAP_ORDER_ID"),
        _binding("STG_WEB_ORDERS", source_col="WEB_ORDER_ID"),
        incremental=True,
    ).to_sql()
    rows = run_select(sql)
    dump(sql, label="2.2.2.2 result")

    assert rows == []


def test_2_2_2_3_incremental_new_bk_both_sources_diff_ldts(
    seed, run_select, dump
):
    """New BK in both sources with different LDTS → earliest is inserted."""
    ldts, rsrc = config.ldts_alias, config.rsrc_alias

    seed("DV.RAW_VAULT.HUB_ORDER", [
        {"HK_ORDER_H": "h_existing", "ORDER_ID": "EXIST",
         ldts: "2026-01-01", rsrc: "SAP/ORDERS"},
    ])
    seed("RAW_DB.STAGE.STG_SAP_ORDERS", [
        {"HK_ORDER_H": "h_new", "SAP_ORDER_ID": "NEW",
         "LOAD_DATE": "2026-01-05", "RECORD_SOURCE": "SAP/ORDERS"},
    ])
    seed("RAW_DB.STAGE.STG_WEB_ORDERS", [
        {"HK_ORDER_H": "h_new", "WEB_ORDER_ID": "NEW",
         "LOAD_DATE": "2026-01-03", "RECORD_SOURCE": "WEB/ORDERS"},
    ])
    dump("RAW_DB.STAGE.STG_SAP_ORDERS", label="2.2.2.3 SAP")
    dump("RAW_DB.STAGE.STG_WEB_ORDERS", label="2.2.2.3 WEB")

    sql = _hub(
        _binding("STG_SAP_ORDERS", source_col="SAP_ORDER_ID"),
        _binding("STG_WEB_ORDERS", source_col="WEB_ORDER_ID"),
        incremental=True,
    ).to_sql()
    rows = run_select(sql)
    dump(sql, label="2.2.2.3 result")

    assert len(rows) == 1
    assert rows[0]["HK_ORDER_H"] == "h_new"
    assert rows[0][ldts] == "2026-01-03"
    assert rows[0][rsrc] == "WEB/ORDERS"


@_LEADING_SOURCE_GAP
def test_2_2_2_4_incremental_new_bk_both_sources_same_ldts_leading_wins(
    seed, run_select, dump
):
    """New BK in both sources, same LDTS → leading source wins."""
    ldts, rsrc = config.ldts_alias, config.rsrc_alias

    seed("DV.RAW_VAULT.HUB_ORDER", [
        {"HK_ORDER_H": "h_existing", "ORDER_ID": "EXIST",
         ldts: "2026-01-01", rsrc: "SAP/ORDERS"},
    ])
    seed("RAW_DB.STAGE.STG_SAP_ORDERS", [
        {"HK_ORDER_H": "h_new", "SAP_ORDER_ID": "NEW",
         "LOAD_DATE": "2026-01-03", "RECORD_SOURCE": "SAP/ORDERS"},
    ])
    seed("RAW_DB.STAGE.STG_WEB_ORDERS", [
        {"HK_ORDER_H": "h_new", "WEB_ORDER_ID": "NEW",
         "LOAD_DATE": "2026-01-03", "RECORD_SOURCE": "WEB/ORDERS"},
    ])
    dump("RAW_DB.STAGE.STG_SAP_ORDERS", label="2.2.2.4 SAP (leading)")
    dump("RAW_DB.STAGE.STG_WEB_ORDERS", label="2.2.2.4 WEB")

    sql = _hub(
        _binding("STG_SAP_ORDERS", source_col="SAP_ORDER_ID"),
        _binding("STG_WEB_ORDERS", source_col="WEB_ORDER_ID"),
        incremental=True,
    ).to_sql()
    rows = run_select(sql)
    dump(sql, label="2.2.2.4 result")

    assert len(rows) == 1
    assert rows[0]["HK_ORDER_H"] == "h_new"
    assert rows[0][rsrc] == "SAP/ORDERS"
