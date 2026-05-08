from __future__ import annotations

from typing import Optional

from sqlglot import exp

from datavault4sqlglot.config import config
from datavault4sqlglot.generators.base import BaseGenerator


class EffectivitySatelliteGenerator(BaseGenerator):
    """
    Generates SQL for a Data Vault Effectivity Satellite (Eff Sat).

    An Effectivity Satellite tracks whether a Link relationship is currently
    active by reading from a historized source (link sat_v0 or raw link stage)
    and adding:

        ledts     = COALESCE(LEAD(ldts) OVER (PARTITION BY driving_hash_key
                                               ORDER BY ldts), end_of_all_times)
        is_active = CASE WHEN ledts = end_of_all_times THEN TRUE ELSE FALSE END

    The ``driving_hash_key`` identifies the entity "owning" the relationship
    (e.g. the order side for an order-customer link).

    Args:
        target_table:       Target effectivity satellite table.
        source_table:       Source table (link sat_v0 or staging table).
        parent_hash_key:    The link's hash key column.
        driving_hash_key:   Foreign hash key that partitions the LEAD window.
        add_is_active:      Whether to add an IS_ACTIVE boolean column.
        is_active_col:      Column name for the is-active flag.
        ledts_alias:        Column name for the load-end-timestamp.
        end_of_all_times:   EOA sentinel value (overrides config).
    """

    def __init__(
        self,
        target_table: str,
        source_table: str,
        parent_hash_key: str,
        driving_hash_key: str,
        source_schema: Optional[str] = None,
        source_database: Optional[str] = None,
        target_schema: Optional[str] = None,
        target_database: Optional[str] = None,
        add_is_active: bool = True,
        is_active_col: str = "is_active",
        ledts_alias: Optional[str] = None,
        end_of_all_times: Optional[str] = None,
        dialect: Optional[str] = None,
    ) -> None:
        super().__init__(target_table, target_schema, target_database, dialect=dialect)
        self.source_table = source_table
        self.source_schema = source_schema
        self.source_database = source_database
        self.parent_hash_key = parent_hash_key
        self.driving_hash_key = driving_hash_key
        self.add_is_active = add_is_active
        self.is_active_col = is_active_col
        self.ledts_alias = ledts_alias or config.ledts_alias
        self.end_of_all_times = end_of_all_times or config.end_of_all_times

    def generate_sql(self) -> exp.Expression:
        parent_hk_col = self.parent_hash_key
        driving_hk_col = self.driving_hash_key
        ldts_col = config.ldts_alias
        ledts_col = self.ledts_alias
        eoa = self.end_of_all_times

        src_exp = self._get_table_expression(
            self.source_table, self.source_schema, self.source_database
        )

        # ------------------------------------------------------------------
        # CTE 1: end_dated_source
        # LEAD(ldts) OVER (PARTITION BY driving_hk ORDER BY ldts) → ledts
        # ------------------------------------------------------------------
        lead_window = exp.Window(
            this=exp.Lead(this=exp.column(ldts_col)),
            partition_by=[exp.column(driving_hk_col)],
            order=exp.Order(
                expressions=[exp.Ordered(this=exp.column(ldts_col))]
            ),
        )
        ledts_expr = exp.Coalesce(
            this=lead_window,
            expressions=[exp.Literal.string(eoa)],
        ).as_(exp.Identifier(this=ledts_col, quoted=True))

        end_dated_query = exp.select(exp.Star(), ledts_expr).from_(src_exp)

        # ------------------------------------------------------------------
        # CTE 2: Final select — optionally adds IS_ACTIVE flag
        # ------------------------------------------------------------------
        final_cols: list[exp.Expression] = [exp.Star()]

        if self.add_is_active:
            is_active_expr = (
                exp.Case()
                .when(
                    exp.column(ledts_col).eq(exp.Literal.string(eoa)),
                    exp.true(),
                )
                .else_(exp.false())
            ).as_(exp.Identifier(this=self.is_active_col, quoted=True))
            final_cols.append(is_active_expr)

        final_query = exp.select(*final_cols).from_("end_dated_source")
        final_query = final_query.with_("end_dated_source", as_=end_dated_query)

        return final_query
