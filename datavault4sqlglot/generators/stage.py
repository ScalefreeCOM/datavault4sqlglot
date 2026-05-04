from __future__ import annotations

from typing import Optional

from sqlglot import exp, parse_one

from datavault4sqlglot.generators.base import BaseGenerator
from datavault4sqlglot.metadata import StageModel
from datavault4sqlglot.metadata.source import ColumnDefinition
from datavault4sqlglot.config import config

# Datatype families for ghost record value selection (datavault4dbt convention)
_STRING_TYPES = frozenset({
    "VARCHAR", "CHAR", "NVARCHAR", "NCHAR", "TEXT", "STRING", "CHARACTER", "VARIANT",
})
_NUMERIC_TYPES = frozenset({
    "INT", "INTEGER", "BIGINT", "SMALLINT", "TINYINT", "BYTEINT",
    "NUMBER", "NUMERIC", "DECIMAL", "FLOAT", "DOUBLE", "REAL", "FLOAT4", "FLOAT8",
})
_DATE_TYPES = frozenset({
    "DATE", "TIMESTAMP", "TIMESTAMP_NTZ", "TIMESTAMP_TZ", "TIMESTAMP_LTZ", "DATETIME", "TIME",
})
_BOOL_TYPES = frozenset({"BOOLEAN", "BOOL"})


class StageGenerator(BaseGenerator):
    """
    Generates SQL for a Data Vault Stage (Hash) Layer.

    Mirrors the dat<avault4dbt stage macro:
    - source_data CTE with optional HWM incremental filter
    - derived_columns CTE
    - hashed_columns projection
    - Optional ghost records (unknown + error) appended via UNION ALL on full loads
    """

    def __init__(
        self,
        source_model: StageModel,
        target_table: str = "stage_view",
        target_schema: Optional[str] = None,
        target_database: Optional[str] = None,
        is_incremental: bool = False,
        enable_ghost_records: bool = False,
        end_of_all_times: Optional[str] = None,
        beginning_of_all_times: Optional[str] = None,
        dialect: Optional[str] = None,
    ) -> None:
        super().__init__(target_table, target_schema, target_database, dialect=dialect)
        self.source_model = source_model
        self.is_incremental = is_incremental
        self.enable_ghost_records = enable_ghost_records
        self.end_of_all_times = end_of_all_times or config.end_of_all_times
        self.beginning_of_all_times = beginning_of_all_times or config.beginning_of_all_times

    def generate_sql(self) -> exp.Expression:
        ldts_col = config.ldts_alias
        src = self.source_model
        src_table = self._get_table_expression(
            src.table_name, src.schema_name, src.database
        )
        target_exp = self._get_table_expression(
            self.target_table, self.target_schema, self.target_database
        )

        # ---------------------------------------------------------
        # 1. Build HWM filter condition (reused in both branches below)
        # ---------------------------------------------------------
        hwm_cond: Optional[exp.Expression] = None
        if self.is_incremental:
            hwm_sub = (
                exp.select(exp.Max(this=exp.column(ldts_col)))
                .from_(target_exp)
                .where(
                    exp.column(ldts_col).neq(
                        exp.Literal.string(self.end_of_all_times)
                    )
                )
            )
            hwm_cond = exp.column(ldts_col) > exp.Paren(this=hwm_sub)

        source_query = exp.select(exp.Star()).from_(src_table)
        if hwm_cond is not None:
            source_query = source_query.where(hwm_cond)

        # ---------------------------------------------------------
        # 2. Derived columns CTE
        # ---------------------------------------------------------
        derived_cte_name = "derived_columns_cte"
        has_derived = bool(src.derived_columns)

        if has_derived:
            # derived CTE wraps source_query (already filtered), main reads from the CTE
            derived_with = self._build_derived_cte(source_query)
            from_table: exp.Expression = exp.Table(
                this=exp.Identifier(this=derived_cte_name, quoted=True)
            )
        else:
            derived_with = None
            from_table = src_table  # HWM applied directly to main_query below

        # ---------------------------------------------------------
        # 3. Main projection (source columns + hashed columns)
        # ---------------------------------------------------------
        projection: list[exp.Expression] = (
            [exp.Star()] if src.include_source_columns else []
        )

        if src.hashed_columns:
            for alias, hash_config in src.hashed_columns.items():
                if isinstance(hash_config, list):
                    hash_expr = self._build_hash_expression(
                        columns=hash_config,
                        is_hashdiff=False,
                        case_sensitivity=src.case_sensitivity,
                        use_rtrim=src.use_rtrim,
                    )
                else:
                    hash_expr = self._build_hash_expression(
                        columns=hash_config.get("columns", []),
                        is_hashdiff=hash_config.get("is_hashdiff", False),
                        case_sensitivity=hash_config.get(
                            "case_sensitivity", src.case_sensitivity
                        ),
                        use_rtrim=hash_config.get("use_rtrim", src.use_rtrim),
                    )
                projection.append(
                    hash_expr.as_(exp.Identifier(this=alias, quoted=True))
                )

        # NULL placeholder columns for schema evolution (mirrors datavault4dbt missing_columns)
        if src.missing_columns:
            for col_name, dtype_str in src.missing_columns.items():
                try:
                    dtype = exp.DataType.build(dtype_str)
                except Exception:
                    dtype = exp.DataType(this=exp.DataType.Type.VARCHAR)
                projection.append(
                    exp.Cast(this=exp.null(), to=dtype).as_(
                        exp.Identifier(this=col_name, quoted=True)
                    )
                )

        # Sequence column — ROW_NUMBER() OVER () (mirrors datavault4dbt sequence option)
        if src.sequence:
            projection.append(
                exp.Window(this=exp.RowNumber()).as_(
                    exp.Identifier(this=src.sequence, quoted=True)
                )
            )

        main_query = exp.select(*projection).from_(from_table)

        if has_derived:
            main_query = main_query.with_(derived_cte_name, as_=derived_with)
        elif hwm_cond is not None:
            # No derived CTE: apply the HWM filter directly to the main query so
            # the ldts column from SELECT * is still accessible in the WHERE clause.
            main_query = main_query.where(hwm_cond)

        # ---------------------------------------------------------
        # 4. Ghost records (only on full loads, mirroring datavault4dbt)
        # ---------------------------------------------------------
        if self.enable_ghost_records and not self.is_incremental:
            unknown_row = self._build_ghost_row(is_unknown=True)
            error_row = self._build_ghost_row(is_unknown=False)
            if unknown_row and error_row:
                ghost_union = unknown_row.union(error_row, distinct=False)
                main_query = main_query.union(ghost_union, distinct=False)

        return main_query

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _build_derived_cte(self, source_query: exp.Select) -> exp.Expression:
        """Build the CTE for derived columns, reading from an already-filtered source query."""
        selection: list[exp.Expression] = [exp.Star()]
        if self.source_model.derived_columns:
            for alias, expr_str in self.source_model.derived_columns.items():
                selection.append(
                    parse_one(expr_str).as_(
                        exp.Identifier(this=alias, quoted=True)
                    )
                )
        return exp.select(*selection).from_(
            exp.Subquery(this=source_query, alias=exp.TableAlias(this=exp.Identifier(this="_src")))
        )

    def _build_ghost_row(self, is_unknown: bool) -> Optional[exp.Select]:
        """
        Build one ghost record row (unknown or error) for known hash columns.

        Only generates values for hashed columns, ldts, and rsrc.
        All other columns are omitted — suitable when include_source_columns=False
        and all relevant columns are declared in hashed_columns / derived_columns.
        Returns None when no hash columns are defined.
        """
        if not self.source_model.hashed_columns:
            return None

        hex_len = 64 if config.hash.upper() == "SHA256" else 32
        hash_val = "0" * hex_len if is_unknown else "f" * hex_len
        ldts_val = self.beginning_of_all_times if is_unknown else self.end_of_all_times
        rsrc_val = config.default_unknown_rsrc if is_unknown else config.default_error_rsrc

        selection: list[exp.Expression] = []

        # Hash columns
        for alias in self.source_model.hashed_columns:
            selection.append(
                exp.Literal.string(hash_val).as_(
                    exp.Identifier(this=alias, quoted=True)
                )
            )

        # ldts / rsrc — include when they come from derived columns
        if self.source_model.derived_columns:
            for alias in self.source_model.derived_columns:
                if alias in (config.ldts_alias, self.source_model.load_date_col or ""):
                    selection.append(
                        exp.Literal.string(ldts_val).as_(
                            exp.Identifier(this=alias, quoted=True)
                        )
                    )
                elif alias in (config.rsrc_alias, self.source_model.record_source_col or ""):
                    selection.append(
                        exp.Literal.string(rsrc_val).as_(
                            exp.Identifier(this=alias, quoted=True)
                        )
                    )
                else:
                    selection.append(
                        exp.null().as_(exp.Identifier(this=alias, quoted=True))
                    )

        return exp.select(*selection) if selection else None
