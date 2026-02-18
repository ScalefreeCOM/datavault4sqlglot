from datavault4sqlglot.generators.satellite import SatelliteGenerator
from datavault4sqlglot.metadata import SourceTable

source_1 = SourceTable(
    database="DB",
    schema="Stage",
    table_name="stg_ORDERS",
    hash_key_col="HK_ORDER_H",
    hash_diff="HK_ORDER_DETAILS_D",
    payload=["ORDER_DATE", "ORDER_STATUS", "TOTAL_PRICE"],
    load_date_col="load_date",
    record_source_col="record_source",
    business_keys=["order_id"]
)

generator = SatelliteGenerator(
    target_database="DV_DB",
    target_schema="DV_SCHEMA",
    target_table="SAT_ORDER_DETAILS",
    parent_hash_key="HK_ORDER_H",
    hash_diff="HK_ORDER_DETAILS_D",
    source_models=[source_1]
)

print(generator.generate_sql().sql(pretty=True))
