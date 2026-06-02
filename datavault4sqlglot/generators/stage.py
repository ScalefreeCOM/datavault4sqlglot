from __future__ import annotations

from typing import Literal, Optional

from sqlglot import exp, parse_one

from datavault4sqlglot.config import config
from datavault4sqlglot.generators.base import BaseGenerator
from datavault4sqlglot.metadata import StageModel

_GhostType = Literal["unknown", "error"]

# Hash sentinel values keyed by the first matching token of config.hash (upper-cased).
# unknown → all-zeros hex; error → all-f's hex.
_HASH_SENTINELS: dict[str, tuple[str, str]] = {
    "MD5":    ("00000000000000000000000000000000",
               "ffffffffffffffffffffffffffffffff"),
    "SHA256": ("0000000000000000000000000000000000000000000000000000000000000000",
               "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"),
    "SHA2":   ("0000000000000000000000000000000000000000000000000000000000000000",
               "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"),
    "SHA1":   ("0000000000000000000000000000000000000000",
               "ffffffffffffffffffffffffffffffffffffffff"),
    "SHA":    ("0000000000000000000000000000000000000000",
               "ffffffffffffffffffffffffffffffffffffffff"),
}


class StageGenerator(BaseGenerator):
    """
    Generates SQL for a Data Vault Stage (Hash) Layer.

    Mirrors the datavault4dbt stage macro:
    - source columns + optional derived columns
    - hashed_columns projection (MD5 / SHA expressions)
    - optional ghost records (unknown + error) appended as UNION ALL

    When source_model.ghost_record_types is set the output matches the
    datavault4dbt ghost record pattern exactly:

        [WITH derived_columns_cte AS (...),]
             unknown_values AS (SELECT <type-aware values>, <hash sentinels>),
             error_values   AS (SELECT <type-aware values>, <hash sentinels>),
             ghost_records  AS (SELECT * FROM unknown_values
                                UNION ALL
                                SELECT * FROM error_values)
        SELECT *, <hash_exprs>
        FROM   <source | derived_columns_cte>
        [WHERE hwm]
        UNION ALL
        SELECT * FROM ghost_records

    Hash columns in ghost rows use literal sentinel values:
        unknown → '000...000'  (MD5: 32 zeros; SHA256: 64 zeros)
        error   → 'fff...fff'  (MD5: 32 f's;   SHA256: 64 f's)
    """

    def __init__(
        self,
        source_model: StageModel,
        target_table: str = "stage_view",
        target_schema: Optional[str] = None,
        target_database: Optional[str] = None,
        is_incremental: bool = False,
        dialect: Optional[str] = None,
    ) -> None:
        super().__init__(target_table, target_schema, target_database, dialect=dialect)
        self.source_model = source_model
        self.is_incremental = is_incremental

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
        # 1. HWM filter condition
        # ---------------------------------------------------------
        hwm_cond: Optional[exp.Expression] = None
        if self.is_incremental:
            hwm_sub = (
                exp.select(exp.Max(this=exp.column(ldts_col)))
                .from_(target_exp)
                .where(
                    exp.column(ldts_col).neq(
                        exp.Literal.string(config.end_of_all_times)
                    )
                )
            )
            hwm_cond = exp.column(ldts_col) > exp.Paren(this=hwm_sub)

        has_ghost = bool(src.ghost_record_types)
        has_derived = bool(src.derived_columns)

        # ---------------------------------------------------------
        # 2. Derived CTE and FROM target for main SELECT
        # ---------------------------------------------------------
        derived_cte: Optional[exp.Expression] = None

        if has_derived:
            filtered_source = exp.select(exp.Star()).from_(src_table)
            if hwm_cond is not None:
                filtered_source = filtered_source.where(hwm_cond)
            derived_cte = self._build_derived_cte(filtered_source)
            final_from: exp.Expression = exp.Table(
                this=exp.Identifier(this="derived_columns_cte", quoted=False)
            )
        else:
            final_from = src_table

        # ---------------------------------------------------------
        # 3. Main SELECT (source columns + hash expressions)
        # ---------------------------------------------------------
        main_select = exp.select(*self._build_projection(src)).from_(final_from)
        if not has_derived and hwm_cond is not None:
            main_select = main_select.where(hwm_cond)

        # ---------------------------------------------------------
        # 4. Ghost records UNION ALL (datavault4dbt pattern)
        # ---------------------------------------------------------
        # unknown_values / error_values CTEs hold literal typed values;
        # hash columns use all-zeros / all-f's sentinels — no hashing applied.
        if has_ghost:
            unknown_select = self._build_ghost_values_select(src, "unknown")
            error_select = self._build_ghost_values_select(src, "error")
            ghost_records_q = (
                exp.select(exp.Star())
                .from_(exp.Table(this=exp.Identifier(this="unknown_values")))
                .union(
                    exp.select(exp.Star()).from_(
                        exp.Table(this=exp.Identifier(this="error_values"))
                    ),
                    distinct=False,
                )
            )
            ghost_ref = exp.select(exp.Star()).from_(
                exp.Table(this=exp.Identifier(this="ghost_records"))
            )
            result: exp.Expression = main_select.union(ghost_ref, distinct=False)
        else:
            result = main_select

        # ---------------------------------------------------------
        # 5. Attach CTEs (order matters: derived → ghost)
        # ---------------------------------------------------------
        if derived_cte is not None:
            result = result.with_("derived_columns_cte", as_=derived_cte)
        if has_ghost:
            result = (
                result
                .with_("unknown_values", as_=unknown_select)
                .with_("error_values", as_=error_select)
                .with_("ghost_records", as_=ghost_records_q)
            )

        return result

    # ------------------------------------------------------------------
    # Projection helper
    # ------------------------------------------------------------------

    def _build_projection(self, src: StageModel) -> list[exp.Expression]:
        """Build SELECT projection: source columns + hashed + missing + sequence."""
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
                    hash_expr.as_(
                        exp.Identifier(this=alias, quoted=config.quote_identifiers)
                    )
                )

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

        if src.sequence:
            projection.append(
                exp.Window(this=exp.RowNumber()).as_(
                    exp.Identifier(this=src.sequence, quoted=True)
                )
            )

        return projection

    # ------------------------------------------------------------------
    # Ghost record helpers
    # ------------------------------------------------------------------

    def _build_ghost_values_select(
        self, src: StageModel, record_type: _GhostType
    ) -> exp.Select:
        """
        Build the SELECT for the unknown_values or error_values ghost CTE.

        Column order mirrors the main projection:
          1. Source columns (from ghost_record_types) — type-aware values
          2. Hash columns   (from hashed_columns keys) — sentinel hex literals
          3. missing_columns — always NULL (schema-evolution placeholders)
          4. sequence column — NULL (no meaningful row number for ghost rows)
        """
        ldts_col = src.load_date_col or config.ldts_alias
        rsrc_col = src.record_source_col or config.rsrc_alias
        unknown_key, error_key = self._ghost_hash_sentinels()
        hash_sentinel = unknown_key if record_type == "unknown" else error_key

        selections: list[exp.Expression] = []

        # 1. Source columns
        if src.include_source_columns:
            for col_name, dtype_str in (src.ghost_record_types or {}).items():
                value = self._ghost_value_for_col(
                    col_name, dtype_str, record_type, ldts_col, rsrc_col
                )
                try:
                    dtype = exp.DataType.build(dtype_str)
                except Exception:
                    dtype = exp.DataType(this=exp.DataType.Type.VARCHAR)
                selections.append(
                    exp.Cast(this=value, to=dtype).as_(
                        exp.Identifier(this=col_name, quoted=config.quote_identifiers)
                    )
                )

        # 2. Hash columns — sentinel literal, no computation
        if src.hashed_columns:
            for hash_col_name in src.hashed_columns.keys():
                selections.append(
                    exp.Literal.string(hash_sentinel).as_(
                        exp.Identifier(this=hash_col_name, quoted=config.quote_identifiers)
                    )
                )

        # 3. missing_columns — always NULL in ghost rows
        if src.missing_columns:
            for col_name, dtype_str in src.missing_columns.items():
                try:
                    dtype = exp.DataType.build(dtype_str)
                except Exception:
                    dtype = exp.DataType(this=exp.DataType.Type.VARCHAR)
                selections.append(
                    exp.Cast(this=exp.null(), to=dtype).as_(
                        exp.Identifier(this=col_name, quoted=True)
                    )
                )

        # 4. sequence — NULL
        if src.sequence:
            selections.append(
                exp.null().as_(exp.Identifier(this=src.sequence, quoted=True))
            )

        return exp.select(*selections)

    def _ghost_value_for_col(
        self,
        col_name: str,
        dtype_str: str,
        record_type: _GhostType,
        ldts_col: str,
        rsrc_col: str,
    ) -> exp.Expression:
        """
        Return the ghost value expression for one source column.

        Precedence:
        1. ldts column  → beginning_of_all_times (unknown) / end_of_all_times (error)
        2. rsrc column  → config.ghost_record_rsrc / config.ghost_record_error_rsrc
        3. TIMESTAMP / DATETIME → same timestamp sentinel as ldts
        4. DATE         → same date sentinel as ldts
        5. string types (CHAR/VARCHAR/TEXT/STRING) → '(unknown)' / '(error)'
        6. numeric types (INT/FLOAT/DECIMAL/…)     → -1 / -2
        7. BOOLEAN      → FALSE
        8. anything else → NULL
        """
        is_unknown = record_type == "unknown"
        d = dtype_str.strip().upper()

        if col_name == ldts_col:
            return exp.Literal.string(
                self.beginning_of_all_times if is_unknown else self.end_of_all_times
            )
        if col_name == rsrc_col:
            return exp.Literal.string(
                config.ghost_record_rsrc if is_unknown else config.ghost_record_error_rsrc
            )
        if "TIMESTAMP" in d or "DATETIME" in d:
            return exp.Literal.string(
                self.beginning_of_all_times if is_unknown else self.end_of_all_times
            )
        if d == "DATE":
            return exp.Literal.string(
                self.beginning_of_all_times if is_unknown else self.end_of_all_times
            )
        if any(t in d for t in ("CHAR", "TEXT", "STRING", "VARCHAR")):
            return exp.Literal.string("(unknown)" if is_unknown else "(error)")
        if any(
            t in d
            for t in ("INT", "FLOAT", "DOUBLE", "DECIMAL", "NUMERIC", "NUMBER",
                      "REAL", "BIGINT", "SMALLINT", "BYTEINT", "TINYINT")
        ):
            return exp.Literal.number(-1 if is_unknown else -2)
        if d == "BOOLEAN":
            return exp.Boolean(this=False)
        return exp.null()

    def _ghost_hash_sentinels(self) -> tuple[str, str]:
        """Return (unknown_key, error_key) for the configured hash algorithm."""
        h = config.hash.upper()
        for key, sentinels in _HASH_SENTINELS.items():
            if key in h:
                return sentinels
        return _HASH_SENTINELS["MD5"]

    # ------------------------------------------------------------------
    # Derived CTE helper
    # ------------------------------------------------------------------

    def _build_derived_cte(self, source_query: exp.Select) -> exp.Expression:
        """Build the derived columns CTE, wrapping an already-filtered source query."""
        selection: list[exp.Expression] = [exp.Star()]
        if self.source_model.derived_columns:
            for alias, expr_str in self.source_model.derived_columns.items():
                selection.append(
                    parse_one(expr_str).as_(
                        exp.Identifier(this=alias, quoted=config.quote_identifiers)
                    )
                )
        return exp.select(*selection).from_(
            exp.Subquery(
                this=source_query,
                alias=exp.TableAlias(this=exp.Identifier(this="_src")),
            )
        )
