from __future__ import annotations

from typing import List, Optional

from sqlglot import exp

from datavault4sqlglot.generators.base import BaseGenerator
from datavault4sqlglot.metadata import SourceModel
from datavault4sqlglot.config import config


class NonHistorizedSatGenerator(BaseGenerator):
    """
    Generates SQL for a Non-Historized Satellite (nh_sat).

    Loads the latest snapshot per parent hash key with no history tracking —
    no hashdiff, no deduplication of changes. Only new parent hash keys are
    inserted on incremental loads. Matches the datavault4dbt nh_sat pattern.
    """

    def __init__(
        self,
        target_table: str,
        source_model: SourceModel,
        parent_hash_key: str,
        target_schema: Optional[str] = None,
        target_database: Optional[str] = None,
        payload: Optional[List[str]] = None,
        is_incremental: bool = False,
        disable_hwm: bool = False,
        source_is_single_batch: bool = False,
        additional_columns: Optional[List[str]] = None,
        end_of_all_times: Optional[str] = None,
        beginning_of_all_times: Optional[str] = None,
        dialect: Optional[str] = None,
    ) -> None:
        super().__init__(target_table, target_schema, target_database, dialect=dialect)
        self.source_model = source_model
        self.parent_hash_key = parent_hash_key
        self.payload = payload or []
        self.is_incremental = is_incremental
        self.disable_hwm = disable_hwm
        self.source_is_single_batch = source_is_single_batch
        self.additional_columns = additional_columns or []
        self.end_of_all_times = end_of_all_times or config.end_of_all_times
        self.beginning_of_all_times = beginning_of_all_times or config.beginning_of_all_times

    def generate_sql(self) -> exp.Expression:
        parent_hk_col = self.parent_hash_key
        ldts_col = config.ldts_alias
        rsrc_col = config.rsrc_alias
        boa = self.beginning_of_all_times

        src = self.source_model
        src_table = self._get_table_expression(
            src.table_name, src.schema_name, src.database
        )
        target_exp = self._get_table_expression(
            self.target_table, self.target_schema, self.target_database
        )

        ctes: dict = {}

        # ---------------------------------------------------------
        # 1. source_data — with optional HWM filter and deduplication
        # ---------------------------------------------------------
        src_parent_hk = parent_hk_col
        src_ldts = src.load_date_col or ldts_col
        src_rsrc = src.record_source_col or rsrc_col
        payload = self.payload
        extra_cols = self.additional_columns

        select_exprs = [
            exp.column(src_parent_hk).as_(parent_hk_col),
            *[exp.column(p) for p in payload],
            *[exp.column(col) for col in extra_cols],
            exp.column(src_ldts).as_(ldts_col),
            exp.column(src_rsrc).as_(rsrc_col),
        ]
        source_query = exp.select(*select_exprs).from_(src_table)

        if self.is_incremental and not self.disable_hwm:
            hwm_sub = (
                exp.select(
                    exp.Coalesce(
                        this=exp.Max(this=exp.column(ldts_col)),
                        expressions=[exp.Literal.string(boa)],
                    )
                )
                .from_(target_exp)
                .where(
                    exp.column(ldts_col).neq(
                        exp.Literal.string(self.end_of_all_times)
                    )
                )
            )
            source_query = source_query.where(
                exp.column(src_ldts) > exp.Paren(this=hwm_sub)
            )

        if not self.source_is_single_batch:
            dedup_window = exp.Window(
                this=exp.RowNumber(),
                partition_by=[exp.column(parent_hk_col)],
                order=exp.Order(
                    expressions=[exp.Ordered(this=exp.column(ldts_col), desc=True)]
                ),
            )
            source_query = source_query.qualify(dedup_window.eq(1))

        ctes["source_data"] = source_query
        last_cte = "source_data"

        # ---------------------------------------------------------
        # 2. Incremental — filter to new parent hash keys only
        # ---------------------------------------------------------
        if self.is_incremental:
            target_cte = "distinct_target_hashkeys"
            ctes[target_cte] = exp.select(parent_hk_col).from_(target_exp)

            insert_query = exp.select("*").from_(last_cte).where(
                exp.column(parent_hk_col)
                .isin(exp.select(parent_hk_col).from_(target_cte))
                .not_()
            )
            ctes["records_to_insert"] = insert_query
            last_cte = "records_to_insert"

        # ---------------------------------------------------------
        # 3. Final Select + Assemble CTEs
        # ---------------------------------------------------------
        final_query = exp.select("*").from_(last_cte)
        for name, expression in ctes.items():
            final_query = final_query.with_(name, as_=expression)

        return final_query
