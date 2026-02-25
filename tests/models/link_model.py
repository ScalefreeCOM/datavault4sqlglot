from datavault4sqlglot.generators.link import LinkGenerator
from datavault4sqlglot.metadata import SourceModel

source_1 = SourceModel(
    database="DB",
    schema="Stage",
    table_name="stg_ORDERS",
    link_hash_key="HK_ORDER_CUSTOMER_L",
    foreign_hash_keys=["HK_ORDER_H", "HK_CUSTOMER_H"],
    load_date_col="load_date",
    record_source_col="record_source",
    business_keys=["order_id", "customer_id"]
)

generator = LinkGenerator(
    target_database="DV_DB",
    target_schema="DV_SCHEMA",
    target_table="LINK_ORDER_CUSTOMER",
    link_hash_key="HK_ORDER_CUSTOMER_L",
    source_models=[source_1]
)

print(generator.generate_sql().sql(pretty=True))
