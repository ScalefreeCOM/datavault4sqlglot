from datavault4sqlglot.generators.hub import HubGenerator
from datavault4sqlglot.metadata import SourceTable

source_1 = SourceTable(
    database="RAW_DB",
    schema="RAW_SCHEMA",
    table_name="ORDERS",
    business_keys=["order_id"],
    load_date_col="load_date",
    record_source_col="record_source"
)

source_2 = SourceTable(
    database="RAW_DB",
    schema="RAW_SCHEMA",
    table_name="WEB_ORDERS",
    business_keys=["web_order_id"],
    load_date_col="load_tss",
    record_source_col="rsrc"
)

generator = HubGenerator(
    target_database="DV_DB",
    target_schema="DV_SCHEMA",
    target_table="HUB_ORDERS",
    source_models=[source_1, source_2]
)

print(generator.generate_sql().sql(pretty=True))
