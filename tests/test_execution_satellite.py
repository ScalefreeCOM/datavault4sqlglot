"""
DuckDB execution tests for SatelliteGenerator (sat_v0) — full Satellite matrix.

Test numbering, BK / HD / LOAD_DATE values, target ("current state") seeds,
source ("input") seeds, and expected outputs are taken **verbatim** from the
test-spec table:

    4    Satellite v0
    4.1      source_is_single_batch = true
    4.1.1      single_batch  (one ldts in source)
    4.1.1.1      initial
    4.1.1.2      incremental
    4.1.2      multi_batch  (consecutive ldts in source)
    4.1.2.1      initial
    4.1.2.2      incremental
    4.2      source_is_single_batch = false
    4.2.1      single_batch
    4.2.1.1      initial
    4.2.1.2      incremental
    4.2.2      multi_batch
    4.2.2.1      initial
    4.2.2.2      incremental

Conventions used across all tests:
- Parent hashkey:    HK_ORDER_H        (the spec's "BK" column)
- Hashdiff column:   HD_ORDER          (the spec's "HD" column)
- Payload column:    ORDER_STATUS      (held constant per row, not asserted)
- LDTS / RSRC names: read from config.ldts_alias / config.rsrc_alias —
                     the casing follows whatever the project configures,
                     it is not hardcoded here.
- Current-state rows always sit at LOAD_DATE 2026-01-01, source rows at
  2026-01-02 / 2026-01-03 — so the global-HWM filter
  (max(target.ldts) = 2026-01-01) never accidentally drops them.

Each test asserts on the *delta* the generated SELECT produces — i.e. the
new rows the satellite would insert — which equals the spec's "Sample
Output" minus the spec's "Assumed Current State".

Run with:  pytest tests/test_execution_satellite.py -v -s
"""
from __future__ import annotations

from datavault4sqlglot.config import config
from datavault4sqlglot.generators.satellite import SatelliteGenerator
from datavault4sqlglot.metadata import SourceModel


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _src(table: str = "STG_ORDERS") -> SourceModel:
    return SourceModel(
        database="RAW_DB",
        schema="STAGE",
        table_name=table,
        load_date_col="LOAD_DATE",
        record_source_col="RECORD_SOURCE",
    )


def _sat(
    *,
    is_incremental: bool,
    is_single_batch: bool = False,
) -> SatelliteGenerator:
    """Build a SatelliteGenerator pre-wired against STG_ORDERS."""
    return SatelliteGenerator(
        target_database="DV",
        target_schema="RAW_VAULT",
        target_table="SAT_ORDER",
        source_model=_src(),
        parent_hash_key="HK_ORDER_H",
        hash_diff="HD_ORDER",
        payload=["ORDER_STATUS"],
        is_incremental=is_incremental,
        source_is_single_batch=is_single_batch,
        dialect="duckdb",
    )


# ---------------------------------------------------------------------------
# Row-builder shorthands. Match the spec table column order: BK, HD, LOAD_DATE.
# `_t` builds a target ("current state") row, `_s` builds a source ("input") row.
# Payload is a constant so it never confuses the assertion.
# ---------------------------------------------------------------------------

def _t(bk: str, hd: str, ld: str) -> dict:
    return {
        "HK_ORDER_H": bk,
        "HD_ORDER": hd,
        config.ldts_alias: ld,
        config.rsrc_alias: "ERP",
    }


def _s(bk: str, hd: str, ld: str) -> dict:
    return {
        "HK_ORDER_H": bk,
        "HD_ORDER": hd,
        "ORDER_STATUS": "data",
        "LOAD_DATE": ld,
        "RECORD_SOURCE": "ERP",
    }


def _triples(rows: list[dict]) -> set[tuple[str, str, str]]:
    """Project SELECT result rows down to the spec's (BK, HD, LOAD_DATE) shape."""
    ldts = config.ldts_alias
    return {(r["HK_ORDER_H"], r["HD_ORDER"], r[ldts]) for r in rows}


# ===========================================================================
# 4.1.1.1 — Initial load, single-batch source, single-batch data
# ===========================================================================

def test_4_1_1_1_1_initial_single_batch_all_inserted(seed, run_select, dump):
    """All records of a single batch are inserted."""
    seed("RAW_DB.STAGE.STG_ORDERS", [
        _s("A", "1", "2026-01-01"),
        _s("B", "1", "2026-01-01"),
    ])
    dump("RAW_DB.STAGE.STG_ORDERS", label="4.1.1.1.1 stage")

    sql = _sat(is_incremental=False, is_single_batch=True).to_sql()
    rows = run_select(sql)
    dump(sql, label="4.1.1.1.1 result")

    assert _triples(rows) == {
        ("A", "1", "2026-01-01"),
        ("B", "1", "2026-01-01"),
    }


# ===========================================================================
# 4.1.1.2 — Incremental load, single-batch source, single-batch data
# ===========================================================================

def test_4_1_1_2_1_incremental_existing_bk_new_hd_inserted(
    seed, run_select, dump
):
    """Existing BK has a new HD → inserted."""
    seed("DV.RAW_VAULT.SAT_ORDER", [
        _t("A", "1", "2026-01-01"),
        _t("B", "1", "2026-01-01"),
    ])
    seed("RAW_DB.STAGE.STG_ORDERS", [
        _s("A", "2", "2026-01-02"),
    ])
    dump("DV.RAW_VAULT.SAT_ORDER",  label="4.1.1.2.1 target")
    dump("RAW_DB.STAGE.STG_ORDERS", label="4.1.1.2.1 stage")

    sql = _sat(is_incremental=True, is_single_batch=True).to_sql()
    rows = run_select(sql)
    dump(sql, label="4.1.1.2.1 result")

    assert _triples(rows) == {("A", "2", "2026-01-02")}


def test_4_1_1_2_2_incremental_existing_bk_same_hd_not_inserted(
    seed, run_select, dump
):
    """Existing BK has the same HD as existing → not inserted."""
    seed("DV.RAW_VAULT.SAT_ORDER", [
        _t("A", "1", "2026-01-01"),
        _t("B", "1", "2026-01-01"),
    ])
    seed("RAW_DB.STAGE.STG_ORDERS", [
        _s("A", "1", "2026-01-02"),
    ])
    dump("DV.RAW_VAULT.SAT_ORDER",  label="4.1.1.2.2 target")
    dump("RAW_DB.STAGE.STG_ORDERS", label="4.1.1.2.2 stage")

    sql = _sat(is_incremental=True, is_single_batch=True).to_sql()
    rows = run_select(sql)
    dump(sql, label="4.1.1.2.2 result")

    assert _triples(rows) == set()


def test_4_1_1_2_3_incremental_new_bk_inserted(seed, run_select, dump):
    """New BK → inserted."""
    seed("DV.RAW_VAULT.SAT_ORDER", [
        _t("A", "1", "2026-01-01"),
        _t("B", "1", "2026-01-01"),
    ])
    seed("RAW_DB.STAGE.STG_ORDERS", [
        _s("C", "1", "2026-01-02"),
    ])
    dump("DV.RAW_VAULT.SAT_ORDER",  label="4.1.1.2.3 target")
    dump("RAW_DB.STAGE.STG_ORDERS", label="4.1.1.2.3 stage")

    sql = _sat(is_incremental=True, is_single_batch=True).to_sql()
    rows = run_select(sql)
    dump(sql, label="4.1.1.2.3 result")

    assert _triples(rows) == {("C", "1", "2026-01-02")}


# ===========================================================================
# 4.1.2.1 — Initial load, single-batch source, multi-batch data
# ===========================================================================

def test_4_1_2_1_1_initial_one_bk_same_hd_consecutive_both_inserted(
    seed, run_select, dump
):
    """One BK has the same HD over consecutive batches → both inserted."""
    seed("RAW_DB.STAGE.STG_ORDERS", [
        _s("A", "1", "2026-01-01"),
        _s("A", "1", "2026-01-02"),
    ])
    dump("RAW_DB.STAGE.STG_ORDERS", label="4.1.2.1.1 stage")

    sql = _sat(is_incremental=False, is_single_batch=True).to_sql()
    rows = run_select(sql)
    dump(sql, label="4.1.2.1.1 result")

    assert _triples(rows) == {
        ("A", "1", "2026-01-01"),
        ("A", "1", "2026-01-02"),
    }


def test_4_1_2_1_2_initial_one_bk_diff_hd_consecutive_both_inserted(
    seed, run_select, dump
):
    """One BK has different HDs over consecutive batches → both inserted."""
    seed("RAW_DB.STAGE.STG_ORDERS", [
        _s("A", "1", "2026-01-01"),
        _s("A", "2", "2026-01-02"),
    ])
    dump("RAW_DB.STAGE.STG_ORDERS", label="4.1.2.1.2 stage")

    sql = _sat(is_incremental=False, is_single_batch=True).to_sql()
    rows = run_select(sql)
    dump(sql, label="4.1.2.1.2 result")

    assert _triples(rows) == {
        ("A", "1", "2026-01-01"),
        ("A", "2", "2026-01-02"),
    }


# ===========================================================================
# 4.1.2.2 — Incremental load, single-batch source, multi-batch data
# ===========================================================================

def test_4_1_2_2_1_incremental_new_bk_same_hd_consecutive_both_inserted(
    seed, run_select, dump
):
    """New BK has the same HD over consecutive batches → both inserted."""
    seed("DV.RAW_VAULT.SAT_ORDER", [
        _t("A", "1", "2026-01-01"),
    ])
    seed("RAW_DB.STAGE.STG_ORDERS", [
        _s("B", "1", "2026-01-02"),
        _s("B", "1", "2026-01-03"),
    ])
    dump("DV.RAW_VAULT.SAT_ORDER",  label="4.1.2.2.1 target")
    dump("RAW_DB.STAGE.STG_ORDERS", label="4.1.2.2.1 stage")

    sql = _sat(is_incremental=True, is_single_batch=True).to_sql()
    rows = run_select(sql)
    dump(sql, label="4.1.2.2.1 result")

    assert _triples(rows) == {
        ("B", "1", "2026-01-02"),
        ("B", "1", "2026-01-03"),
    }


def test_4_1_2_2_2_incremental_new_bk_diff_hd_consecutive_both_inserted(
    seed, run_select, dump
):
    """New BK has different HDs over consecutive batches → both inserted."""
    seed("DV.RAW_VAULT.SAT_ORDER", [
        _t("A", "1", "2026-01-01"),
    ])
    seed("RAW_DB.STAGE.STG_ORDERS", [
        _s("B", "1", "2026-01-02"),
        _s("B", "2", "2026-01-03"),
    ])
    dump("DV.RAW_VAULT.SAT_ORDER",  label="4.1.2.2.2 target")
    dump("RAW_DB.STAGE.STG_ORDERS", label="4.1.2.2.2 stage")

    sql = _sat(is_incremental=True, is_single_batch=True).to_sql()
    rows = run_select(sql)
    dump(sql, label="4.1.2.2.2 result")

    assert _triples(rows) == {
        ("B", "1", "2026-01-02"),
        ("B", "2", "2026-01-03"),
    }


def test_4_1_2_2_3_incremental_existing_bk_same_hd_as_existing_no_inserts(
    seed, run_select, dump
):
    """Existing BK, same HD over batches and equal to existing → no inserts."""
    seed("DV.RAW_VAULT.SAT_ORDER", [
        _t("A", "1", "2026-01-01"),
    ])
    seed("RAW_DB.STAGE.STG_ORDERS", [
        _s("A", "1", "2026-01-02"),
        _s("A", "1", "2026-01-03"),
    ])
    dump("DV.RAW_VAULT.SAT_ORDER",  label="4.1.2.2.3 target")
    dump("RAW_DB.STAGE.STG_ORDERS", label="4.1.2.2.3 stage")

    sql = _sat(is_incremental=True, is_single_batch=True).to_sql()
    rows = run_select(sql)
    dump(sql, label="4.1.2.2.3 result")

    assert _triples(rows) == set()


def test_4_1_2_2_4_incremental_existing_bk_same_hd_diff_existing_both_inserted(
    seed, run_select, dump
):
    """Existing BK, same HD over batches but different from existing → both inserted."""
    seed("DV.RAW_VAULT.SAT_ORDER", [
        _t("A", "1", "2026-01-01"),
    ])
    seed("RAW_DB.STAGE.STG_ORDERS", [
        _s("A", "2", "2026-01-02"),
        _s("A", "2", "2026-01-03"),
    ])
    dump("DV.RAW_VAULT.SAT_ORDER",  label="4.1.2.2.4 target")
    dump("RAW_DB.STAGE.STG_ORDERS", label="4.1.2.2.4 stage")

    sql = _sat(is_incremental=True, is_single_batch=True).to_sql()
    rows = run_select(sql)
    dump(sql, label="4.1.2.2.4 result")

    assert _triples(rows) == {
        ("A", "2", "2026-01-02"),
        ("A", "2", "2026-01-03"),
    }


def test_4_1_2_2_5_incremental_existing_bk_diff_hd_first_eq_existing_only_later_inserted(
    seed, run_select, dump
):
    """Existing BK, different HDs over batches, first HD = existing → only later inserted."""
    seed("DV.RAW_VAULT.SAT_ORDER", [
        _t("A", "1", "2026-01-01"),
    ])
    seed("RAW_DB.STAGE.STG_ORDERS", [
        _s("A", "1", "2026-01-02"),
        _s("A", "2", "2026-01-03"),
    ])
    dump("DV.RAW_VAULT.SAT_ORDER",  label="4.1.2.2.5 target")
    dump("RAW_DB.STAGE.STG_ORDERS", label="4.1.2.2.5 stage")

    sql = _sat(is_incremental=True, is_single_batch=True).to_sql()
    rows = run_select(sql)
    dump(sql, label="4.1.2.2.5 result")

    assert _triples(rows) == {("A", "2", "2026-01-03")}


def test_4_1_2_2_6_incremental_existing_bk_diff_hd_first_neq_existing_both_inserted(
    seed, run_select, dump
):
    """Existing BK, different HDs over batches, first HD ≠ existing → both inserted."""
    seed("DV.RAW_VAULT.SAT_ORDER", [
        _t("A", "1", "2026-01-01"),
    ])
    seed("RAW_DB.STAGE.STG_ORDERS", [
        _s("A", "2", "2026-01-02"),
        _s("A", "3", "2026-01-03"),
    ])
    dump("DV.RAW_VAULT.SAT_ORDER",  label="4.1.2.2.6 target")
    dump("RAW_DB.STAGE.STG_ORDERS", label="4.1.2.2.6 stage")

    sql = _sat(is_incremental=True, is_single_batch=True).to_sql()
    rows = run_select(sql)
    dump(sql, label="4.1.2.2.6 result")

    assert _triples(rows) == {
        ("A", "2", "2026-01-02"),
        ("A", "3", "2026-01-03"),
    }


# ===========================================================================
# 4.2.1.1 — Initial load, multi-batch source, single-batch data
# ===========================================================================

def test_4_2_1_1_1_initial_single_batch_all_inserted(seed, run_select, dump):
    """All records of a single batch are inserted."""
    seed("RAW_DB.STAGE.STG_ORDERS", [
        _s("A", "1", "2026-01-01"),
        _s("B", "1", "2026-01-01"),
    ])
    dump("RAW_DB.STAGE.STG_ORDERS", label="4.2.1.1.1 stage")

    sql = _sat(is_incremental=False).to_sql()
    rows = run_select(sql)
    dump(sql, label="4.2.1.1.1 result")

    assert _triples(rows) == {
        ("A", "1", "2026-01-01"),
        ("B", "1", "2026-01-01"),
    }


# ===========================================================================
# 4.2.1.2 — Incremental load, multi-batch source, single-batch data
# ===========================================================================

def test_4_2_1_2_1_incremental_existing_bk_new_hd_inserted(
    seed, run_select, dump
):
    """Existing BK has a new HD → inserted."""
    seed("DV.RAW_VAULT.SAT_ORDER", [
        _t("A", "1", "2026-01-01"),
        _t("B", "1", "2026-01-01"),
    ])
    seed("RAW_DB.STAGE.STG_ORDERS", [
        _s("A", "2", "2026-01-02"),
    ])
    dump("DV.RAW_VAULT.SAT_ORDER",  label="4.2.1.2.1 target")
    dump("RAW_DB.STAGE.STG_ORDERS", label="4.2.1.2.1 stage")

    sql = _sat(is_incremental=True).to_sql()
    rows = run_select(sql)
    dump(sql, label="4.2.1.2.1 result")

    assert _triples(rows) == {("A", "2", "2026-01-02")}


def test_4_2_1_2_2_incremental_existing_bk_same_hd_not_inserted(
    seed, run_select, dump
):
    """Existing BK has the same HD as existing → not inserted."""
    seed("DV.RAW_VAULT.SAT_ORDER", [
        _t("A", "1", "2026-01-01"),
        _t("B", "1", "2026-01-01"),
    ])
    seed("RAW_DB.STAGE.STG_ORDERS", [
        _s("A", "1", "2026-01-02"),
    ])
    dump("DV.RAW_VAULT.SAT_ORDER",  label="4.2.1.2.2 target")
    dump("RAW_DB.STAGE.STG_ORDERS", label="4.2.1.2.2 stage")

    sql = _sat(is_incremental=True).to_sql()
    rows = run_select(sql)
    dump(sql, label="4.2.1.2.2 result")

    assert _triples(rows) == set()


def test_4_2_1_2_3_incremental_new_bk_inserted(seed, run_select, dump):
    """New BK → inserted."""
    seed("DV.RAW_VAULT.SAT_ORDER", [
        _t("A", "1", "2026-01-01"),
        _t("B", "1", "2026-01-01"),
    ])
    seed("RAW_DB.STAGE.STG_ORDERS", [
        _s("C", "1", "2026-01-02"),
    ])
    dump("DV.RAW_VAULT.SAT_ORDER",  label="4.2.1.2.3 target")
    dump("RAW_DB.STAGE.STG_ORDERS", label="4.2.1.2.3 stage")

    sql = _sat(is_incremental=True).to_sql()
    rows = run_select(sql)
    dump(sql, label="4.2.1.2.3 result")

    assert _triples(rows) == {("C", "1", "2026-01-02")}


# ===========================================================================
# 4.2.2.1 — Initial load, multi-batch source, multi-batch data
# ===========================================================================

def test_4_2_2_1_1_initial_one_bk_same_hd_consecutive_earliest_inserted(
    seed, run_select, dump
):
    """One BK has the same HD over consecutive batches → earliest inserted."""
    seed("RAW_DB.STAGE.STG_ORDERS", [
        _s("A", "1", "2026-01-01"),
        _s("A", "1", "2026-01-02"),
    ])
    dump("RAW_DB.STAGE.STG_ORDERS", label="4.2.2.1.1 stage")

    sql = _sat(is_incremental=False).to_sql()
    rows = run_select(sql)
    dump(sql, label="4.2.2.1.1 result")

    assert _triples(rows) == {("A", "1", "2026-01-01")}


def test_4_2_2_1_2_initial_one_bk_diff_hd_consecutive_both_inserted(
    seed, run_select, dump
):
    """One BK has different HDs over consecutive batches → both inserted."""
    seed("RAW_DB.STAGE.STG_ORDERS", [
        _s("A", "1", "2026-01-01"),
        _s("A", "2", "2026-01-02"),
    ])
    dump("RAW_DB.STAGE.STG_ORDERS", label="4.2.2.1.2 stage")

    sql = _sat(is_incremental=False).to_sql()
    rows = run_select(sql)
    dump(sql, label="4.2.2.1.2 result")

    assert _triples(rows) == {
        ("A", "1", "2026-01-01"),
        ("A", "2", "2026-01-02"),
    }


# ===========================================================================
# 4.2.2.2 — Incremental load, multi-batch source, multi-batch data
# ===========================================================================

def test_4_2_2_2_1_incremental_new_bk_same_hd_consecutive_earliest_inserted(
    seed, run_select, dump
):
    """New BK has the same HD over consecutive batches → earliest inserted."""
    seed("DV.RAW_VAULT.SAT_ORDER", [
        _t("A", "1", "2026-01-01"),
    ])
    seed("RAW_DB.STAGE.STG_ORDERS", [
        _s("B", "1", "2026-01-02"),
        _s("B", "1", "2026-01-03"),
    ])
    dump("DV.RAW_VAULT.SAT_ORDER",  label="4.2.2.2.1 target")
    dump("RAW_DB.STAGE.STG_ORDERS", label="4.2.2.2.1 stage")

    sql = _sat(is_incremental=True).to_sql()
    rows = run_select(sql)
    dump(sql, label="4.2.2.2.1 result")

    assert _triples(rows) == {("B", "1", "2026-01-02")}


def test_4_2_2_2_2_incremental_new_bk_diff_hd_consecutive_both_inserted(
    seed, run_select, dump
):
    """New BK has different HDs over consecutive batches → both inserted."""
    seed("DV.RAW_VAULT.SAT_ORDER", [
        _t("A", "1", "2026-01-01"),
    ])
    seed("RAW_DB.STAGE.STG_ORDERS", [
        _s("B", "1", "2026-01-02"),
        _s("B", "2", "2026-01-03"),
    ])
    dump("DV.RAW_VAULT.SAT_ORDER",  label="4.2.2.2.2 target")
    dump("RAW_DB.STAGE.STG_ORDERS", label="4.2.2.2.2 stage")

    sql = _sat(is_incremental=True).to_sql()
    rows = run_select(sql)
    dump(sql, label="4.2.2.2.2 result")

    assert _triples(rows) == {
        ("B", "1", "2026-01-02"),
        ("B", "2", "2026-01-03"),
    }


def test_4_2_2_2_3_incremental_existing_bk_same_hd_as_existing_no_inserts(
    seed, run_select, dump
):
    """Existing BK, same HD over batches and equal to existing → no inserts."""
    seed("DV.RAW_VAULT.SAT_ORDER", [
        _t("A", "1", "2026-01-01"),
    ])
    seed("RAW_DB.STAGE.STG_ORDERS", [
        _s("A", "1", "2026-01-02"),
        _s("A", "1", "2026-01-03"),
    ])
    dump("DV.RAW_VAULT.SAT_ORDER",  label="4.2.2.2.3 target")
    dump("RAW_DB.STAGE.STG_ORDERS", label="4.2.2.2.3 stage")

    sql = _sat(is_incremental=True).to_sql()
    rows = run_select(sql)
    dump(sql, label="4.2.2.2.3 result")

    assert _triples(rows) == set()


def test_4_2_2_2_4_incremental_existing_bk_same_hd_diff_existing_earliest_inserted(
    seed, run_select, dump
):
    """Existing BK, same HD over batches but different from existing → earliest inserted."""
    seed("DV.RAW_VAULT.SAT_ORDER", [
        _t("A", "1", "2026-01-01"),
    ])
    seed("RAW_DB.STAGE.STG_ORDERS", [
        _s("A", "2", "2026-01-02"),
        _s("A", "2", "2026-01-03"),
    ])
    dump("DV.RAW_VAULT.SAT_ORDER",  label="4.2.2.2.4 target")
    dump("RAW_DB.STAGE.STG_ORDERS", label="4.2.2.2.4 stage")

    sql = _sat(is_incremental=True).to_sql()
    rows = run_select(sql)
    dump(sql, label="4.2.2.2.4 result")

    assert _triples(rows) == {("A", "2", "2026-01-02")}


def test_4_2_2_2_5_incremental_existing_bk_diff_hd_first_eq_existing_only_later_inserted(
    seed, run_select, dump
):
    """Existing BK, different HDs over batches, first HD = existing → only later inserted."""
    seed("DV.RAW_VAULT.SAT_ORDER", [
        _t("A", "1", "2026-01-01"),
    ])
    seed("RAW_DB.STAGE.STG_ORDERS", [
        _s("A", "1", "2026-01-02"),
        _s("A", "2", "2026-01-03"),
    ])
    dump("DV.RAW_VAULT.SAT_ORDER",  label="4.2.2.2.5 target")
    dump("RAW_DB.STAGE.STG_ORDERS", label="4.2.2.2.5 stage")

    sql = _sat(is_incremental=True).to_sql()
    rows = run_select(sql)
    dump(sql, label="4.2.2.2.5 result")

    assert _triples(rows) == {("A", "2", "2026-01-03")}


def test_4_2_2_2_6_incremental_existing_bk_diff_hd_first_neq_existing_both_inserted(
    seed, run_select, dump
):
    """Existing BK, different HDs over batches, first HD ≠ existing → both inserted."""
    seed("DV.RAW_VAULT.SAT_ORDER", [
        _t("A", "1", "2026-01-01"),
    ])
    seed("RAW_DB.STAGE.STG_ORDERS", [
        _s("A", "2", "2026-01-02"),
        _s("A", "3", "2026-01-03"),
    ])
    dump("DV.RAW_VAULT.SAT_ORDER",  label="4.2.2.2.6 target")
    dump("RAW_DB.STAGE.STG_ORDERS", label="4.2.2.2.6 stage")

    sql = _sat(is_incremental=True).to_sql()
    rows = run_select(sql)
    dump(sql, label="4.2.2.2.6 result")

    assert _triples(rows) == {
        ("A", "2", "2026-01-02"),
        ("A", "3", "2026-01-03"),
    }
