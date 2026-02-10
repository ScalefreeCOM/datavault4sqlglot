from abc import ABC, abstractmethod
from typing import List, Union

from sqlglot import exp
from sqlglot.expressions import DataType


class BaseGenerator(ABC):
    """
    Abstract base class for all Data Vault generators.
    """

    def __init__(self, target_table_name: str):
        self.target_table_name = target_table_name

    @abstractmethod
    def generate_sql(self) -> exp.Expression:
        """
        Generates the SQL expression for the entity.
        """
        pass

    def _hash_column(self, columns: List[str], alias: str = None) -> exp.Expression:
        """
        Generates a hash expression (MD5) for the given columns using standard DV patterns.
        Wraps _build_hash_expression for backward compatibility/aliasing.
        """
        hash_exp = self._build_hash_expression(columns)
        if alias:
            return hash_exp.as_(alias)
        return hash_exp

    def _get_type(self, data_type: DataType.Type, length: int = None):
        return DataType.build(data_type, expressions=[exp.Literal.number(length)] if length else None)

    def _clean_column(self, col_name: str):
        """Standard Data Vault column cleaning for hashing."""
        varchar_type = self._get_type(DataType.Type.VARCHAR, 4000)
        
        # 1. Trim and Cast
        c = exp.Trim(this=exp.Cast(this=exp.Column(this=col_name), to=varchar_type))
        
        # 2. Escape delimiters and quotes
        # REPLACE(val, '\', '\\')
        c = exp.func("REPLACE", c, exp.Literal.string("\\"), exp.Literal.string("\\\\"))
        c = exp.func("REPLACE", c, exp.Literal.string('"'), exp.Literal.string('\"'))
        c = exp.func("REPLACE", c, exp.Literal.string("^^"), exp.Literal.string("--"))
        
        # 3. Quoting: CONCAT('"', c, '"')
        quote = exp.Literal.string('"')
        quoted_col = exp.Concat(expressions=[quote, c, quote])
        
        # 4. Handle Nulls with Ghost Record '^^'
        return exp.Coalesce(this=quoted_col, expressions=[exp.Literal.string("^^")])

    def _build_hash_expression(self, columns: list) -> exp.Expression:
        """
        Constructs the hash calculation expression.
        MD5(NULLIF(UPPER(CONCAT_WS('||', ...)), '^^...'))
        """
        varchar_type = self._get_type(DataType.Type.VARCHAR, 4000)
        
        processed_cols = [self._clean_column(c) for c in columns]
        num_cols = len(columns)

        if num_cols == 1:
            # CONCAT(col, '') ? implied in original logic
            concat_block = exp.Concat(expressions=[processed_cols[0], exp.Literal.string("")])
            null_check_string = "^^"
        else:
            # CONCAT_WS('||', col, col...)
            # sqlglot.exp.ConcatWs(expressions=[delim, col1, col2...])
            concat_block = exp.ConcatWs(
                expressions=[exp.Literal.string("||"), *processed_cols]
            )
            null_check_string = "||".join(["^^"] * num_cols)
        
        # UPPER
        stripped = exp.Upper(this=concat_block)
        
        # NULLIF(CAST(stripped AS VARCHAR), '^^||^^')
        nullif_block = exp.Nullif(
             this=exp.Cast(this=stripped, to=varchar_type),
             expression=exp.Literal.string(null_check_string)
        )
        
        # MD5
        hash_expr = exp.MD5(this=nullif_block)
        
        # COALESCE(MD5(...), '0000...') -> Binary Hash Default
        return exp.Coalesce(this=hash_expr, expressions=[exp.Literal.string('0' * 32)])
