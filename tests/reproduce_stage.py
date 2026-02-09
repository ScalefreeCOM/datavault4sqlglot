from datavault4sqlglot.stage import StageGenerator
from sqlglot import exp

gen = StageGenerator("SOURCE_TABLE", db_dialect="snowflake")

# Add Derived Columns first
gen.add_derived_columns({
    "derived_col": "col1 + col2",
    "upper_col": "UPPER(some_col)"
})

# Add Hashes (referencing derived_col)
gen.add_hashes({
    "hk_l_order_customer": ["o_orderkey", "o_custkey"], 
    "hk_derived": ["derived_col"]
})

# Add Meta Columns
gen.add_meta_columns({
    "LDTS": "CURRENT_TIMESTAMP()", 
    "RSRC": "'SYSTEM'"
})

sql = gen.generate_sql()
print(sql)
