import sqlglot
from sqlglot import exp, parse_one
from sqlglot.expressions import DataType

class StageGenerator:
    def __init__(self, source_table: str, db_dialect: str = "snowflake"):
        self.source_table = source_table
        self.dialect = db_dialect
        self.hash_definitions = {}
        self.derived_columns = {}
        self.meta_columns = {}
    
    def add_hashes(self, hash_config: dict):
        """
        Accepts a dictionary mapping: {'HASH_KEY_NAME: ['COL1', 'COL2']}
        """
        self.hash_definitions.update(hash_config)

    def add_derived_columns(self, derived_config: dict):
        """
        Accepts a dictionary of alias -> expression/string
        """
        self.derived_columns.update(derived_config)

    def add_meta_columns(self, meta_config: dict):
        """
        Accepts a dictionary of alias -> expression/string
        """
        self.meta_columns.update(meta_config)
    
    def _get_type(self, data_type: DataType.Type, length: int = None):

        return DataType.build(data_type, expressions=[exp.Literal.number(length)] if length else None)
    
    def _clean_column(self, col_name: str):
        """inner column cleaning"""
        
        varchar_type = self._get_type(DataType.Type.VARCHAR, 4000)
        
        c = exp.Trim(this=exp.Cast(this=exp.column(col_name), to=varchar_type))
        # 2. Escape backslashes, quotes, and the '^^' delimiter
        c = exp.func("REPLACE", c, exp.Literal.string("\\"), exp.Literal.string("\\\\"))
        c = exp.func("REPLACE", c, exp.Literal.string('"'), exp.Literal.string('\"'))
        c = exp.func("REPLACE", c, exp.Literal.string("^^"), exp.Literal.string("--"))
        
        # 3. Quoting: CONCAT('"', col, '"')
        quote = exp.Literal.string('"')
        quoted_col = exp.Concat(expressions=[quote, c, quote])
        
        # 4. Handle Nulls with '^^'
        #return exp.func("ISNULL", quoted_col, exp.Literal.string("^^"))
        return exp.Coalesce(this=quoted_col, expressions=[exp.Literal.string("^^")])

    def _build_hash_expression(self, columns: list):
        """
        Constructs hash columns
        """
        varchar_type = self._get_type(DataType.Type.VARCHAR, 4000)
        binary_type = self._get_type(DataType.Type.BINARY, 16)

        num_cols = len(columns)
        processed_cols = [self._clean_column(c) for c in columns]

        if num_cols == 1:
            concat_block = exp.func("CONCAT", processed_cols[0], exp.Literal.string(""))
            null_check_string = "^^"
            
        else:
            concat_block = exp.func("CONCAT_WS", exp.Literal.string("||"), *processed_cols)
            null_check_string = "||".join(["^^"] * num_cols)
        

        stripped = exp.Upper(this=concat_block)

        #for char_code in [10, 9, 11, 13]:
        #    stripped = exp.Replace(this=stripped, old=exp.func("CHAR", exp.Literal.number(char_code)), new=exp.Literal.string(""))

        nullif_block = exp.func("NULLIF", exp.Cast(this=stripped, to=varchar_type), exp.Literal.string(null_check_string))
        
        hash_expr = exp.MD5(this=nullif_block)

        # hash_expr_bin = exp.Cast(this=hash_expr, to=binary_type)

        #zero_binary = exp.Cast(this=exp.Literal.string('0' * 32), to=binary_type)
        
        #return exp.func("ISNULL", hash_expr, zero_binary)
        return exp.Coalesce(this=hash_expr, expressions=[exp.Literal.string('0' * 32)])
    
    def generate_sql(self, hash_config: dict = None):
        if hash_config:
             self.add_hashes(hash_config)

        # 1. Derived Columns (Inner CTE)
        derived_expressions = [exp.Star()]
        for alias, expression in self.derived_columns.items():
             if isinstance(expression, str):
                 expression = parse_one(expression)
             derived_expressions.append(exp.Alias(this=expression, alias=exp.Identifier(this=alias, quoted=False)))
        
        derived_cte_name = "derived_columns_cte"
        derived_cte = exp.select(*derived_expressions).from_(self.source_table)

        # 2. Main Projection (Hashes + Meta)
        projection = [exp.Star()]

        # Hashes
        for alias, cols in self.hash_definitions.items():
            hash_logic = self._build_hash_expression(cols)
            projection.append(exp.Alias(this=hash_logic, alias=exp.Identifier(this=alias, quoted=False)))

        # Meta Columns
        for alias, expression in self.meta_columns.items():
             if isinstance(expression, str):
                 expression = parse_one(expression)
             projection.append(exp.Alias(this=expression, alias=exp.Identifier(this=alias, quoted=False)))

        return exp.select(*projection).from_(derived_cte_name).with_(derived_cte_name, as_=derived_cte).sql(dialect=self.dialect, pretty=True)