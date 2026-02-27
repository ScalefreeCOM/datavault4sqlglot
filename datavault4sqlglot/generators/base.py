from abc import ABC, abstractmethod
import logging
from typing import List, Union, Optional

from sqlglot import exp
from sqlglot.expressions import DataType
from datavault4sqlglot.config import config


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

    def _get_table_expression(
        self, 
        table: str, 
        schema: Optional[str] = None, 
        database: Optional[str] = None
    ) -> exp.Table:
        """
        Converts table, schema, and database strings into a sqlglot.exp.Table.
        """
        return exp.Table(
            this=exp.Identifier(this=table, quoted=True),
            db=exp.Identifier(this=schema, quoted=True) if schema else None,
            catalog=exp.Identifier(this=database, quoted=True) if database else None
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

    def _clean_column(self, col_name: str, use_rtrim: bool = True):
        """Standard Data Vault column cleaning for hashing."""
        varchar_type = self._get_type(DataType.Type.VARCHAR, 4000)
        
        # 1. Cast
        # Use explicit Column with Identifier to ensure quoting
        col_expr = exp.Column(this=exp.Identifier(this=col_name, quoted=True))
        c = exp.Cast(this=col_expr, to=varchar_type)
        
        # 2. Trim (if enabled)
        if use_rtrim:
            c = exp.Trim(this=c)
        
        # 3. Escape delimiters and quotes
        c = exp.Replace(this=c, expression=exp.Literal.string(r"\\"), replacement=exp.Literal.string(r"\\\\"))
        c = exp.Replace(this=c, expression=exp.Literal.string(r'"'), replacement=exp.Literal.string(r'\"'))
        c = exp.Replace(this=c, expression=exp.Literal.string("^^"), replacement=exp.Literal.string("--"))
        
        # 4. Quoting: CONCAT('\"', c, '\"')
        quote = exp.Literal.string(r'\"')
        quoted_col = exp.Concat(expressions=[quote, c, quote])
        
        # 5. Handle Nulls with Ghost Record '^^'
        return exp.Nullif(this=quoted_col, expression=exp.Literal.string("^^"))

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

        varchar_type = self._get_type(DataType.Type.VARCHAR, 4000)
        
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
        
        # UPPER (if not case sensitive)
        # Note: If case_sensitivity is False, it means we WANT to normalize to UPPER (standard DV behavior)
        # If case_sensitivity is True, we keep it as is.
        # UPPER (if not case sensitive)
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
        
        # Hash Function Selection
        hash_alg = config.hash.upper()
        if hash_alg == "SHA256":
            hash_expr = exp.SHA2(this=nullif_block, length=exp.Literal.number(256))
        elif hasattr(exp, hash_alg):
            hash_func = getattr(exp, hash_alg)
            hash_expr = hash_func(this=nullif_block)
        else:
            logging.warning(f"Hash algorithm '{hash_alg}' not natively supported by sqlglot.exp. Defaulting to MD5.")
            hash_expr = exp.MD5(this=nullif_block)
            
        hash_expr = exp.Lower(this=hash_expr)
        
        # NULLIF(MD5(...), '0000...') -> Binary Hash Default
        # Hex length: MD5=32, SHA256=64
        hex_len = 64 if "SHA2" in hash_alg or "SHA256" in hash_alg else 32
        return exp.Nullif(this=hash_expr, expression=exp.Literal.string('0' * hex_len))
