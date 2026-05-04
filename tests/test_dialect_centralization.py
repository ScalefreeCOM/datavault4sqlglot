from datavault4sqlglot.generators.stage import StageGenerator
from datavault4sqlglot.metadata import StageModel
from datavault4sqlglot.config import config

# 1. Setup Source
source = StageModel(
    table_name="orders",
    hashed_columns={"hk_order": ["order_id"]}
)

# 2. Test Default (Snowflake)
config.dialect = "snowflake"
gen_sf = StageGenerator(source_model=source)
sql_sf = gen_sf.to_sql()
print("--- Snowflake (Default) ---")
print(sql_sf[:200]) # Print first 200 chars

# 3. Test Global Override (Postgres)
config.dialect = "postgres"
gen_pg = StageGenerator(source_model=source)
sql_pg = gen_pg.to_sql()
print("\n--- Postgres (Global Override) ---")
print(sql_pg[:200])

# 4. Test Instance Override (DuckDB)
gen_duck = StageGenerator(source_model=source, dialect="duckdb")
sql_duck = gen_duck.to_sql()
print("\n--- DuckDB (Instance Override) ---")
print(sql_duck[:200])

# Verify CHR vs CHAR logic via dialect transpile
# Note: My to_sql() uses the internal dialect
print("\n--- Dialect specific characters ---")
if "CHR(" in sql_pg: print("Postgres correctly uses CHR")
if "CHAR(" in sql_duck: print("DuckDB (instance) correctly uses CHAR")
