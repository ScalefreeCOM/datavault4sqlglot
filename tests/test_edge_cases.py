"""
Edge cases and behavior pinning across generators.

These tests cover three categories:

1. Documented divergences from datavault4dbt — port-specific design choices
   that are intentional but should not silently change.

2. Surface bugs found while auditing — written as `xfail` so they are visible
   in test output without failing the suite. Convert to passing tests once
   the underlying generator is hardened.

3. Defensive checks against silent SQL corruption (empty projections, etc.).

If a test in section 2 starts passing, that means the bug got fixed — flip the
xfail marker to a regular pass and update the assertion to lock in the fix.
"""
from __future__ import annotations

import pytest
import sqlglot
from sqlglot import exp

from datavault4sqlglot.generators.hub import HubGenerator
from datavault4sqlglot.generators.satellite import SatelliteGenerator
from datavault4sqlglot.generators.stage import StageGenerator
from datavault4sqlglot.metadata import SourceBinding, SourceModel, StageModel


# ===========================================================================
# 1. Documented divergence — mixed rsrc_static across hub sources
# ===========================================================================
def test_hub_mixed_rsrc_static_filters_only_source_with_statics():
    """
    Port behavior: when one source has rsrc_statics and another does not,
    the source WITH statics still gets a per-source HWM filter; the source
    WITHOUT statics receives no filter at all.

    Divergence from datavault4dbt: the dbt macro disables HWM for ALL
    sources in this mixed scenario (conservative). The port is more
    aggressive — it filters where it can. Both are safe (no data loss),
    but they produce different SQL on the unfiltered source. This test
    pins the port behavior so any future change is intentional.
    """
    gen = HubGenerator(
        target_table="HUB_ORDER",
        sources=[
            SourceBinding(
                source=SourceModel(table_name="STG_SAP"),
                rsrc_statics=["SAP/%"],
            ),
            SourceBinding(
                source=SourceModel(table_name="STG_WEB"),
                # No rsrc_statics — the divergence point.
            ),
        ],
        hashkey="HK_ORDER_H",
        business_keys=["ID"],
        is_incremental=True,
    )
    tree = sqlglot.parse_one(gen.to_sql())

    # The HWM CTE exists because at least one source contributes statics.
    hwm = next(
        (c for c in tree.find_all(exp.CTE)
         if c.alias_or_name == "max_ldts_per_rsrc_static_in_target"),
        None,
    )
    assert hwm is not None, "HWM CTE expected when any source has statics"

    # The source WITH statics has a WHERE clause (per-source HWM filter).
    src0 = next(c for c in tree.find_all(exp.CTE) if c.alias_or_name == "src_new_0")
    assert src0.find(exp.Where) is not None, (
        "src_new_0 (with statics) must carry the per-source HWM WHERE"
    )

    # The source WITHOUT statics has NO WHERE clause — port-specific behavior.
    src1 = next(c for c in tree.find_all(exp.CTE) if c.alias_or_name == "src_new_1")
    assert src1.find(exp.Where) is None, (
        "src_new_1 (no statics) currently receives no HWM filter — port "
        "diverges from dbt here. Update this test if the policy changes."
    )


# ===========================================================================
# 2. Surface bugs (xfail) — generators silently emit broken or meaningless SQL
# ===========================================================================
@pytest.mark.xfail(
    reason="HubGenerator does not validate business_keys >= 1; emits a "
           "structurally valid but semantically meaningless hub. LinkGenerator "
           "validates foreign_hash_keys >= 2 — Hub should validate similarly.",
    strict=True,
)
def test_hub_empty_business_keys_should_raise():
    gen = HubGenerator(
        target_table="HUB_X",
        sources=[SourceBinding(source=SourceModel(table_name="STG"))],
        hashkey="HK_X",
        business_keys=[],
    )
    with pytest.raises(ValueError, match="business_keys"):
        gen.generate_sql()


@pytest.mark.xfail(
    reason="StageGenerator with no hashed_columns and include_source_columns=False "
           "emits 'SELECT FROM <table>' — sqlglot parses it leniently but real "
           "engines reject it. Should raise a configuration error or fall back "
           "to SELECT *.",
    strict=True,
)
def test_stage_no_projection_emits_invalid_sql():
    src = StageModel(table_name="X", include_source_columns=False)
    sql = StageGenerator(source_model=src).to_sql()
    parsed = sqlglot.parse_one(sql, dialect="snowflake")
    top = parsed.find(exp.Select)
    assert top is not None
    # An empty projection list is the core defect — assert that a real
    # database would accept this SQL by requiring at least one expression.
    assert len(top.expressions) > 0, (
        "SELECT must project at least one column; got an empty projection."
    )


# ===========================================================================
# 3. Behavior pinning — semantically thin but technically valid
# ===========================================================================
def test_satellite_empty_payload_emits_valid_sql():
    """
    A satellite with no payload is semantically pointless but should still
    produce parseable SQL — there is no 'wrong' answer here, but if the
    generator ever starts emitting `SELECT , ldts FROM ...` we want to know.
    """
    gen = SatelliteGenerator(
        target_table="SAT_EMPTY",
        source_model=SourceModel(table_name="STG"),
        parent_hash_key="HK_X",
        hash_diff="HD_X",
        payload=[],
    )
    sql = gen.to_sql()
    sqlglot.parse_one(sql, dialect="snowflake")


def test_stage_no_hashed_columns_with_source_columns_emits_valid_sql():
    """SELECT * fallback when no hash columns are configured but source columns are kept."""
    src = StageModel(table_name="X", include_source_columns=True)
    sql = StageGenerator(source_model=src).to_sql()
    parsed = sqlglot.parse_one(sql, dialect="snowflake")
    # Top-level SELECT must contain a star.
    selects = list(parsed.find_all(exp.Select))
    assert any(any(isinstance(p, exp.Star) for p in s.expressions) for s in selects), (
        "SELECT * expected when no hash columns and include_source_columns=True"
    )
