"""
AST-shape assertions for SatelliteGenerator (sat_v0) output.

Where test_satellite.py confirms substrings appear in the generated SQL,
these tests parse the SQL back into a sqlglot AST and assert structural
properties that substring matches cannot — e.g. that the HWM filter uses
`>` not `>=`, that the dedup LAG window partitions by parent_hk and orders
by ldts, that the latest-entries CTE orders DESC, that the single-batch
branch actually skips the dedup CTE and drops the `rn = 1` NOT EXISTS clause.

These catch the class of regressions where the SQL "still mentions LAG" but
the operator, the partition column, or the CTE wiring has silently broken.
"""
from __future__ import annotations

import sqlglot
from sqlglot import exp

from datavault4sqlglot.config import config
from datavault4sqlglot.generators.satellite import SatelliteGenerator
from datavault4sqlglot.metadata import SourceModel


def _parse(sql: str) -> exp.Expression:
    return sqlglot.parse_one(sql, dialect=config.dialect)


def _find_cte(tree: exp.Expression, alias: str) -> exp.CTE | None:
    for cte in tree.find_all(exp.CTE):
        if cte.alias_or_name == alias:
            return cte
    return None


def _find_window(node: exp.Expression, fn_type: type) -> exp.Window | None:
    """Return the first Window whose .this is an instance of fn_type."""
    for w in node.find_all(exp.Window):
        if isinstance(w.this, fn_type):
            return w
    return None


def _sat(
    *,
    is_incremental: bool,
    source_is_single_batch: bool = False,
) -> SatelliteGenerator:
    return SatelliteGenerator(
        target_table="SAT_ORDER",
        source_model=SourceModel(
            table_name="STG_ORDERS",
            load_date_col="LOAD_DATE",
            record_source_col="RECORD_SOURCE",
        ),
        parent_hash_key="HK_ORDER_H",
        hash_diff="HD_ORDER",
        payload=["ORDER_STATUS"],
        is_incremental=is_incremental,
        source_is_single_batch=source_is_single_batch,
    )


# ---------------------------------------------------------------------------
# HWM filter — strict-GT, COALESCE with beginning_of_all_times, EOA exclusion
# ---------------------------------------------------------------------------
def test_hwm_filter_uses_strict_gt_not_gte():
    """The HWM ldts filter must be `>` — `>=` would cause duplicate inserts on overlap."""
    tree = _parse(_sat(is_incremental=True).to_sql())
    src_cte = _find_cte(tree, "src_new")
    assert src_cte is not None

    where = src_cte.find(exp.Where)
    assert where is not None, "src_new must have a WHERE clause when incremental"

    gts = list(where.find_all(exp.GT))
    gtes = list(where.find_all(exp.GTE))
    assert gts, "src_new WHERE must contain a strict-greater-than comparison"
    assert not gtes, "src_new WHERE must not use >= (would duplicate equal-ldts rows)"


def test_hwm_filter_coalesces_with_beginning_of_all_times():
    """Cold-start safety: COALESCE must wrap MAX with beginning_of_all_times."""
    beginning_of_all_times = "1900-01-01"
    config.beginning_of_all_times = beginning_of_all_times

    tree = _parse(_sat(is_incremental=True).to_sql())
    src_cte = _find_cte(tree, "src_new")
    assert src_cte is not None

    coalesces = list(src_cte.find_all(exp.Coalesce))
    assert coalesces, "src_new must COALESCE the HWM lookup with beginning_of_all_times"
    literals = [
        lit.this for c in coalesces for lit in c.find_all(exp.Literal) if lit.is_string
    ]
    assert beginning_of_all_times in literals, f"COALESCE must fall back to {beginning_of_all_times!r}, got literals={literals}"


def test_hwm_subquery_excludes_end_of_all_times_rows():
    """The HWM subquery's own WHERE must skip rows where ldts = end_of_all_times."""
    end_of_all_times = "9999-12-31"
    config.end_of_all_times = end_of_all_times

    tree = _parse(_sat(is_incremental=True).to_sql())
    src_cte = _find_cte(tree, "src_new")
    assert src_cte is not None

    # The HWM subquery is the inner Select inside src_new's WHERE — its own
    # WHERE clause must compare ldts to the end_of_all_times literal.
    inner_selects = list(src_cte.find_all(exp.Select))
    end_of_all_times_literals = []
    for sel in inner_selects:
        if sel is src_cte.this:  # skip the outer src_new SELECT itself
            continue
        for lit in sel.find_all(exp.Literal):
            if lit.is_string and lit.this == end_of_all_times:
                end_of_all_times_literals.append(lit)
    assert end_of_all_times_literals, f"HWM subquery must filter out ldts = {end_of_all_times!r}"


# ---------------------------------------------------------------------------
# Multi-batch dedup — LAG and ROW_NUMBER windows
# ---------------------------------------------------------------------------
def test_dedup_lag_window_partitions_by_parent_hk_orders_by_ldts():
    """LAG(hash_diff) in the dedup CTE must partition by parent_hk, order by ldts."""
    tree = _parse(_sat(is_incremental=False).to_sql())
    dedup_cte = _find_cte(tree, "deduplicated_numbered_source")
    assert dedup_cte is not None

    lag_win = _find_window(dedup_cte, exp.Lag)
    assert lag_win is not None, "dedup CTE must use a LAG window"

    partition_cols = [c.name for c in lag_win.args.get("partition_by", [])]
    assert "HK_ORDER_H" in partition_cols, f"LAG partition cols={partition_cols}"

    order = lag_win.args.get("order")
    assert order is not None, "LAG window needs ORDER BY"
    order_cols = [o.this.name for o in order.expressions]
    assert "ldts" in order_cols or "LOAD_DATE" in order_cols, (
        f"LAG order cols={order_cols}"
    )


def test_incremental_dedup_adds_rn_row_number_window():
    """Incremental + multi-batch must add an `rn` ROW_NUMBER column to the dedup CTE."""
    tree = _parse(_sat(is_incremental=True).to_sql())
    dedup_cte = _find_cte(tree, "deduplicated_numbered_source")
    assert dedup_cte is not None

    rn_win = _find_window(dedup_cte, exp.RowNumber)
    assert rn_win is not None, "dedup CTE must add ROW_NUMBER for the rn=1 NOT EXISTS check"

    partition_cols = [c.name for c in rn_win.args.get("partition_by", [])]
    assert "HK_ORDER_H" in partition_cols, f"rn partition cols={partition_cols}"

    # ASC ordering — earliest within partition gets rn=1.
    order = rn_win.args.get("order")
    assert order is not None
    assert not any(o.args.get("desc") for o in order.expressions), (
        "rn ROW_NUMBER must order ldts ASC so the earliest row is rn=1"
    )


# ---------------------------------------------------------------------------
# latest_entries_in_sat — DESC ordering picks the most recent target row
# ---------------------------------------------------------------------------
def test_latest_entries_window_orders_ldts_desc():
    """latest_entries_in_sat must order ROW_NUMBER ldts DESC to pick the latest row per BK."""
    tree = _parse(_sat(is_incremental=True).to_sql())
    latest_cte = _find_cte(tree, "latest_entries_in_sat")
    assert latest_cte is not None

    rn_win = _find_window(latest_cte, exp.RowNumber)
    assert rn_win is not None, "latest_entries_in_sat must use ROW_NUMBER"

    order = rn_win.args.get("order")
    assert order is not None and order.expressions, "latest CTE window needs ORDER BY"
    assert all(o.args.get("desc") for o in order.expressions), (
        "latest_entries_in_sat ORDER BY must be DESC — otherwise the oldest row wins"
    )


# ---------------------------------------------------------------------------
# Multi-batch NOT EXISTS — must include the rn = 1 restriction
# ---------------------------------------------------------------------------
def test_not_exists_includes_rn_one_clause_for_multi_batch():
    """Multi-batch incremental: NOT EXISTS must restrict the comparison to rn=1."""
    tree = _parse(_sat(is_incremental=True, source_is_single_batch=False).to_sql())
    insert_cte = _find_cte(tree, "records_to_insert")
    assert insert_cte is not None

    # Look for a comparison whose LHS column is named "rn" against literal 1.
    rn_eq_one = False
    for eq in insert_cte.find_all(exp.EQ):
        lhs, rhs = eq.this, eq.expression
        if (
            isinstance(lhs, exp.Column)
            and lhs.name == "rn"
            and isinstance(rhs, exp.Literal)
            and rhs.this == "1"
        ):
            rn_eq_one = True
            break
    assert rn_eq_one, "multi-batch NOT EXISTS must include `rn = 1`"


# ---------------------------------------------------------------------------
# source_is_single_batch — dedup CTE skipped, NOT EXISTS drops the rn clause
# ---------------------------------------------------------------------------
def test_single_batch_skips_dedup_cte():
    """source_is_single_batch=True must skip the deduplicated_numbered_source CTE entirely."""
    tree = _parse(_sat(is_incremental=True, source_is_single_batch=True).to_sql())
    assert _find_cte(tree, "deduplicated_numbered_source") is None, (
        "single-batch path must not emit the LAG/QUALIFY dedup CTE"
    )
    # records_to_insert should read from src_new directly.
    insert_cte = _find_cte(tree, "records_to_insert")
    assert insert_cte is not None
    from_table = insert_cte.this.find(exp.From)
    assert from_table is not None
    assert from_table.this.name == "src_new", (
        f"records_to_insert must read from src_new, got {from_table.this.name!r}"
    )


def test_single_batch_not_exists_omits_rn_clause():
    """source_is_single_batch=True must drop the `rn = 1` clause from NOT EXISTS."""
    tree = _parse(_sat(is_incremental=True, source_is_single_batch=True).to_sql())
    insert_cte = _find_cte(tree, "records_to_insert")
    assert insert_cte is not None

    for eq in insert_cte.find_all(exp.EQ):
        lhs = eq.this
        assert not (isinstance(lhs, exp.Column) and lhs.name == "rn"), (
            "single-batch NOT EXISTS must not reference `rn` — the dedup CTE that "
            "produced it was skipped"
        )


# ---------------------------------------------------------------------------
# Initial mode — incremental-only CTEs and HWM must be absent
# ---------------------------------------------------------------------------
def test_initial_mode_omits_incremental_ctes_and_hwm():
    """is_incremental=False: no latest_entries_in_sat, no records_to_insert, no HWM WHERE."""
    tree = _parse(_sat(is_incremental=False).to_sql())

    assert _find_cte(tree, "latest_entries_in_sat") is None
    assert _find_cte(tree, "records_to_insert") is None

    src_cte = _find_cte(tree, "src_new")
    assert src_cte is not None
    assert src_cte.find(exp.Where) is None, (
        "initial-mode src_new must not carry an HWM WHERE clause"
    )
