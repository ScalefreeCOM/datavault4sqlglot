from __future__ import annotations

from typing import Dict, List, Optional, Union

from sqlglot import exp

from datavault4sqlglot.generators.base import BaseGenerator
from datavault4sqlglot.metadata import SourceModel
from datavault4sqlglot.config import config


class SatelliteGenerator(BaseGenerator):
    """
    Generates SQL for a Data Vault Satellite entity (sat_v0).

    Satellites are always single-source. Implements consecutive-hashdiff
    deduplication via LAG QUALIFY and change detection via NOT EXISTS against
    the latest target record per parent hash key — matching datavault4dbt sat_v0.

    HWM uses the global MAX(ldts) from the target table (no rsrc_static scoping).
    """

    def __init__(
        self,
        target_table: str,
        source_model: SourceModel,
        parent_hash_key: str,
        hash_diff: Union[str, Dict[str, str]],
        target_schema: Optional[str] = None,
        target_database: Optional[str] = None,
        payload: Optional[List[str]] = None,
        is_incremental: bool = False,
        disable_hwm: bool = False,
        additional_columns: Optional[List[str]] = None,
        end_of_all_times: Optional[str] = None,
        beginning_of_all_times: Optional[str] = None,
        dialect: Optional[str] = None,
    ):
        super().__init__(target_table, target_schema, target_database, dialect=dialect)
        self.source_model = source_model
        self.parent_hash_key = parent_hash_key
        self.hash_diff = hash_diff
        self.payload = payload or []
        self.is_incremental = is_incremental
        self.disable_hwm = disable_hwm
        self.additional_columns = additional_columns or []
        self.end_of_all_times = end_of_all_times or config.end_of_all_times
        self.beginning_of_all_times = beginning_of_all_times or config.beginning_of_all_times

    def generate_sql(self) -> exp.Expression:
        src = self.source_model
        parent_hk_col = self.parent_hash_key
        _, hash_diff_col = self._resolve_column_config(self.hash_diff)
        ldts_col = config.ldts_alias
        rsrc_col = config.rsrc_alias
        boa = self.beginning_of_all_times

        target_exp = self._get_table_expression(
            self.target_table, self.target_schema, self.target_database
        )
        src_table_exp = self._get_table_expression(
            src.table_name, src.schema_name, src.database
        )

        src_parent_hk = parent_hk_col
        src_hd_src, _ = self._resolve_column_config(self.hash_diff)
        src_payload = self.payload
        extra_cols = self.additional_columns
        src_ldts = src.load_date_col or ldts_col
        src_rsrc = src.record_source_col or rsrc_col

        ctes: dict = {}

        # ---------------------------------------------------------
        # 1. Source CTE with optional global HWM filter
        # ---------------------------------------------------------
        select_exprs = [
            exp.column(src_parent_hk).as_(parent_hk_col),
            exp.column(src_hd_src).as_(hash_diff_col),
            *[exp.column(p) for p in src_payload],
            *[exp.column(col) for col in extra_cols],
            exp.column(src_ldts).as_(ldts_col),
            exp.column(src_rsrc).as_(rsrc_col),
        ]
        src_query = exp.select(*select_exprs).from_(src_table_exp)

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
            src_query = src_query.where(
                exp.column(src_ldts) > exp.Paren(this=hwm_sub)
            )

        ctes["src_new"] = src_query

        # ---------------------------------------------------------
        # 2. Deduplication — LAG-based consecutive hashdiff detection
        #
        # QUALIFY CASE WHEN hash_diff = LAG(hash_diff) OVER (PARTITION BY parent_hk ORDER BY ldts)
        #              THEN FALSE ELSE TRUE END
        #
        # Allows the same hashdiff to reappear after a change (A → B → A),
        # unlike PARTITION BY (hk, hd) which would drop the second A entirely.
        #
        # When incremental, also adds rn = ROW_NUMBER() per parent_hk so the
        # NOT EXISTS check below can restrict comparison to rn=1 only — matching
        # datavault4dbt sat_v0. Without this, a re-appearing hashdiff (rn>1 after
        # a change) would be wrongly excluded because it still matches the satellite's
        # latest entry.
        # ---------------------------------------------------------
        lag_window = exp.Window(
            this=exp.Lag(this=exp.column(hash_diff_col)),
            partition_by=[exp.column(parent_hk_col)],
            order=exp.Order(
                expressions=[exp.Ordered(this=exp.column(ldts_col))]
            ),
        )
        qualify_case = (
            exp.Case()
            .when(exp.column(hash_diff_col).eq(lag_window), exp.false())
            .else_(exp.true())
        )
        if self.is_incremental:
            rn_window = exp.Window(
                this=exp.RowNumber(),
                partition_by=[exp.column(parent_hk_col)],
                order=exp.Order(
                    expressions=[exp.Ordered(this=exp.column(ldts_col))]
                ),
            )
            dedup_select = exp.select("*", rn_window.as_("rn"))
        else:
            dedup_select = exp.select("*")
        ctes["deduplicated_numbered_source"] = (
            dedup_select.from_("src_new").qualify(qualify_case)
        )

        # ---------------------------------------------------------
        # 3. Incremental — NOT EXISTS against latest target record per parent_hk
        # ---------------------------------------------------------
        if self.is_incremental:
            latest_target_cte = "latest_entries_in_sat"
            target_window = exp.Window(
                this=exp.RowNumber(),
                partition_by=[exp.column(parent_hk_col)],
                order=exp.Order(
                    expressions=[exp.Ordered(this=exp.column(ldts_col), desc=True)]
                ),
            )
            ctes[latest_target_cte] = (
                exp.select(exp.column(parent_hk_col), exp.column(hash_diff_col))
                .from_(target_exp)
                .qualify(target_window.eq(1))
            )

            # Only the first record per parent_hk (rn=1) is checked against the
            # latest satellite entry. Records with rn>1 always pass through — they
            # represent genuine changes that follow rn=1 within the same batch and
            # must not be filtered even if their hashdiff happens to match the
            # current satellite state (e.g. A→B→A pattern across batches).
            not_exists_sub = (
                exp.select(exp.Literal.number(1))
                .from_(latest_target_cte)
                .where(
                    exp.and_(
                        exp.column(parent_hk_col, table=latest_target_cte).eq(
                            exp.column(parent_hk_col, table="deduplicated_numbered_source")
                        ),
                        exp.column(hash_diff_col, table=latest_target_cte).eq(
                            exp.column(hash_diff_col, table="deduplicated_numbered_source")
                        ),
                        exp.column("rn", table="deduplicated_numbered_source").eq(
                            exp.Literal.number(1)
                        ),
                    )
                )
            )
            ctes["records_to_insert"] = (
                exp.select("*")
                .from_("deduplicated_numbered_source")
                .where(exp.Not(this=exp.Exists(this=not_exists_sub)))
            )
            last_cte = "records_to_insert"
        else:
            last_cte = "deduplicated_numbered_source"

        # ---------------------------------------------------------
        # 4. Final Select + Assemble CTEs
        # ---------------------------------------------------------
        final_query = exp.select("*").from_(last_cte)
        for name, expression in ctes.items():
            final_query = final_query.with_(name, as_=expression)

        return final_query
