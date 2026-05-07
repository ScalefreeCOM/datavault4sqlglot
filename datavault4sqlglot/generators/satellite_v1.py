from __future__ import annotations

from typing import Optional

from sqlglot import exp

from datavault4sqlglot.generators.base import BaseGenerator
from datavault4sqlglot.config import config


class SatelliteV1Generator(BaseGenerator):
    """
    Generates SQL for an end-dated Data Vault Satellite (sat_v1).

    Reads from a sat_v0 table and calculates the load-end-timestamp (ledts)
    using a LEAD window function — matching the datavault4dbt sat_v1 pattern:

        ledts = COALESCE(LEAD(ldts) OVER (PARTITION BY parent_hk ORDER BY ldts),
                         end_of_all_times)
        is_current = CASE WHEN ledts = end_of_all_times THEN TRUE ELSE FALSE END

    Every column from the underlying sat_v0 table is carried through via
    ``SELECT *``; payload columns are not declared explicitly.

    Args:
        sat_v0_table: Source sat_v0 table name.
        parent_hash_key: Hash key column partitioning the satellite.
        hash_diff: Hash diff column name.
        add_is_current: Whether to add an IS_CURRENT boolean column.
        ledts_alias: Column name for the load-end-timestamp (default: ledts_alias from config).
        is_current_col: Column name for the is-current flag.
    """

    def __init__(
        self,
        target_table: str,
        sat_v0_table: str,
        parent_hash_key: str,
        hash_diff: str,
        sat_v0_schema: Optional[str] = None,
        sat_v0_database: Optional[str] = None,
        target_schema: Optional[str] = None,
        target_database: Optional[str] = None,
        add_is_current: bool = True,
        ledts_alias: Optional[str] = None,
        is_current_col: str = "is_current",
        dialect: Optional[str] = None,
    ) -> None:
        super().__init__(target_table, target_schema, target_database, dialect=dialect)
        self.sat_v0_table = sat_v0_table
        self.sat_v0_schema = sat_v0_schema
        self.sat_v0_database = sat_v0_database
        self.parent_hash_key = parent_hash_key
        self.hash_diff = hash_diff
        self.add_is_current = add_is_current
        self.ledts_alias = ledts_alias or config.ledts_alias
        self.is_current_col = is_current_col

    def generate_sql(self) -> exp.Expression:
        parent_hk_col = self.parent_hash_key
        hash_diff_col = self.hash_diff
        ldts_col = config.ldts_alias
        rsrc_col = config.rsrc_alias
        ledts_col = self.ledts_alias
        eoa = config.end_of_all_times

        src_exp = self._get_table_expression(
            self.sat_v0_table, self.sat_v0_schema, self.sat_v0_database
        )

        # ---------------------------------------------------------
        # CTE 1: end_dated_source
        # Calculates ledts = COALESCE(LEAD(ldts) OVER (...), end_of_all_times)
        # ---------------------------------------------------------
        lead_window = exp.Window(
            this=exp.Lead(this=exp.column(ldts_col)),
            partition_by=[exp.column(parent_hk_col)],
            order=exp.Order(
                expressions=[exp.Ordered(this=exp.column(ldts_col))]
            ),
        )
        ledts_expr = exp.Coalesce(
            this=lead_window,
            expressions=[exp.Literal.string(eoa)],
        ).as_(exp.Identifier(this=ledts_col, quoted=True))

        base_cols = [
            exp.Star(),
            ledts_expr,
        ]
        end_dated_query = exp.select(*base_cols).from_(src_exp)

        # ---------------------------------------------------------
        # CTE 2: Final select with optional IS_CURRENT flag
        # ---------------------------------------------------------
        final_cols: list[exp.Expression] = [exp.Star()]

        if self.add_is_current:
            is_current_expr = (
                exp.Case()
                .when(
                    exp.column(ledts_col).eq(exp.Literal.string(eoa)),
                    exp.true(),
                )
                .else_(exp.false())
            ).as_(exp.Identifier(this=self.is_current_col, quoted=True))
            final_cols.append(is_current_expr)

        final_query = exp.select(*final_cols).from_("end_dated_source")
        final_query = final_query.with_("end_dated_source", as_=end_dated_query)

        return final_query
