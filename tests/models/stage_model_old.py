from datavault4sqlglot.stage import StageGenerator
# --- Usage ---
gen = StageGenerator("USER_SPACES.USER_MSZERENCSE.ORDERS_TPCH_SF1", db_dialect="snowflake")
sql = gen.generate_sql({"hk_l_order_customer": ["o_orderkey", "o_custkey"], "hk_h_order": ["o_orderkey"]})
print(sql)