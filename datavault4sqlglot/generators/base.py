from abc import ABC, abstractmethod
import logging
from typing import Dict, List, Optional, Tuple, Union

import sqlglot
from sqlglot import exp
from sqlglot.expressions import DataType

from datavault4sqlglot.config import config
from datavault4sqlglot.metadata import SourceBinding, SourceModel


class BaseGenerator(ABC):
    """
    Abstract base class for all Data Vault generators.
    """

    def __init__(
        self, 
        target_table: str, 
        target_schema: Optional[str] = None, 
        target_database: Optional[str] = None,
        dialect: Optional[str] = None
    ):
        self.target_table = target_table
        self.target_schema = target_schema
        self.target_database = target_database
        self._dialect = dialect

    @property
    def dialect(self) -> str:
        """
        Returns the dialect to be used for SQL generation.
        Prioritizes instance-level override, then falls back to global configuration.
        """
        return self._dialect or config.dialect

    def _resolve_column_config(
        self, col_config: Union[str, Dict[str, str]]
    ) -> Tuple[str, str]:
        """
        Returns (source_column_name, target_alias) for a column that may be supplied
        as a plain string or as ``{"source_column": "x", "alias": "y"}``.
        """
        if isinstance(col_config, dict):
            src = col_config["source_column"]
            return src, col_config.get("alias", src)
        return col_config, col_config

    def _get_table_with_alias(
        self,
        table: str,
        alias: str,
        schema: Optional[str] = None,
        database: Optional[str] = None,
    ) -> exp.Table:
        """Like _get_table_expression but adds a table alias."""
        tbl = self._get_table_expression(table, schema, database)
        tbl.set("alias", exp.TableAlias(this=exp.Identifier(this=alias)))
        return tbl

    def _get_table_expression(
        self, 
        table: str, 
        schema: Optional[str] = None, 
        database: Optional[str] = None
    ) -> exp.Table:
        """
        Converts table, schema, and database strings into a sqlglot.exp.Table.
        """
        quoted = config.quote_identifiers
        return exp.Table(
            this=exp.Identifier(this=table, quoted=quoted),
            db=exp.Identifier(this=schema, quoted=quoted) if schema else None,
            catalog=exp.Identifier(this=database, quoted=quoted) if database else None
        )

    @abstractmethod
    def generate_sql(self) -> exp.Expression:
        """
        Generates the SQL expression for the entity.
        """
        pass

    def to_sql(self, pretty: bool = True) -> str:
        """
        Renders the generated expression into a SQL string based on the configuration or instance dialect.
        """
        return self.generate_sql().sql(dialect=self.dialect, pretty=pretty)

    def _build_rsrc_static_hwm_query(
        self,
        bindings: List[SourceBinding],
        target_exp: exp.Table,
        ldts_col: str,
        rsrc_col: str,
        end_of_all_times: str,
    ) -> Optional[exp.Expression]:
        """
        Builds a UNION ALL of ``SELECT MAX(ldts) AS max_ldts, '<val>' AS rsrc_static``
        per rsrc_static value across all bindings.

        Returns None when no binding has rsrc_statics defined.  The result is
        intended as the body of the ``max_ldts_per_rsrc_static_in_target`` CTE.
        """
        union_selects = []
        for src in bindings:
            for sv in (src.rsrc_statics or []):
                union_selects.append(
                    exp.select(
                        exp.Max(this=exp.column(ldts_col)).as_("max_ldts"),
                        exp.Literal.string(sv).as_("rsrc_static"),
                    )
                    .from_(target_exp)
                    .where(exp.column(rsrc_col).like(exp.Literal.string(sv)))
                    .where(exp.column(ldts_col).neq(exp.Literal.string(end_of_all_times)))
                )
        if not union_selects:
            return None
        return (
            sqlglot.union(*union_selects, distinct=False)
            if len(union_selects) > 1
            else union_selects[0]
        )

    def _build_rsrc_static_or_filter(
        self,
        statics: List[str],
        src_ldts: str,
        src_rsrc: str,
        hwm_cte_name: str,
        beginning_of_all_times: str,
    ) -> exp.Expression:
        """
        Builds the OR expression used to filter a source CTE against the HWM CTE:

            (rsrc = 'val' AND src_ldts > (SELECT COALESCE(MAX(max_ldts), boa)
                                           FROM hwm_cte WHERE rsrc_static = 'val'))
            OR ...

        One branch per entry in ``statics``.
        """
        conditions = [
            exp.and_(
                exp.column(src_rsrc).like(exp.Literal.string(sv)),
                exp.column(src_ldts)
                > exp.Paren(
                    this=exp.select(
                        exp.Coalesce(
                            this=exp.Max(this=exp.column("max_ldts")),
                            expressions=[exp.Literal.string(beginning_of_all_times)],
                        )
                    )
                    .from_(hwm_cte_name)
                    .where(exp.column("rsrc_static").like(exp.Literal.string(sv)))
                ),
            )
            for sv in statics
        ]
        return exp.or_(*conditions)

    def _hash_column(
        self, 
        columns: List[str], 
        alias: str = None,
        is_hashdiff: bool = False,
        case_sensitivity: Optional[bool] = None,
        use_rtrim: Optional[bool] = None
    ) -> exp.Expression:
        """
        Generates a hash expression (MD5) for the given columns using standard DV patterns.
        Wraps _build_hash_expression for backward compatibility/aliasing.
        """
        hash_exp = self._build_hash_expression(
            columns, 
            is_hashdiff=is_hashdiff, 
            case_sensitivity=case_sensitivity, 
            use_rtrim=use_rtrim
        )
        if alias:
            return hash_exp.as_(alias)
        return hash_exp

    def _get_type(self, data_type: DataType.Type, length: int = None):
        return DataType.build(data_type, expressions=[exp.Literal.number(length)] if length else None)

    @staticmethod
    def _chr(code: int) -> exp.Expression:
        return exp.Chr(expressions=[exp.Literal.number(code)])

    def _clean_column(self, col_name: str, use_rtrim: bool = True):
        """Standard Data Vault column cleaning for hashing."""
        varchar_type = self._get_type(DataType.Type.VARCHAR)

        # 1. Cast
        col_expr = exp.Column(this=exp.Identifier(this=col_name, quoted=config.quote_identifiers))
        c = exp.Cast(this=col_expr, to=varchar_type)

        # 2. Trim (if enabled)
        if use_rtrim:
            c = exp.Trim(this=c)

        # 3. Escape delimiters and quotes.
        # CHR(92) = backslash; used for the \ → \\ escape.
        # The doublequote wrapper uses CHR(34) only (no leading backslash) because
        # Snowflake's ESCAPE_STRING mode interprets '\"' as just '"', matching dbt output.
        bs = self._chr(92)
        bs_bs = exp.Concat(expressions=[self._chr(92), self._chr(92)])

        c = exp.Replace(this=c, expression=bs, replacement=bs_bs)
        c = exp.Replace(this=c, expression=exp.Literal.string('"'), replacement=self._chr(34))
        c = exp.Replace(this=c, expression=exp.Literal.string("^^"), replacement=exp.Literal.string("--"))

        # 4. Wrap: CONCAT('"', c, '"')  =  "value"
        dq = exp.Literal.string('"')
        quoted_col = exp.Concat(expressions=[dq, c, exp.Literal.string('"')])

        # 5. NULL → '^^' placeholder so it contributes to the concat string rather than being dropped
        return exp.Coalesce(this=quoted_col, expressions=[exp.Literal.string("^^")])

    def _dialect_hash(self, inner: exp.Expression, algorithm: str) -> exp.Expression:
        """
        Returns LOWER(hash_func(inner)) using the hash function appropriate for the active
        dialect.  Handles databases that lack a native MD5() function.

        Algorithm is 'MD5' or 'SHA256' (from config.hash).
        """
        dialect = (self.dialect or "").lower()
        alg = algorithm.upper()
        hex_len = 64 if alg in ("SHA256", "SHA2") else 32

        if dialect in ("tsql", "synapse"):
            # T-SQL: LOWER(CONVERT(VARCHAR(32), HASHBYTES('MD5', inner), 2))
            tsql_alg = "SHA2_256" if alg == "SHA256" else "MD5"
            hb = exp.Anonymous(this="HASHBYTES", expressions=[
                exp.Literal.string(tsql_alg), inner
            ])
            converted = exp.Anonymous(this="CONVERT", expressions=[
                exp.DataType.build(f"VARCHAR({hex_len})"), hb, exp.Literal.number(2)
            ])
            return exp.Lower(this=converted)

        elif dialect == "oracle":
            # Oracle: LOWER(CAST(STANDARD_HASH(inner, 'MD5') AS VARCHAR2(40)))
            oracle_alg = "SHA256" if alg == "SHA256" else "MD5"
            sh = exp.Anonymous(this="STANDARD_HASH", expressions=[
                inner, exp.Literal.string(oracle_alg)
            ])
            return exp.Lower(this=exp.Cast(this=sh, to=exp.DataType.build(f"VARCHAR2({hex_len})")))

        elif dialect == "bigquery":
            # BigQuery: MD5/SHA256 return BYTES — must wrap in TO_HEX
            if alg == "SHA256":
                hash_inner = exp.SHA2(this=inner, length=exp.Literal.number(256))
            else:
                hash_inner = exp.MD5(this=inner)
            return exp.Lower(this=exp.Anonymous(this="TO_HEX", expressions=[hash_inner]))

        else:
            # Snowflake, Postgres, Redshift, Databricks, Exasol — standard functions
            if alg == "SHA256":
                h: exp.Expression = exp.SHA2(this=inner, length=exp.Literal.number(256))
            elif hasattr(exp, alg):
                h = getattr(exp, alg)(this=inner)
            else:
                logging.warning(
                    f"Hash algorithm '{alg}' not natively supported by sqlglot.exp. Defaulting to MD5."
                )
                h = exp.MD5(this=inner)
            return exp.Lower(this=h)

    def _build_hash_expression(
        self, 
        columns: list[str],
        is_hashdiff: bool = False,
        case_sensitivity: Optional[bool] = None,
        use_rtrim: Optional[bool] = None
    ) -> exp.Expression:
        """
        Constructs the hash calculation expression.
        MD5(NULLIF(UPPER(CONCAT_WS('||', ...)), '^^...'))
        """
        # Determine effective parameters based on defaults and is_hashdiff
        if case_sensitivity is None:
            case_sensitivity = (
                config.hashdiff_input_case_sensitive if is_hashdiff 
                else config.hashkey_input_case_sensitive
            )
        
        if use_rtrim is None:
            use_rtrim = config.use_trim

        varchar_type = self._get_type(DataType.Type.VARCHAR)

        processed_cols = [self._clean_column(c, use_rtrim=use_rtrim) for c in columns]
        num_cols = len(columns)

        if num_cols == 1:
            # CONCAT(col, '')
            concat_block = exp.Concat(expressions=[processed_cols[0]])
            null_check_string = "^^"
        else:
            # CONCAT_WS('||', col, col...)
            concat_block = exp.ConcatWs(
                expressions=[exp.Literal.string("||"), *processed_cols]
            )
            null_check_string = "||".join(["^^"] * num_cols)
        
        # case_sensitivity=False → apply UPPER (standard DV behavior); True → preserve case
        if not case_sensitivity:
            concat_block = exp.Upper(this=concat_block)
            
        # Remove newlines, tabs, vertical tabs, carriage returns (loop with REGEXP_REPLACE and CHR(i))
        for char_code in [9, 10, 11, 13]:
            concat_block = exp.RegexpReplace(
                this=concat_block,
                expression=exp.Chr(expressions=[exp.Literal.number(char_code)]),
                replacement=exp.Literal.string("")
            )
        
        # NULLIF(CAST(stripped AS VARCHAR), '^^||^^')
        nullif_block = exp.Nullif(
             this=exp.Cast(this=concat_block, to=varchar_type),
             expression=exp.Literal.string(null_check_string)
        )
        
        hash_alg = config.hash.upper()
        hex_len = 64 if "SHA2" in hash_alg or "SHA256" in hash_alg else 32
        return exp.Coalesce(
            this=self._dialect_hash(nullif_block, hash_alg),
            expressions=[exp.Literal.string('0' * hex_len)]
        )
