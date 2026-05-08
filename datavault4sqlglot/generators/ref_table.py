from __future__ import annotations

from typing import List, Optional

from sqlglot import exp

from datavault4sqlglot.config import config
from datavault4sqlglot.generators.base import BaseGenerator
from datavault4sqlglot.metadata import SourceModel


class RefTableGenerator(BaseGenerator):
    """
    Generates SQL for a Data Vault Reference Table.

    A Reference Table is a standalone lookup table — not attached to a parent
    hub entity. It keeps only the **latest** record per ``ref_hash_key``,
    making it a full-replace rather than append structure.

    No hash diff column is produced. The payload is always overwritten with
    the newest source values.

    Args:
        target_table:       Target reference table name.
        source_model:       Physical source table reference.
        ref_hash_key:       Hash key column that identifies each reference entry.
        ref_key_columns:    Optional raw business key columns to include alongside
                            the hash key (e.g. country_code, status_code).
        payload:            Descriptive payload columns.
        is_incremental:     Whether to apply a global HWM filter before dedup.
        disable_hwm:        Skip the HWM filter even when incremental.
        additional_columns: Extra columns to carry through.
    """

    def __init__(
        self,
        target_table: str,
        source_model: SourceModel,
        ref_hash_key: str,
        ref_key_columns: Optional[List[str]] = None,
        target_schema: Optional[str] = None,
        target_database: Optional[str] = None,
        payload: Optional[List[str]] = None,
        is_incremental: bool = False,
        disable_hwm: bool = False,
        additional_columns: Optional[List[str]] = None,
        end_of_all_times: Optional[str] = None,
        beginning_of_all_times: Optional[str] = None,
        dialect: Optional[str] = None,
    ) -> None:
        super().__init__(target_table, target_schema, target_database, dialect=dialect)
        self.source_model = source_model
        self.ref_hash_key = ref_hash_key
        self.ref_key_columns = ref_key_columns or []
        self.payload = payload or []
        self.is_incremental = is_incremental
        self.disable_hwm = disable_hwm
        self.additional_columns = additional_columns or []
        self.end_of_all_times = end_of_all_times or config.end_of_all_times
        self.beginning_of_all_times = beginning_of_all_times or config.beginning_of_all_times

    def generate_sql(self) -> exp.Expression:
        src = self.source_model
        ref_hk_col = self.ref_hash_key
        ldts_col = config.ldts_alias
        rsrc_col = config.rsrc_alias
        boa = self.beginning_of_all_times

        target_exp = self._get_table_expression(
            self.target_table, self.target_schema, self.target_database
        )
        src_table_exp = self._get_table_expression(
            src.table_name, src.schema_name, src.database
        )
        src_ldts = src.load_date_col or ldts_col
        src_rsrc = src.record_source_col or rsrc_col

        ctes: dict = {}

        # ------------------------------------------------------------------
        # 1. Source CTE with optional global HWM filter
        # ------------------------------------------------------------------
        select_exprs = (
            [exp.column(ref_hk_col)]
            + [exp.column(c) for c in self.ref_key_columns]
            + [exp.column(p) for p in self.payload]
            + [exp.column(c) for c in self.additional_columns]
            + [exp.column(src_ldts).as_(ldts_col), exp.column(src_rsrc).as_(rsrc_col)]
        )
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
                    exp.column(ldts_col).neq(exp.Literal.string(self.end_of_all_times))
                )
            )
            src_query = src_query.where(
                exp.column(src_ldts) > exp.Paren(this=hwm_sub)
            )

        ctes["src_new"] = src_query

        # ------------------------------------------------------------------
        # 2. Deduplication — latest record per ref_hash_key (ROW_NUMBER DESC)
        # ------------------------------------------------------------------
        window_expression = exp.Window(
            this=exp.RowNumber(),
            partition_by=[exp.column(ref_hk_col)],
            order=exp.Order(
                expressions=[exp.Ordered(this=exp.column(ldts_col), desc=True)]
            ),
        )
        ctes["latest_records"] = (
            exp.select("*").from_("src_new").qualify(window_expression.eq(1))
        )

        # ------------------------------------------------------------------
        # 3. Final SELECT + assemble CTEs
        # ------------------------------------------------------------------
        final_query = exp.select("*").from_("latest_records")
        for name, expression in ctes.items():
            final_query = final_query.with_(name, as_=expression)

        return final_query
