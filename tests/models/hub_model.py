from datavault4sqlglot.generators.hub import HubGenerator
from datavault4sqlglot.metadata import SourceModel
## metadata von stage
source_1 = SourceModel(
    database="DB",
    schema="Stage",
    table_name="stg_ORDERS",
    business_keys=["order_id"],
    load_date_col="load_date",
    record_source_col="record_source"
)

source_2 = SourceModel(
    database="DB",
    schema="Stage",
    table_name="stg_WEB_ORDERS",
    business_keys=["web_order_id"],
    load_date_col="load_tss",
    record_source_col="rsrc"
)

generator = HubGenerator(
    target_database="DV_DB",
    target_schema="DV_SCHEMA",
    target_table="HUB_ORDERS",
    hashkey="HK_ORDER_H",
    source_models=[source_1, source_2],
    is_incremental=True
)


print(generator.to_sql())
